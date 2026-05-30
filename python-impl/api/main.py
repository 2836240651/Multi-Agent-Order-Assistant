"""FastAPI 入口：W1-W6 全量端点。

设计.md §5.3 SSE 事件：start / token / citation / agent_step / interrupt / done / error。
W5 版本路由：rollout.decide() → v1/v2/v3 图；v3 复杂意图走完整 planner→critic→risk_review。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Any, AsyncIterator

from fastapi import Depends, FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from agents import (
    AgentState,
    get_checkpointer,
    get_graph,
    initial_state,
    stream_knowledge,
)
from agents.intent_router import run_intent_router
from auth.jwt import create_access_token, create_refresh_token, verify_token, revoke_all_refresh_tokens
from auth.permissions import CurrentUser, get_current_user, require_perm
from auth.user_service import authenticate_user, get_user_roles_and_perms
from db import current_tenant_id
from exceptions import BusinessException, ErrorCode, http_status_for
from middleware import TenantMiddleware

logger = logging.getLogger(__name__)


# ---------- 跨租户审计工具 ----------

async def _audit_cross_tenant(
    user_id: int | None,
    action: str,
    target_tenant_id: int | None = None,
    payload: dict | None = None,
) -> None:
    """记录跨租户/管理操作到 audit_logs。不阻塞主流程。"""
    try:
        from db.models import AuditLog
        from db.session import async_session
        from db.tenant_context import skip_tenant_filter

        async with async_session() as session:
            with skip_tenant_filter(reason="audit_log_write"):
                log = AuditLog(
                    user_id=user_id,
                    action=action,
                    target_type="tenant",
                    target_id=target_tenant_id,
                    payload=payload,
                )
                session.add(log)
                await session.commit()
    except Exception as exc:
        logger.warning("audit log write failed: %s", exc)


# ---------- Lifespan ----------
@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: D401
    """启动时预热 graph、KB 索引与 tracer；失败不阻塞。"""
    try:
        from tracing.otel_config import init_tracer

        init_tracer()
    except Exception as exc:  # pragma: no cover
        logger.warning("tracer init failed: %s", exc)

    try:
        get_graph()
    except Exception as exc:  # pragma: no cover
        logger.warning("graph warmup failed: %s", exc)

    if os.getenv("SKIP_KB_BOOTSTRAP") != "1":
        try:
            from rag.bootstrap import ensure_kb_indexed

            stats = ensure_kb_indexed()
            logger.info("KB bootstrap on startup: %s", stats)
        except Exception as exc:  # pragma: no cover
            logger.warning("KB bootstrap failed: %s", exc)

    yield


# ---------- App ----------
app = FastAPI(
    title="RetailGuard Copilot API",
    description="W1: RAG + Knowledge Agent + Tenant Middleware",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TenantMiddleware)


# ---------- 异常处理 ----------
@app.exception_handler(BusinessException)
async def _handle_business_exc(_: Request, exc: BusinessException) -> JSONResponse:
    return JSONResponse(status_code=http_status_for(exc.code), content=exc.to_dict())


@app.exception_handler(Exception)
async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
    logger.exception("unhandled error: %s", exc)
    biz = BusinessException(ErrorCode.SYS_INTERNAL_ERROR, message="服务内部异常")
    return JSONResponse(status_code=http_status_for(biz.code), content=biz.to_dict())


# ---------- 请求 / 响应 ----------
class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    thread_id: str | None = None
    user_id: int | None = None
    version: str = Field(default="v3", pattern="^v[1-3]$")


# ---------- SSE 工具 ----------
def _sse_event(event: str, data: dict[str, Any]) -> str:
    """格式化单个 SSE 事件。data 始终 JSON 序列化。"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


_COMPLEX_INTENTS = frozenset({"refund", "order_query", "address_change", "logistics_query", "ticket_create", "complex"})


async def _stream_chat(state: AgentState) -> AsyncIterator[str]:
    """主流式逻辑。

    路由策略：
    - greeting → 快路径，单次 LLM
    - v3 + 复杂意图（退款/订单/地址/complex 或 complexity≥60）→ 完整 supervisor 图
    - 其余（v1/v2，或 v3 知识类）→ KnowledgeAgent 流式
    """
    request_id = uuid.uuid4().hex

    # ── 版本路由（rollout 决策）────────────────────────────────
    from agents.rollout import decide as _rollout_decide
    version_hint = state.get("version") or "v3"
    version = _rollout_decide(
        version_hint=version_hint,
        user_id=state.get("user_id"),
        tenant_id=state.get("tenant_id"),
    )
    state["version"] = version  # type: ignore[index]

    yield _sse_event("start", {
        "request_id": request_id,
        "thread_id": state.get("thread_id"),
        "version": version,
    })

    # ── 意图识别 ────────────────────────────────────────────────
    try:
        intent_update = await run_intent_router(state)
    except Exception as exc:
        logger.exception("intent router failed: %s", exc)
        intent_update = AgentState(intent="knowledge", complexity=30)  # type: ignore[call-arg]
    state.update(intent_update)  # type: ignore[arg-type]

    intent = state.get("intent") or "knowledge"
    complexity = state.get("complexity") or 0
    yield _sse_event("agent_step", {
        "agent": "intent_router",
        "intent": intent,
        "complexity": complexity,
        "version": version,
    })

    # ── Greeting 快路径 ─────────────────────────────────────────
    if intent == "greeting":
        from agents import run_greeting
        greet = await run_greeting(state)
        yield _sse_event("agent_step", {"agent": "greeting"})
        yield _sse_event("token", {"text": str(greet.get("answer") or "你好！")})
        yield _sse_event("done", {"citations": 0})
        return

    # ── 版本图路由 ────────────────────────────────────────────────
    is_complex = intent in _COMPLEX_INTENTS or complexity >= 60

    # V1 始终走 KnowledgeAgent（无复杂流）
    # V2 复杂流 → v2 图（含 risk_lite）
    # V3 复杂流 → 完整 supervisor 图（含 planner + critic + risk_review）
    if is_complex and version in {"v2", "v3"}:
        from agents.versions.v2 import build_v2
        graph = get_graph() if version == "v3" else build_v2()
        yield _sse_event("agent_step", {
            "agent": "planner" if version == "v3" else "risk_lite",
            "version": version,
        })

        thread_id = state.get("thread_id") or uuid.uuid4().hex
        config = {"configurable": {"thread_id": thread_id}}

        try:
            final_state = await graph.ainvoke(state, config) or {}
        except Exception as exc:
            logger.exception("graph.ainvoke failed: %s", exc)
            yield _sse_event("error", {"message": "处理失败，请稍后重试"})
            return

        plan = final_state.get("plan") or []
        if plan:
            yield _sse_event("agent_step", {"agent": "critic"})
            yield _sse_event("agent_step", {
                "agent": "plan_execute",
                "steps": len(plan),
            })

        # 中断：需要人工审核
        if final_state.get("needs_review"):
            risk_d = final_state.get("risk_decision") or {}
            yield _sse_event("agent_step", {
                "agent": "risk_review",
                "decision": risk_d.get("decision", "review"),
                "score": risk_d.get("fusion_score", 0),
            })
            yield _sse_event("interrupt", {
                "thread_id": thread_id,
                "reason": final_state.get("interrupt_reason") or "需要人工审核",
                "risk_decision": risk_d,
            })
            yield _sse_event("done", {"citations": 0, "interrupted": True})
            return

        # 正常完成：流式输出答案
        answer = final_state.get("answer") or "已为您处理完毕。"
        chunk_size = 8
        for i in range(0, len(answer), chunk_size):
            yield _sse_event("token", {"text": answer[i:i + chunk_size]})

        for cit in final_state.get("citations") or []:
            yield _sse_event("citation", cit)
        yield _sse_event("done", {"citations": len(final_state.get("citations") or [])})
        return

    # ── 默认：KnowledgeAgent 流式（v1/v2 全部；v3 简单意图）───
    yield _sse_event("agent_step", {"agent": "knowledge"})
    try:
        async for ev in stream_knowledge(state):
            yield _sse_event(ev.type, ev.data)
    except Exception as exc:
        logger.exception("knowledge stream failed: %s", exc)
        yield _sse_event("error", {"message": "知识检索异常，请稍后重试"})


@app.post("/api/v1/chat", dependencies=[require_perm("chat:send")])
async def chat_sse(req: ChatRequest):
    """SSE 流式聊天端点。

    返回 Content-Type: text/event-stream。事件类型见设计.md §5.3。
    """
    if not req.messages or req.messages[-1].role != "user":
        raise BusinessException(
            ErrorCode.BIZ_PARAM_INVALID, message="messages 末尾必须为 user 消息"
        )

    thread_id = req.thread_id or uuid.uuid4().hex
    tid = current_tenant_id()
    state = initial_state(
        messages=[m.model_dump() for m in req.messages],
        thread_id=thread_id,
        user_id=req.user_id,
        tenant_id=tid,
        version=req.version,
    )

    return StreamingResponse(
        _stream_chat(state),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 兼容 nginx：禁缓冲
            "X-Thread-Id": thread_id,
        },
    )


@app.get("/api/v1/admin/cost", dependencies=[require_perm("admin:cost")])
async def admin_cost(
    group_by: str = "model",
) -> dict[str, Any]:
    """成本汇总接口（W4）。按 model / agent / version / tenant 分组返回 token + 成本估算。

    数据源优先级：Langfuse API → RuntimeObservability 内存指标。
    """
    allowed_groups = {"model", "agent", "version", "tenant"}
    if group_by not in allowed_groups:
        raise BusinessException(
            ErrorCode.BIZ_PARAM_INVALID,
            message=f"group_by must be one of {allowed_groups}",
        )

    langfuse_data = None
    try:
        import os
        import httpx

        lf_host = os.getenv("LANGFUSE_HOST", "http://localhost:13000")
        lf_pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        lf_sk = os.getenv("LANGFUSE_SECRET_KEY", "")
        if lf_pk and lf_sk:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{lf_host}/api/public/metrics/daily",
                    auth=(lf_pk, lf_sk),
                )
                if resp.status_code == 200:
                    langfuse_data = resp.json()
    except Exception as exc:
        logger.debug("Langfuse metrics fetch failed: %s", exc)

    from tracing.otel_config import get_runtime_obs
    obs = get_runtime_obs()
    summary = obs.get_summary()

    cache_stats = {}
    try:
        from llm.semantic_cache import get_cache
        cache = get_cache()
        r = cache._get_client()
        if r:
            import json as _json
            raw_index = r.get("sem_cache_index")
            cache_stats["cached_entries"] = len(_json.loads(raw_index)) if raw_index else 0
        else:
            cache_stats["cached_entries"] = 0
        cache_stats["threshold"] = cache.threshold
        cache_stats["ttl_seconds"] = cache.ttl
    except Exception:
        cache_stats = {"cached_entries": 0, "note": "cache stats unavailable"}

    return {
        "group_by": group_by,
        "runtime_summary": summary,
        "langfuse": langfuse_data,
        "semantic_cache": cache_stats,
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "version": app.version}


# ---------- W5: 异步任务 ----------

class BatchReviewRequest(BaseModel):
    ticket_ids: list[str] = Field(..., min_length=1, max_length=500)


@app.post("/api/v1/tasks/batch_review", dependencies=[require_perm("task:batch_review")])
async def start_batch_review(req: BatchReviewRequest) -> dict[str, Any]:
    """启动批量风控审核任务，返回 task_id。Celery 不可用時同步 fallback。"""
    tid = current_tenant_id() or 1
    try:
        from tasks.batch_jobs import batch_review

        result = batch_review.delay(req.ticket_ids, tenant_id=tid)
        return {"task_id": result.id, "status": "queued", "total": len(req.ticket_ids), "mode": "celery"}
    except Exception as exc:
        logger.warning("batch_review celery dispatch failed, sync fallback: %s", exc)
        from tasks.batch_jobs import run_batch_review_sync

        sync_id = f"sync-{uuid.uuid4().hex[:12]}"

        async def _run() -> None:
            await asyncio.to_thread(
                run_batch_review_sync, req.ticket_ids, tid, sync_id,
            )

        asyncio.create_task(_run())
        return {
            "task_id": sync_id,
            "status": "running",
            "total": len(req.ticket_ids),
            "mode": "sync_fallback",
        }


@app.get("/api/v1/admin/capabilities", dependencies=[require_perm("admin:cost")])
async def admin_capabilities() -> dict[str, Any]:
    """能力矩陣探測：各子系統 code_exists / demo_ready。"""
    from api.demo_capabilities import probe_all

    return await probe_all()


@app.get("/api/v1/tasks/{task_id}/progress")
async def get_task_progress(task_id: str) -> dict[str, Any]:
    """查询任务进度。"""
    from tasks.progress import get_progress
    progress = get_progress(task_id)
    if progress is None:
        raise BusinessException(ErrorCode.BIZ_NOT_FOUND, message=f"task {task_id} not found")
    return progress


@app.websocket("/ws/tasks/{task_id}")
async def ws_task_progress(websocket: WebSocket, task_id: str):
    """WebSocket 实时推送任务进度。

    客户端连入后每秒轮询 Redis，进度变化时推送，任务终态后关闭连接。
    降级方案：客户端回退到 HTTP GET /api/v1/tasks/{id}/progress 轮询。
    """
    from starlette.websockets import WebSocketDisconnect
    from tasks.progress import get_progress as _get_progress

    await websocket.accept()
    try:
        last_pct = -1.0
        for _ in range(300):  # 最多 5 分钟
            progress = _get_progress(task_id)
            if progress is None:
                await websocket.send_json({"status": "unknown", "message": "任务不存在"})
                break
            pct = progress.get("pct", 0)
            if pct != last_pct:
                await websocket.send_json(progress)
                last_pct = pct
            if progress.get("status") in {"done", "failed"}:
                break
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("ws_task_progress error: %s", exc)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ---------- W5: 灰度版本管理 ----------

class RolloutWeights(BaseModel):
    v1: float = Field(ge=0.0, le=1.0, default=0.0)
    v2: float = Field(ge=0.0, le=1.0, default=0.0)
    v3: float = Field(ge=0.0, le=1.0, default=1.0)


@app.get("/api/v1/admin/rollout", dependencies=[require_perm("admin:rollout")])
async def get_rollout() -> dict[str, Any]:
    """查询当前灰度权重。"""
    from agents.rollout import get_weights
    return {"weights": get_weights()}


@app.put("/api/v1/admin/rollout", dependencies=[require_perm("admin:rollout")])
async def update_rollout(body: RolloutWeights) -> dict[str, Any]:
    """更新灰度权重（v1+v2+v3 自动归一化）。"""
    from agents.rollout import set_weights, get_weights
    set_weights({"v1": body.v1, "v2": body.v2, "v3": body.v3})
    return {"updated": True, "weights": get_weights()}


@app.get("/api/v1/admin/rollout/audit", dependencies=[require_perm("admin:rollout")])
async def get_rollout_audit(
    limit: int = 20, offset: int = 0,
) -> dict[str, Any]:
    """查询灰度变更审计日志（最新优先）。"""
    from agents.rollout import get_audit_log
    entries = get_audit_log(limit=limit, offset=offset)
    return {"total": len(entries), "entries": entries}


# ---------- W3: 人审 resume ----------

class ReviewAction(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|escalate)$")
    reviewer_note: str = Field(default="", max_length=500)


@app.post("/api/v1/review/{thread_id}/resume", dependencies=[require_perm("review:approve")])
async def review_resume(thread_id: str, body: ReviewAction) -> dict[str, Any]:
    """人审决策后恢复被中断的 graph。

    Approve → 继续执行后续步骤；Reject/Escalate → 终止并记录。
    """
    checkpointer = get_checkpointer()
    if checkpointer is None:
        raise BusinessException(
            ErrorCode.SYS_CONFIG_INVALID,
            message="checkpoint 未配置，无法 resume（需 PG_DSN_SYNC 或 APP_ENV=test）",
        )

    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    # 写入人审决策到 state
    risk_decision = {
        "action": body.action,
        "reviewer_note": body.reviewer_note,
        "thread_id": thread_id,
    }
    try:
        await graph.aupdate_state(
            config,
            {"risk_decision": risk_decision, "needs_review": False},
            as_node="risk_review",
        )
        if body.action == "approve":
            final_state = await graph.ainvoke(None, config)
            answer = (final_state or {}).get("answer") or "操作已完成。"
        else:
            answer = f"请求已{('拒绝' if body.action == 'reject' else '升级转人工')}。{body.reviewer_note}"
    except Exception as exc:
        logger.exception("resume failed for thread %s: %s", thread_id, exc)
        raise BusinessException(ErrorCode.SYS_INTERNAL_ERROR, message=f"resume 失败: {exc}") from exc

    return {
        "thread_id": thread_id,
        "action": body.action,
        "answer": answer,
    }


# ---------- W6: Auth endpoints ----------

class LoginRequest(BaseModel):
    username: str
    password: str
    tenant_id: int


class RefreshRequest(BaseModel):
    refresh_token: str


@app.post("/auth/login")
async def auth_login(body: LoginRequest) -> dict[str, Any]:
    """账号密码登录，返回 access_token + refresh_token。"""
    user = await authenticate_user(body.username, body.password, body.tenant_id)
    roles, perms = await get_user_roles_and_perms(user["id"], body.tenant_id)
    access = create_access_token(
        user_id=user["id"],
        tenant_id=body.tenant_id,
        roles=roles,
        permissions=perms,
    )
    refresh = create_refresh_token(user_id=user["id"], tenant_id=body.tenant_id)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "roles": roles,
        },
    }


@app.post("/auth/refresh")
async def auth_refresh(body: RefreshRequest) -> dict[str, Any]:
    """用 refresh_token 换新 access_token（refresh_token 本身不轮换）。"""
    payload = verify_token(body.refresh_token, expected_type="refresh")
    user_id = int(payload["sub"])
    tenant_id = int(payload["tid"])
    roles, perms = await get_user_roles_and_perms(user_id, tenant_id)
    access = create_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=roles,
        permissions=perms,
    )
    return {"access_token": access, "token_type": "bearer"}


@app.get("/auth/me")
async def auth_me(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """返回当前登录用户信息（从 token 解析，无 DB 查询）。"""
    return {
        "id": current_user.id,
        "tenant_id": current_user.tenant_id,
        "roles": current_user.roles,
        "permissions": current_user.permissions,
    }


@app.post("/auth/logout")
async def auth_logout(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """登出：吊销所有 refresh token，写审计日志。"""
    revoke_all_refresh_tokens(current_user.id)
    logger.info("user %d (tenant %d) logged out", current_user.id, current_user.tenant_id)
    return {"message": "已登出"}


# ---------- W6: 租户管理 ----------

class TenantCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)


@app.get("/api/v1/admin/tenants", dependencies=[require_perm("admin:tenant")])
async def list_tenants(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """列出所有租户（admin:tenant）— 跨租户操作，记录审计。"""
    await _audit_cross_tenant(current_user.id, "tenant:list")
    try:
        from db.models import Tenant
        from db.session import async_session
        from sqlalchemy import select

        async with async_session() as session:
            result = await session.execute(select(Tenant).order_by(Tenant.id))
            tenants = result.scalars().all()
            return {
                "tenants": [
                    {"id": t.id, "code": t.code, "name": t.name, "created_at": str(t.created_at)}
                    for t in tenants
                ]
            }
    except Exception as exc:
        logger.warning("list_tenants failed: %s", exc)
        return {"tenants": [], "note": "DB unavailable, use bootstrap.py to initialize"}


@app.post("/api/v1/admin/tenants", dependencies=[require_perm("admin:tenant")])
async def create_tenant(
    body: TenantCreate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """创建新租户（admin:tenant）— 跨租户操作，记录审计。"""
    try:
        from db.models import Tenant
        from db.session import async_session
        from sqlalchemy import select

        async with async_session() as session:
            existing = await session.execute(
                select(Tenant).where(Tenant.code == body.code)
            )
            if existing.scalar_one_or_none():
                raise BusinessException(
                    ErrorCode.BIZ_PARAM_INVALID, message=f"租户 code '{body.code}' 已存在"
                )
            t = Tenant(code=body.code, name=body.name)
            session.add(t)
            await session.commit()
            await _audit_cross_tenant(
                current_user.id, "tenant:create", target_tenant_id=t.id,
                payload={"code": body.code, "name": body.name},
            )
            return {"id": t.id, "code": t.code, "name": t.name}
    except BusinessException:
        raise
    except Exception as exc:
        logger.error("create_tenant failed: %s", exc)
        raise BusinessException(ErrorCode.SYS_INTERNAL_ERROR, message="创建租户失败") from exc


# ---------- W9: Orders CRUD ----------

@app.get("/api/v1/orders", dependencies=[require_perm("order:read")])
async def list_orders(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """订单列表。customer 只看自己的，agent/admin 看租户全部。"""
    from db.models import Order
    from db.session import async_session
    from sqlalchemy import select, func

    page = max(1, page)
    page_size = min(100, max(1, page_size))

    async with async_session() as session:
        count_q = select(func.count(Order.id))
        query = select(Order).order_by(Order.created_at.desc())

        if "customer" in current_user.roles and "admin" not in current_user.roles:
            count_q = count_q.where(Order.user_id == current_user.id)
            query = query.where(Order.user_id == current_user.id)
        if status:
            count_q = count_q.where(Order.status == status)
            query = query.where(Order.status == status)

        total = (await session.execute(count_q)).scalar() or 0
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(query)
        orders = result.scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "orders": [
                {
                    "id": o.id,
                    "order_no": o.order_no,
                    "user_id": o.user_id,
                    "status": o.status,
                    "total_amount": o.total_amount,
                    "item_count": o.item_count,
                    "product_name": o.product_name,
                    "shipping_address": o.shipping_address,
                    "delivered_at": str(o.delivered_at) if o.delivered_at else None,
                    "created_at": str(o.created_at),
                }
                for o in orders
            ],
        }


@app.get("/api/v1/orders/{order_no}", dependencies=[require_perm("order:read")])
async def get_order(order_no: str) -> dict[str, Any]:
    """订单详情（含明细）。"""
    from db.models import Order, OrderItem
    from db.session import async_session
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(select(Order).where(Order.order_no == order_no))
        order = result.scalar_one_or_none()
        if not order:
            raise BusinessException(ErrorCode.BIZ_ORDER_NOT_FOUND, message=f"订单 {order_no} 不存在")

        items_result = await session.execute(
            select(OrderItem).where(OrderItem.order_id == order.id)
        )
        items = items_result.scalars().all()

        return {
            "id": order.id,
            "order_no": order.order_no,
            "user_id": order.user_id,
            "status": order.status,
            "total_amount": order.total_amount,
            "item_count": order.item_count,
            "product_name": order.product_name,
            "shipping_address": order.shipping_address,
            "delivered_at": str(order.delivered_at) if order.delivered_at else None,
            "created_at": str(order.created_at),
            "items": [
                {
                    "id": item.id,
                    "sku": item.sku,
                    "name": item.name,
                    "price": item.price,
                    "quantity": item.quantity,
                }
                for item in items
            ],
        }


# ---------- W9: Tickets CRUD ----------

@app.get("/api/v1/tickets", dependencies=[require_perm("ticket:read")])
async def list_tickets(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    status: str | None = None,
    ticket_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """工单列表。customer 只看自己的，agent/admin 看租户全部。"""
    from db.models import Ticket
    from db.session import async_session
    from sqlalchemy import select, func

    page = max(1, page)
    page_size = min(100, max(1, page_size))

    async with async_session() as session:
        count_q = select(func.count(Ticket.id))
        query = select(Ticket).order_by(Ticket.created_at.desc())

        if "customer" in current_user.roles and "admin" not in current_user.roles:
            count_q = count_q.where(Ticket.user_id == current_user.id)
            query = query.where(Ticket.user_id == current_user.id)
        if status:
            count_q = count_q.where(Ticket.status == status)
            query = query.where(Ticket.status == status)
        if ticket_type:
            count_q = count_q.where(Ticket.type == ticket_type)
            query = query.where(Ticket.type == ticket_type)

        total = (await session.execute(count_q)).scalar() or 0
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(query)
        tickets = result.scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "tickets": [
                {
                    "id": t.id,
                    "ticket_no": t.ticket_no,
                    "order_id": t.order_id,
                    "user_id": t.user_id,
                    "type": t.type,
                    "status": t.status,
                    "amount": t.amount,
                    "reason": t.reason,
                    "assigned_agent_id": t.assigned_agent_id,
                    "risk_score": t.risk_score,
                    "risk_decision": t.risk_decision,
                    "closed_at": str(t.closed_at) if t.closed_at else None,
                    "created_at": str(t.created_at),
                }
                for t in tickets
            ],
        }


@app.get("/api/v1/tickets/{ticket_no}", dependencies=[require_perm("ticket:read")])
async def get_ticket(ticket_no: str) -> dict[str, Any]:
    """工单详情。"""
    from db.models import Ticket
    from db.session import async_session
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(select(Ticket).where(Ticket.ticket_no == ticket_no))
        ticket = result.scalar_one_or_none()
        if not ticket:
            raise BusinessException(ErrorCode.BIZ_TICKET_NOT_FOUND, message=f"工单 {ticket_no} 不存在")

        return {
            "id": ticket.id,
            "ticket_no": ticket.ticket_no,
            "order_id": ticket.order_id,
            "user_id": ticket.user_id,
            "type": ticket.type,
            "status": ticket.status,
            "amount": ticket.amount,
            "reason": ticket.reason,
            "assigned_agent_id": ticket.assigned_agent_id,
            "risk_score": ticket.risk_score,
            "risk_decision": ticket.risk_decision,
            "closed_at": str(ticket.closed_at) if ticket.closed_at else None,
            "created_at": str(ticket.created_at),
        }


class TicketAction(BaseModel):
    action: str = Field(..., pattern="^(accept|reject|escalate|close)$")
    note: str = Field(default="", max_length=500)


_TICKET_TRANSITIONS = {
    "accept": ("assigned", "processing"),
    "reject": ("assigned", "rejected"),
    "escalate": ("assigned", "escalated"),
    "close": ("processing", "resolved"),
}


@app.post("/api/v1/tickets/{ticket_no}/actions", dependencies=[require_perm("ticket:update")])
async def ticket_action(
    ticket_no: str,
    body: TicketAction,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """工单操作：accept / reject / escalate / close。"""
    from db.models import Ticket
    from db.session import async_session
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(select(Ticket).where(Ticket.ticket_no == ticket_no))
        ticket = result.scalar_one_or_none()
        if not ticket:
            raise BusinessException(ErrorCode.BIZ_TICKET_NOT_FOUND, message=f"工单 {ticket_no} 不存在")

        valid_from, new_status = _TICKET_TRANSITIONS[body.action]
        if ticket.status != valid_from and body.action != "close":
            # close 允许从任意活跃状态
            if ticket.status in ("resolved", "rejected", "closed"):
                raise BusinessException(
                    ErrorCode.BIZ_TICKET_STATE_INVALID,
                    message=f"工单当前状态 '{ticket.status}' 不允许执行 '{body.action}'",
                )

        ticket.status = new_status
        if body.action == "accept":
            ticket.assigned_agent_id = current_user.id
        if new_status in ("resolved", "rejected"):
            from datetime import datetime as _dt
            ticket.closed_at = _dt.utcnow()

        await session.commit()

        return {
            "ticket_no": ticket.ticket_no,
            "status": ticket.status,
            "action": body.action,
        }


# ---------- W9: Refunds CRUD ----------

class RefundCreate(BaseModel):
    order_no: str
    reason: str = Field(..., min_length=1, max_length=32)
    description: str = Field(default="", max_length=1000)


@app.post("/api/v1/refunds", dependencies=[require_perm("refund:apply")])
async def create_refund(
    body: RefundCreate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """提交退款申请。校验订单状态 + 防重复，创建 refund + ticket 记录。"""
    import uuid as _uuid
    from db.models import Order, Refund, Ticket
    from db.session import async_session
    from sqlalchemy import select

    async with async_session() as session:
        # 查找订单
        order_result = await session.execute(
            select(Order).where(Order.order_no == body.order_no)
        )
        order = order_result.scalar_one_or_none()
        if not order:
            raise BusinessException(ErrorCode.BIZ_ORDER_NOT_FOUND, message=f"订单 {body.order_no} 不存在")

        if order.status not in ("delivered", "shipped"):
            raise BusinessException(
                ErrorCode.BIZ_ORDER_NOT_ELIGIBLE,
                message=f"订单状态 '{order.status}' 不支持退款",
            )

        # 防重复
        dup_result = await session.execute(
            select(Refund).where(
                Refund.order_id == order.id,
                Refund.status.in_(["applied", "approved", "refunding"]),
            )
        )
        if dup_result.scalar_one_or_none():
            raise BusinessException(ErrorCode.BIZ_REFUND_DUPLICATE, message="该订单已有进行中的退款申请")

        # 创建工单
        ticket_no = f"TK{_uuid.uuid4().hex[:10].upper()}"
        ticket = Ticket(
            ticket_no=ticket_no,
            order_id=order.id,
            user_id=current_user.id,
            type="refund",
            status="open",
            amount=order.total_amount,
            reason=body.reason,
        )
        session.add(ticket)

        # 创建退款记录
        refund_no = f"RF{_uuid.uuid4().hex[:10].upper()}"
        refund = Refund(
            refund_no=refund_no,
            order_id=order.id,
            user_id=current_user.id,
            amount=order.total_amount,
            reason=body.reason,
            description=body.description,
            status="applied",
        )
        session.add(refund)
        await session.commit()

        return {
            "refund_no": refund.refund_no,
            "ticket_no": ticket.ticket_no,
            "amount": refund.amount,
            "status": refund.status,
        }


@app.get("/api/v1/refunds", dependencies=[require_perm("refund:read")])
async def list_refunds(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """退款列表。customer 只看自己的，agent/admin 看租户全部。"""
    from db.models import Refund
    from db.session import async_session
    from sqlalchemy import select, func

    page = max(1, page)
    page_size = min(100, max(1, page_size))

    async with async_session() as session:
        count_q = select(func.count(Refund.id))
        query = select(Refund).order_by(Refund.created_at.desc())

        if "customer" in current_user.roles and "admin" not in current_user.roles:
            count_q = count_q.where(Refund.user_id == current_user.id)
            query = query.where(Refund.user_id == current_user.id)
        if status:
            count_q = count_q.where(Refund.status == status)
            query = query.where(Refund.status == status)

        total = (await session.execute(count_q)).scalar() or 0
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(query)
        refunds = result.scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "refunds": [
                {
                    "id": r.id,
                    "refund_no": r.refund_no,
                    "order_id": r.order_id,
                    "ticket_id": r.ticket_id,
                    "user_id": r.user_id,
                    "amount": r.amount,
                    "reason": r.reason,
                    "status": r.status,
                    "risk_score": r.risk_score,
                    "risk_decision": r.risk_decision,
                    "resolved_at": str(r.resolved_at) if r.resolved_at else None,
                    "created_at": str(r.created_at),
                }
                for r in refunds
            ],
        }


@app.get("/api/v1/refunds/{refund_no}", dependencies=[require_perm("refund:read")])
async def get_refund(refund_no: str) -> dict[str, Any]:
    """退款详情（含风险决策）。"""
    from db.models import Refund
    from db.session import async_session
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(select(Refund).where(Refund.refund_no == refund_no))
        refund = result.scalar_one_or_none()
        if not refund:
            raise BusinessException(ErrorCode.BIZ_NOT_FOUND, message=f"退款 {refund_no} 不存在")

        return {
            "id": refund.id,
            "refund_no": refund.refund_no,
            "order_id": refund.order_id,
            "ticket_id": refund.ticket_id,
            "user_id": refund.user_id,
            "amount": refund.amount,
            "reason": refund.reason,
            "description": refund.description,
            "status": refund.status,
            "risk_score": refund.risk_score,
            "risk_decision": refund.risk_decision,
            "resolved_at": str(refund.resolved_at) if refund.resolved_at else None,
            "created_at": str(refund.created_at),
        }


class RefundReviewAction(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|escalate)$")
    note: str = Field(default="", max_length=500)


@app.post("/api/v1/refunds/{refund_no}/review", dependencies=[require_perm("review:approve")])
async def review_refund(
    refund_no: str,
    body: RefundReviewAction,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """退款审核：approve / reject / escalate。同时更新关联工单状态。"""
    from db.models import Refund, Ticket
    from db.session import async_session
    from sqlalchemy import select
    from datetime import datetime as _dt

    async with async_session() as session:
        result = await session.execute(select(Refund).where(Refund.refund_no == refund_no))
        refund = result.scalar_one_or_none()
        if not refund:
            raise BusinessException(ErrorCode.BIZ_NOT_FOUND, message=f"退款 {refund_no} 不存在")

        if refund.status in ("done", "denied"):
            raise BusinessException(ErrorCode.BIZ_CONFLICT, message=f"退款已终态: {refund.status}")

        if body.action == "approve":
            refund.status = "approved"
            refund.risk_decision = "pass"
        elif body.action == "reject":
            refund.status = "denied"
            refund.risk_decision = "reject"
        else:
            refund.status = "risk_pending"
            refund.risk_decision = "escalate"

        refund.resolved_at = _dt.utcnow()

        # 同步更新关联工单
        if refund.ticket_id:
            ticket_res = await session.execute(
                select(Ticket).where(Ticket.id == refund.ticket_id)
            )
            ticket = ticket_res.scalar_one_or_none()
            if ticket:
                if body.action == "approve":
                    ticket.status = "resolved"
                    ticket.closed_at = _dt.utcnow()
                elif body.action == "reject":
                    ticket.status = "rejected"
                    ticket.closed_at = _dt.utcnow()
                else:
                    ticket.status = "escalated"

        await session.commit()

        return {
            "refund_no": refund.refund_no,
            "status": refund.status,
            "action": body.action,
        }


# ---------- W9: Threads / Messages ----------

@app.get("/api/v1/threads", dependencies=[require_perm("chat:send")])
async def list_threads(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """会话列表（按 thread_id 分组，返回最新消息摘要）。"""
    from db.models import Message
    from db.session import async_session
    from sqlalchemy import select, func

    async with async_session() as session:
        # 按 thread_id 分组，取最新一条消息
        subq = (
            select(
                Message.thread_id,
                func.max(Message.id).label("last_id"),
            )
            .group_by(Message.thread_id)
            .subquery()
        )
        result = await session.execute(
            select(Message)
            .join(subq, Message.id == subq.c.last_id)
            .order_by(Message.created_at.desc())
            .limit(50)
        )
        messages = result.scalars().all()

        return {
            "threads": [
                {
                    "thread_id": m.thread_id,
                    "last_message": m.content[:100],
                    "role": m.role,
                    "created_at": str(m.created_at),
                }
                for m in messages
            ],
        }


@app.get("/api/v1/threads/{thread_id}/messages", dependencies=[require_perm("chat:send")])
async def get_thread_messages(
    thread_id: str,
    limit: int = 50,
) -> dict[str, Any]:
    """会话消息历史。"""
    from db.models import Message
    from db.session import async_session
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(
            select(Message)
            .where(Message.thread_id == thread_id)
            .order_by(Message.created_at.asc())
            .limit(min(200, max(1, limit)))
        )
        messages = result.scalars().all()

        return {
            "thread_id": thread_id,
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "created_at": str(m.created_at),
                }
                for m in messages
            ],
        }


# ---------- W9: Review queue ----------

@app.get("/api/v1/review/queue", dependencies=[require_perm("review:approve")])
async def review_queue(
    status: str = "open",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """待审队列：查询 risk_score >= 60 或 status = waiting_review 的工单。"""
    from db.models import Ticket
    from db.session import async_session
    from sqlalchemy import select, func, or_

    page = max(1, page)
    page_size = min(100, max(1, page_size))

    async with async_session() as session:
        filter_cond = or_(
            Ticket.status == "waiting_review",
            Ticket.risk_score >= 60,
        )
        count_q = select(func.count(Ticket.id)).where(filter_cond)
        query = (
            select(Ticket)
            .where(filter_cond)
            .order_by(Ticket.created_at.desc())
        )

        total = (await session.execute(count_q)).scalar() or 0
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(query)
        tickets = result.scalars().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "tickets": [
                {
                    "id": t.id,
                    "ticket_no": t.ticket_no,
                    "type": t.type,
                    "amount": t.amount,
                    "reason": t.reason,
                    "risk_score": t.risk_score,
                    "risk_decision": t.risk_decision,
                    "status": t.status,
                    "created_at": str(t.created_at),
                }
                for t in tickets
            ],
        }


__all__ = ["app"]
