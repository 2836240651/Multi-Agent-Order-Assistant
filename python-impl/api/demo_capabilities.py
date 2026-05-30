"""api/demo_capabilities.py：能力矩陣自動探測（管理端演示面板用）。"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any

logger = logging.getLogger(__name__)


async def probe_all() -> dict[str, Any]:
    """並行探測各子系統，返回 code_exists + demo_ready + detail。"""
    names = [
        "rag",
        "agents",
        "eval",
        "langfuse",
        "risk",
        "llm_cache",
        "celery",
        "rollout",
        "auth",
        "mcp",
        "frontend",
    ]
    results = await asyncio.gather(
        _probe_rag(),
        _probe_agents(),
        _probe_eval(),
        _probe_langfuse(),
        _probe_risk(),
        _probe_llm_cache(),
        _probe_celery(),
        _probe_rollout(),
        _probe_auth(),
        _probe_mcp(),
        _probe_frontend(),
        return_exceptions=True,
    )
    caps: dict[str, Any] = {}
    for name, res in zip(names, results):
        if isinstance(res, Exception):
            caps[name] = {
                "code_exists": True,
                "demo_ready": False,
                "detail": str(res)[:120],
            }
        else:
            caps[name] = res
    caps["summary"] = {
        "total": len(caps),
        "demo_ready": sum(1 for v in caps.values() if isinstance(v, dict) and v.get("demo_ready")),
    }
    return caps


async def _probe_rag() -> dict[str, Any]:
    from rag.bootstrap import ensure_kb_indexed
    from rag import retriever

    stats = ensure_kb_indexed()
    chunks = stats.get("chunks") or 0
    hits = retriever.hybrid_retrieve(
        query="无理由退货几天", tenant_id=1, top_k_vector=5, top_k_bm25=5,
    )
    demo_ready = chunks > 0 and len(hits) > 0
    return {
        "code_exists": True,
        "demo_ready": demo_ready,
        "detail": f"chunks={chunks}, retrieve_hits={len(hits)}",
        "stats": stats,
    }


async def _probe_agents() -> dict[str, Any]:
    from agents import get_graph
    from agents.versions.v2 import build_v2

    g3 = get_graph()
    g2 = build_v2()
    demo_ready = g3 is not None and g2 is not None
    return {
        "code_exists": True,
        "demo_ready": demo_ready,
        "detail": "v2/v3 LangGraph 已編譯",
    }


async def _probe_eval() -> dict[str, Any]:
    from pathlib import Path

    ds = Path(__file__).resolve().parents[1] / "eval" / "datasets"
    files = list(ds.glob("*.jsonl")) if ds.is_dir() else []
    return {
        "code_exists": True,
        "demo_ready": len(files) >= 4,
        "detail": f"datasets={len(files)}",
    }


async def _probe_langfuse() -> dict[str, Any]:
    host = os.getenv("LANGFUSE_HOST", "http://localhost:13000")
    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    reachable = False
    if pk:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{host}/api/public/health")
                reachable = r.status_code < 500
        except Exception as exc:
            logger.debug("langfuse probe: %s", exc)

    from tracing.otel_config import get_runtime_obs

    obs_ok = get_runtime_obs() is not None
    demo_ready = obs_ok or reachable
    return {
        "code_exists": True,
        "demo_ready": demo_ready,
        "detail": f"langfuse_reachable={reachable}, runtime_obs={obs_ok}",
        "langfuse_host": host,
    }


async def _probe_risk() -> dict[str, Any]:
    from risk import evaluate

    high = await evaluate(
        {"amount": 999.0, "reason": "质量问题", "description": "退款999元"},
        tenant_id=1,
    )
    low = await evaluate(
        {"amount": 50.0, "reason": "尺码不合", "description": "退款50元"},
        tenant_id=1,
    )
    demo_ready = high.decision in {"review", "reject"} and low.decision == "pass"
    return {
        "code_exists": True,
        "demo_ready": demo_ready,
        "detail": f"high={high.decision}({high.fusion_score:.0f}), low={low.decision}",
    }


async def _probe_llm_cache() -> dict[str, Any]:
    from llm.semantic_cache import get_cache
    from llm.router import call_llm

    cache = get_cache()
    q = f"demo_cache_probe_{uuid.uuid4().hex[:8]}"
    await cache.set(q, "缓存探针答案")
    hit = await cache.get(q)
    result = await call_llm(
        profile="medium",
        messages=[{"role": "user", "content": "ping"}],
        stream=False,
    )
    llm_ok = bool(getattr(result, "text", ""))
    return {
        "code_exists": True,
        "demo_ready": llm_ok and hit is not None,
        "detail": f"cache_hit={hit is not None}, llm_ok={llm_ok}",
    }


async def _probe_celery() -> dict[str, Any]:
    broker = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", ""))
    celery_ok = False
    try:
        from tasks.celery_app import app as celery_app

        celery_ok = celery_app.control.inspect(timeout=0.5).ping() is not None
    except Exception:
        celery_ok = False

    from tasks.progress import update_progress, get_progress

    tid = f"probe-{uuid.uuid4().hex[:8]}"
    update_progress(tid, status="done", done=1, total=1, message="probe")
    prog = get_progress(tid)
    progress_ok = prog is not None and prog.get("status") == "done"
    return {
        "code_exists": True,
        "demo_ready": progress_ok,
        "detail": f"celery_workers={celery_ok}, progress_store={progress_ok}",
        "sync_fallback": not celery_ok,
    }


async def _probe_rollout() -> dict[str, Any]:
    from agents.rollout import decide, get_weights

    w = get_weights()
    v1 = decide(version_hint="v1", user_id=1, tenant_id=1)
    v3 = decide(version_hint="v3", user_id=99999, tenant_id=1)
    demo_ready = v1 == "v1" and v3 in {"v1", "v2", "v3"}
    return {
        "code_exists": True,
        "demo_ready": demo_ready,
        "detail": f"weights={w}, sample_v1={v1}, sample_v3={v3}",
    }


async def _probe_auth() -> dict[str, Any]:
    from auth.jwt import create_access_token, verify_token

    tok = create_access_token(
        user_id=1,
        tenant_id=1,
        roles=["admin"],
        permissions=["admin:cost"],
    )
    payload = verify_token(tok, expected_type="access")
    demo_ready = str(payload.get("sub")) == "1"
    return {
        "code_exists": True,
        "demo_ready": demo_ready,
        "detail": "JWT 簽發/校驗正常",
    }


async def _probe_mcp() -> dict[str, Any]:
    from pathlib import Path

    mcp_path = Path(__file__).resolve().parents[1] / "mcp_tools" / "mcp_server.py"
    exists = mcp_path.is_file()
    return {
        "code_exists": exists,
        "demo_ready": exists,
        "detail": str(mcp_path.name) if exists else "mcp_server 缺失",
    }


async def _probe_frontend() -> dict[str, Any]:
    from pathlib import Path

    views = Path(__file__).resolve().parents[2] / "frontend" / "src" / "views"
    required = [
        "ChatView.vue",
        "agent/ConversationView.vue",
        "agent/SessionInboxView.vue",
        "risk/ReviewQueueView.vue",
        "admin/AdminDashboardView.vue",
    ]
    missing = [v for v in required if not (views / v).exists()]
    return {
        "code_exists": len(missing) == 0,
        "demo_ready": len(missing) == 0,
        "detail": "四角色視圖齊全" if not missing else f"缺少 {missing}",
    }


__all__ = ["probe_all"]
