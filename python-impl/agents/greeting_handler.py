"""GreetingHandler：闲聊/寒暄兜底。W1 极简实现，W4 接 @observe。"""
from __future__ import annotations

from .state import AgentState
from tracing.observe import observe


_RESPONSES = {
    "你好": "你好！我是 RetailGuard 智能客服，可以帮你查订单、办退款、回答售后政策。",
    "您好": "您好！请问需要查询订单、申请退款，还是想了解售后政策？",
    "hi": "Hi! 请问需要什么帮助？",
    "hello": "Hello! 请问需要什么帮助？",
    "在吗": "在的，请问有什么可以帮您？",
}


def _last_user_message(state: AgentState) -> str:
    for m in reversed(state.get("messages") or []):
        if m.get("role") == "user":
            return str(m.get("content", "")).strip()
    return ""


@observe(name="greeting.run", capture_input=False)
async def run_greeting(state: AgentState) -> AgentState:
    text = _last_user_message(state)
    answer = _RESPONSES.get(text.lower()) or "你好，我是 RetailGuard 售后助手。请告诉我你的诉求。"
    return AgentState(answer=answer, citations=[])


__all__ = ["run_greeting"]
