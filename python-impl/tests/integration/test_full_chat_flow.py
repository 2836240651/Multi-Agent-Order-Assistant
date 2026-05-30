"""tests/integration/test_full_chat_flow.py：完整 chat 流程集成测试。

覆盖：
- SSE _stream_chat 路由逻辑（版本选择、意图分发）
- v3 复杂意图 → 全图调用 → 正常完成 / interrupt
- 版本路由（rollout decide）
- dead_letter 模块基本行为
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.state import AgentState, initial_state


# ── 辅助 ─────────────────────────────────────────────────────

def _parse_sse(raw: str) -> list[dict]:
    """把 SSE 文本解析为 [{event, data}] 列表。"""
    events = []
    for frame in raw.strip().split("\n\n"):
        if not frame.strip():
            continue
        event, data = "message", ""
        for line in frame.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
        if data:
            try:
                events.append({"event": event, "data": json.loads(data)})
            except json.JSONDecodeError:
                events.append({"event": event, "data": data})
    return events


async def _collect_stream(gen) -> list[dict]:
    chunks = []
    async for chunk in gen:
        chunks.append(chunk)
    return _parse_sse("".join(chunks))


def _make_state(**kwargs) -> AgentState:
    base = initial_state(
        messages=[{"role": "user", "content": kwargs.pop("content", "你好")}],
        thread_id=kwargs.pop("thread_id", "test-thread-001"),
        user_id=kwargs.pop("user_id", 1),
        tenant_id=kwargs.pop("tenant_id", 1),
        version=kwargs.pop("version", "v3"),
    )
    base.update(kwargs)  # type: ignore[arg-type]
    return base


# ── rollout.decide 测试 ───────────────────────────────────────

def test_rollout_decide_hint_v3():
    from agents.rollout import decide
    assert decide(version_hint="v3") == "v3"


def test_rollout_decide_hint_v1():
    from agents.rollout import decide
    assert decide(version_hint="v1") == "v1"


def test_rollout_decide_hint_v2():
    from agents.rollout import decide
    assert decide(version_hint="v2") == "v2"


def test_rollout_set_and_get_weights():
    from agents.rollout import set_weights, get_weights
    # Redis 不可用时退化到内存默认值，不应 raise
    try:
        set_weights({"v1": 0.0, "v2": 0.3, "v3": 0.7})
    except Exception:
        pass  # Redis 未启动，跳过写入
    w = get_weights()
    assert set(w.keys()) == {"v1", "v2", "v3"}
    total = sum(w.values())
    assert abs(total - 1.0) < 0.01 or total == 0.0  # 归一化或未写入


# ── _stream_chat 路由测试 ─────────────────────────────────────

@pytest.mark.asyncio
async def test_stream_chat_greeting():
    """greeting 意图 → 快路径，不调用 graph。"""
    from api.main import _stream_chat

    state = _make_state(content="你好", version="v3")

    mock_greet = AsyncMock(return_value={"answer": "您好！有什么可以帮您？"})
    mock_intent = AsyncMock(return_value=AgentState(intent="greeting", complexity=5))  # type: ignore[call-arg]

    with (
        patch("api.main.run_intent_router", mock_intent),
        patch("agents.greeting_handler.run_greeting", mock_greet),
        patch("agents.supervisor.run_greeting", mock_greet),
        # rollout：强制 v3
        patch("agents.rollout.get_weights", return_value={"v1": 0.0, "v2": 0.0, "v3": 1.0}),
    ):
        events = await _collect_stream(_stream_chat(state))

    event_types = [e["event"] for e in events]
    assert "start" in event_types
    assert "agent_step" in event_types
    assert "token" in event_types
    assert "done" in event_types
    assert "error" not in event_types

    # 确认 agent_step 包含 intent_router
    intent_steps = [e for e in events if e["event"] == "agent_step" and e["data"].get("agent") == "intent_router"]
    assert len(intent_steps) == 1
    assert intent_steps[0]["data"]["intent"] == "greeting"


@pytest.mark.asyncio
async def test_stream_chat_knowledge_simple():
    """简单知识意图 → stream_knowledge，不走 graph。"""
    from api.main import _stream_chat

    state = _make_state(content="7天无理由退货政策是什么", version="v3")

    async def _mock_stream(s):
        from rag.answer_generator import AnswerEvent
        yield AnswerEvent(type="token", data={"text": "根据政策，"})
        yield AnswerEvent(type="token", data={"text": "7天内可退。"})
        yield AnswerEvent(type="done", data={"citations": 0})

    mock_intent = AsyncMock(return_value=AgentState(intent="knowledge", complexity=20))  # type: ignore[call-arg]

    with (
        patch("api.main.run_intent_router", mock_intent),
        patch("api.main.stream_knowledge", _mock_stream),
        patch("agents.rollout.get_weights", return_value={"v1": 0.0, "v2": 0.0, "v3": 1.0}),
    ):
        events = await _collect_stream(_stream_chat(state))

    event_types = [e["event"] for e in events]
    assert "start" in event_types
    assert "token" in event_types
    # knowledge 路径，没有 planner agent_step
    planner_steps = [e for e in events if e["event"] == "agent_step" and e["data"].get("agent") == "planner"]
    assert len(planner_steps) == 0


@pytest.mark.asyncio
async def test_stream_chat_v3_complex_normal_completion():
    """v3 退款意图 → 完整图执行 → 正常完成（无中断）。"""
    from api.main import _stream_chat

    state = _make_state(content="我要退款，订单号 ORD-001", version="v3")

    mock_intent = AsyncMock(return_value=AgentState(intent="refund", complexity=70))  # type: ignore[call-arg]
    mock_final_state = {
        "answer": "退款申请已提交，金额 ¥99，预计 3-5 个工作日到账。",
        "citations": [],
        "plan": [{"step": 1, "action": "create_refund", "description": "创建退款"}],
        "needs_review": False,
    }
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value=mock_final_state)

    with (
        patch("api.main.run_intent_router", mock_intent),
        patch("api.main.get_graph", return_value=mock_graph),
        patch("agents.rollout.get_weights", return_value={"v1": 0.0, "v2": 0.0, "v3": 1.0}),
    ):
        events = await _collect_stream(_stream_chat(state))

    event_types = [e["event"] for e in events]
    assert "start" in event_types
    assert "token" in event_types
    assert "done" in event_types
    assert "interrupt" not in event_types

    # 确认有 planner agent_step
    planner_steps = [e for e in events if e["event"] == "agent_step" and e["data"].get("agent") == "planner"]
    assert len(planner_steps) == 1

    # 确认 done 不带 interrupted
    done_events = [e for e in events if e["event"] == "done"]
    assert done_events[-1]["data"].get("interrupted") is not True


@pytest.mark.asyncio
async def test_stream_chat_v3_complex_interrupt():
    """v3 高风险退款 → 图执行 → needs_review=True → 发 interrupt 事件。"""
    from api.main import _stream_chat

    state = _make_state(content="我要退款 9999 元", version="v3")

    mock_intent = AsyncMock(return_value=AgentState(intent="refund", complexity=80))  # type: ignore[call-arg]
    mock_final_state = {
        "answer": None,
        "citations": [],
        "plan": [{"step": 1, "action": "escalate", "description": "金额超阈值"}],
        "needs_review": True,
        "interrupt_reason": "退款金额超阈值，需人工审核",
        "risk_decision": {"decision": "review", "fusion_score": 75.0, "explanation": "金额超规则阈值"},
    }
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value=mock_final_state)

    with (
        patch("api.main.run_intent_router", mock_intent),
        patch("api.main.get_graph", return_value=mock_graph),
        patch("agents.rollout.get_weights", return_value={"v1": 0.0, "v2": 0.0, "v3": 1.0}),
    ):
        events = await _collect_stream(_stream_chat(state))

    event_types = [e["event"] for e in events]
    assert "interrupt" in event_types
    assert "done" in event_types

    interrupt_ev = next(e for e in events if e["event"] == "interrupt")
    assert interrupt_ev["data"]["reason"] == "退款金额超阈值，需人工审核"
    assert "thread_id" in interrupt_ev["data"]
    assert "risk_decision" in interrupt_ev["data"]

    done_ev = next(e for e in events if e["event"] == "done")
    assert done_ev["data"].get("interrupted") is True


@pytest.mark.asyncio
async def test_stream_chat_v1_complex_goes_to_knowledge():
    """v1 版本遇到复杂意图 → 仍走 knowledge，不用 graph。"""
    from api.main import _stream_chat

    state = _make_state(content="我要退款", version="v1")

    async def _mock_stream(s):
        from rag.answer_generator import AnswerEvent
        yield AnswerEvent(type="token", data={"text": "v1 知识回答"})
        yield AnswerEvent(type="done", data={"citations": 0})

    mock_intent = AsyncMock(return_value=AgentState(intent="refund", complexity=70))  # type: ignore[call-arg]

    with (
        patch("api.main.run_intent_router", mock_intent),
        patch("api.main.stream_knowledge", _mock_stream),
        patch("agents.rollout.get_weights", return_value={"v1": 1.0, "v2": 0.0, "v3": 0.0}),
    ):
        events = await _collect_stream(_stream_chat(state))

    planner_steps = [e for e in events if e["event"] == "agent_step" and e["data"].get("agent") == "planner"]
    assert len(planner_steps) == 0

    token_texts = "".join(e["data"].get("text", "") for e in events if e["event"] == "token")
    assert "v1" in token_texts


@pytest.mark.asyncio
async def test_stream_chat_graph_error_yields_error_event():
    """graph.ainvoke 抛异常 → 产出 error SSE 事件。"""
    from api.main import _stream_chat

    state = _make_state(content="我要退款", version="v3")

    mock_intent = AsyncMock(return_value=AgentState(intent="refund", complexity=70))  # type: ignore[call-arg]
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("模拟图崩溃"))

    with (
        patch("api.main.run_intent_router", mock_intent),
        patch("api.main.get_graph", return_value=mock_graph),
        patch("agents.rollout.get_weights", return_value={"v1": 0.0, "v2": 0.0, "v3": 1.0}),
    ):
        events = await _collect_stream(_stream_chat(state))

    assert any(e["event"] == "error" for e in events)


# ── dead_letter 测试 ──────────────────────────────────────────

def test_dead_letter_push_no_redis():
    """无 Redis 时 push 不 raise，仅记录日志。"""
    from tasks.dead_letter import push_dead_letter
    import os
    old = os.environ.pop("REDIS_URL", None)
    try:
        push_dead_letter("task-001", "tasks.test", [], {}, "error msg", retries=3)
    except Exception as exc:
        pytest.fail(f"push_dead_letter raised unexpectedly: {exc}")
    finally:
        if old is not None:
            os.environ["REDIS_URL"] = old


def test_dead_letter_list_no_redis():
    """无 Redis 时 list_dead 返回空列表。"""
    from tasks.dead_letter import list_dead
    import os
    old = os.environ.pop("REDIS_URL", None)
    try:
        result = list_dead()
        assert result == []
    finally:
        if old is not None:
            os.environ["REDIS_URL"] = old


def test_dead_letter_requeue_missing():
    """requeue 不存在的 task_id 返回 False。"""
    from tasks.dead_letter import requeue_dead
    result = requeue_dead("non-existent-task-id-xyz")
    assert result is False


def test_dead_letter_dlq_size_no_redis():
    """无 Redis 时 dlq_size 返回 0。"""
    from tasks.dead_letter import dlq_size
    import os
    old = os.environ.pop("REDIS_URL", None)
    try:
        assert dlq_size() == 0
    finally:
        if old is not None:
            os.environ["REDIS_URL"] = old


# ── intent_router 优化测试 ─────────────────────────────────────

@pytest.mark.asyncio
async def test_intent_router_skips_llm_if_intent_preset():
    """如果 state 已有 intent，intent_router 不应发起 LLM 调用。"""
    from agents.intent_router import run_intent_router

    state: AgentState = {"intent": "refund", "complexity": 65, "messages": [{"role": "user", "content": "test"}]}  # type: ignore
    mock_llm = AsyncMock()

    with patch("agents.intent_router.call_llm", mock_llm):
        result = await run_intent_router(state)

    mock_llm.assert_not_called()
    assert result.get("intent") == "refund"
    assert result.get("complexity") == 65
