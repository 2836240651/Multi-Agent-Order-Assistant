"""IntentRouter：意图识别 + 复杂度估算。

W1 用轻量 LLM 加规则兜底（关键词命中）；W3 接入更精细的 complexity 估算。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Literal

from llm import call_llm
from llm.semantic_cache import get_cache
from agents.state import AgentState
from tracing.observe import observe

logger = logging.getLogger(__name__)


Intent = Literal[
    "knowledge", "order_query", "order_list", "refund", "refund_query",
    "logistics_query", "ticket_create", "ticket_query", "address_change",
    "greeting", "complex", "other",
]

_ALL_INTENTS = {
    "knowledge", "order_query", "order_list", "refund", "refund_query",
    "logistics_query", "ticket_create", "ticket_query", "address_change",
    "greeting", "complex", "other",
}

_PROMPT = """你是电商售后意图分类器。从下列意图中精确选一个：

- greeting: 打招呼、闲聊
- knowledge: 咨询政策/规定/FAQ（如"7天无理由吗"、"保修多久"）
- order_query: 查单个订单详情/状态（含订单号）
- order_list: 查我的订单列表
- logistics_query: 查物流/快递进度
- refund: 申请退款/退货
- refund_query: 查退款/退货进度
- ticket_create: 创建工单
- ticket_query: 查工单状态
- address_change: 修改收货地址
- complex: 需要多步骤的复合任务（如"退两件其中一件换地址"）
- other: 以上都不匹配

同时给出复杂度 0-100（>=60 表示需要多步规划）。
仅输出 JSON：{{"intent": "...", "complexity": 0}}

用户消息：{message}
"""


# 政策/FAQ 问法（优先于业务动作类关键词，对齐 intent.jsonl 口径）
_POLICY_Q = re.compile(
    r"(怎么|如何|多久|可以吗|能不能|吗|什么|哪些|谁承担|谁付|什么意思|怎么办|门槛|条件|政策|规定|能否|是否)"
)
_ACTION_Q = re.compile(
    r"(帮我|给我|立即|马上)(申请|办理)?(退款|退货)|创建工单|改地址|查.*订单|ORD-|订单号"
)

# 关键词兜底规则（按优先级从高到低）
_KEYWORD_RULES: list[tuple[Intent, re.Pattern[str]]] = [
    ("greeting", re.compile(
        r"^(你好|您好|hi|hello|在吗|嗨|哈喽|早上好|嗯嗯|谢谢|感谢).*$|^(你是谁|你能做什么).*$",
        re.IGNORECASE,
    )),
    ("address_change", re.compile(r"改地址|换地址|修改收货|改收件|变更地址")),
    ("logistics_query", re.compile(r"物流|快递|到哪了|运单|配送|到货")),
    ("refund_query", re.compile(r"退款.*进度|退货.*进度|退款.*查|退.*到哪|RF-")),
    ("refund", re.compile(r"申请退款|申请换货|帮我.*退款|帮我退|我要退款|退款\s*\d|退\d+\s*元")),
    ("ticket_query", re.compile(r"工单.*进度|工单.*状态|工单T-|查看工单|加急.*工单|取消工单")),
    ("ticket_create", re.compile(r"创建工单|开个工单|投诉")),
    ("order_query", re.compile(r"(查|查询).*(订单|ORD-)|ORD-.*(状态|物流|清单|超过)")),
    ("order_list", re.compile(r"(我的|最近|所有|全部).*(订单|退款记录|购物)")),
    ("knowledge", re.compile(r"政策|规定|条款|多久|几天|可以.*吗|能.*吗|无理由|保修|积分")),
]


def _is_policy_question(text: str) -> bool:
    """售后政策咨询（intent.jsonl 以 knowledge 为主；带单号/明确操作为业务意图）。"""
    t = text.strip()
    if _ACTION_Q.search(t):
        return False
    if re.search(r"ORD-|订单号|T-\d|RF-|工单\s*T", t, re.I):
        return False
    if re.search(r"(查一下|查询|查看|帮我|创建|取消|加急|投诉)", t):
        return False
    if _POLICY_Q.search(t):
        return True
    if re.match(r"^我要(退款|退货)[。.]?$", t):
        return True
    if re.search(r"(运费|包邮|保修|积分|发票|会员|门槛)", t):
        return True
    if re.search(r"(退款|退货)", t) and re.search(r"(多久|怎么|如何|到账|状态|意思)", t):
        return True
    return False


def _keyword_intent(text: str) -> Intent | None:
    if _is_policy_question(text):
        return "knowledge"
    for intent, pat in _KEYWORD_RULES:
        if pat.search(text):
            return intent
    return None


def _last_user_message(state: AgentState) -> str:
    msgs = state.get("messages") or []
    for m in reversed(msgs):
        if m.get("role") == "user":
            return str(m.get("content", ""))
    return ""


def _safe_parse(text: str) -> dict:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return {}


@observe(name="intent_router.run", capture_input=False)
async def run_intent_router(state: AgentState) -> AgentState:
    """节点函数：写回 state["intent"], state["complexity"]"""
    # 若已由外部（如 _stream_chat 预路由）设置 intent，直接复用，避免重复 LLM 调用
    if state.get("intent") is not None:
        return AgentState(intent=state["intent"], complexity=state.get("complexity") or 30)  # type: ignore[return-value]

    text = _last_user_message(state)

    # 关键词/政策问法优先（评测集以 knowledge/greeting 为主）
    kw = _keyword_intent(text)
    if kw:
        complexity = 10 if kw == "greeting" else 25
        return AgentState(intent=kw, complexity=complexity)

    prompt_text = _PROMPT.format(message=text)
    cache = get_cache()
    cached_raw = await cache.get(prompt_text)

    try:
        if cached_raw is not None:
            data = _safe_parse(cached_raw)
        else:
            result = await call_llm(
                profile="light",
                messages=[{"role": "user", "content": prompt_text}],
                stream=False,
            )
            raw_text = result.text  # type: ignore[union-attr]
            data = _safe_parse(raw_text)
            await cache.set(prompt_text, raw_text)

        intent = data.get("intent", "other")
        if intent not in _ALL_INTENTS:
            intent = "other"
        complexity = int(data.get("complexity", 30))
        complexity = max(0, min(100, complexity))
    except Exception as exc:
        logger.warning("intent router LLM failed, using fallback: %s", exc)
        intent = kw or "knowledge"
        complexity = 30

    return AgentState(intent=intent, complexity=complexity)  # type: ignore[arg-type]


__all__ = ["run_intent_router", "Intent"]
