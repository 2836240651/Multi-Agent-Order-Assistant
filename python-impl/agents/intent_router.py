from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from langchain_openai import ChatOpenAI

from tracing.otel_config import trace_agent_call


class IntentCategory(str, Enum):
    ORDER_QUERY = "order_query"
    REFUND_REQUEST = "refund_request"
    ADDRESS_CHANGE = "address_change"
    TICKET_QUERY = "ticket_query"
    KNOWLEDGE = "knowledge"
    GREETING = "greeting"
    LOGISTICS_QUERY = "logistics_query"
    LOGISTICS_EXPEDITE = "logistics_expedite"
    CONTINUATION = "continuation"
    EXCHANGE_REQUEST = "exchange_request"


@dataclass
class IntentResult:
    primary_intent: IntentCategory
    confidence: float
    entities: dict[str, str]
    suggested_agent: str
    execution_action: str


ORDER_ID_PATTERN = re.compile(r"ORD-\d{8}-\d{4}", re.IGNORECASE)
TICKET_ID_PATTERN = re.compile(r"TK-\d{8}-[A-Z0-9]{6}", re.IGNORECASE)


class IntentRouterAgent:
    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    @trace_agent_call("intent_router")
    async def classify(self, user_message: str) -> IntentResult:
        msg = user_message.lower()
        entities: dict[str, str] = {}

        order_id_match = ORDER_ID_PATTERN.search(user_message)
        ticket_id_match = TICKET_ID_PATTERN.search(user_message)
        if order_id_match:
            entities["order_id"] = order_id_match.group(0).upper()
        if ticket_id_match:
            entities["ticket_id"] = ticket_id_match.group(0).upper()

        if entities.get("ticket_id") or ("工单" in user_message and "查询" in user_message):
            return IntentResult(
                primary_intent=IntentCategory.TICKET_QUERY,
                confidence=0.95,
                entities=entities,
                suggested_agent="ticket_handler",
                execution_action="ticket_query",
            )

        continuation_words = ["继续", "继续说", "上一个问题是啥", "接着上一个", "下一步怎么做", "然后呢", "后来呢", "接着说", "继续之前的话题", "继续刚才的"]
        if any(word in user_message for word in continuation_words):
            return IntentResult(
                primary_intent=IntentCategory.CONTINUATION,
                confidence=0.95,
                entities=entities,
                suggested_agent="ticket_handler",
                execution_action="continuation",
            )

        greeting_words = ["你好", "您好", "hi", "hello", "嗨", "嘿", "早上好", "下午好", "晚上好"]
        if any(greeting in msg for greeting in greeting_words) and len(user_message.strip()) < 20:
            return IntentResult(
                primary_intent=IntentCategory.GREETING,
                confidence=0.95,
                entities=entities,
                suggested_agent="greeting_handler",
                execution_action="greeting",
            )

        service_words = ["你能做什么", "你能解决什么问题", "你能帮助我什么", "服务范围", "有什么服务", "你能干嘛", "你会什么", "干什么用的", "有什么用", "怎么用"]
        if any(word in msg for word in service_words):
            return IntentResult(
                primary_intent=IntentCategory.GREETING,
                confidence=0.9,
                entities=entities,
                suggested_agent="greeting_handler",
                execution_action="service_info",
            )

        if any(word in msg for word in ["退款", "退货", "refund"]):
            return IntentResult(
                primary_intent=IntentCategory.REFUND_REQUEST,
                confidence=0.93,
                entities=entities,
                suggested_agent="ticket_handler",
                execution_action="refund_apply",
            )

        if (
            ("地址" in user_message and any(k in msg for k in ["修改", "更改", "变更", "改地址", "改"]))
            or "change address" in msg
        ):
            return IntentResult(
                primary_intent=IntentCategory.ADDRESS_CHANGE,
                confidence=0.92,
                entities=entities,
                suggested_agent="ticket_handler",
                execution_action="order_update_address",
            )

        if any(word in msg for word in ["快递", "快递到", "物流到", "到哪了", "发货没", "发货了没", "追踪", "tracking", "delivery", "催发货", "催促发货", "物流状态", "快递状态", "发货状态"]):
            if any(word in msg for word in ["催促", "催发货", "加急", "快点", "急", "尽快", "urge"]):
                return IntentResult(
                    primary_intent=IntentCategory.LOGISTICS_EXPEDITE,
                    confidence=0.95,
                    entities=entities,
                    suggested_agent="ticket_handler",
                    execution_action="logistics_expedite",
                )
            return IntentResult(
                primary_intent=IntentCategory.LOGISTICS_QUERY,
                confidence=0.93,
                entities=entities,
                suggested_agent="ticket_handler",
                execution_action="logistics_query",
            )

        if any(word in msg for word in ["订单", "物流", "查单", "order", "shipping"]):
            return IntentResult(
                primary_intent=IntentCategory.ORDER_QUERY,
                confidence=0.9,
                entities=entities,
                suggested_agent="ticket_handler",
                execution_action="order_query",
            )

        if any(word in msg for word in ["换货", "更换", "换商品", "换型号"]):
            return IntentResult(
                primary_intent=IntentCategory.EXCHANGE_REQUEST,
                confidence=0.95,
                entities=entities,
                suggested_agent="ticket_handler",
                execution_action="exchange_request",
            )

        return IntentResult(
            primary_intent=IntentCategory.KNOWLEDGE,
            confidence=0.6,
            entities=entities,
            suggested_agent="knowledge_rag",
            execution_action="knowledge_search",
        )

    @trace_agent_call("intent_router_process")
    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        messages = state.get("messages", [])
        if not messages:
            return state

        last_message = messages[-1].content
        intent_result = await self.classify(last_message)
        
        entities = dict(intent_result.entities)
        if not entities.get("order_id") and state.get("context_order_id"):
            entities["order_id"] = state["context_order_id"]

        return {
            **state,
            "intent": intent_result.suggested_agent,
            "execution_action": intent_result.execution_action,
            "entities": entities,
            "sub_results": {
                **state.get("sub_results", {}),
                "intent_router": {
                    "primary": intent_result.primary_intent.value,
                    "confidence": intent_result.confidence,
                    "entities": entities,
                    "execution_action": intent_result.execution_action,
                },
            },
        }
