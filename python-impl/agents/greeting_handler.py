from __future__ import annotations

from typing import Any

from tracing.otel_config import trace_agent_call


SYSTEM_PROMPT = """你是一名专业的零售电商客服助手，名称是 RetailGuard。

你的职责是帮助用户处理以下业务：

【可用服务】
1. 订单查询 - 用户可以查询订单状态、物流信息、收货地址、订单金额等
2. 退款申请 - 帮助用户提交退款请求，查询退款进度
3. 地址修改 - 帮助用户修改未发货订单的收货地址
4. 催促发货 - 帮助用户催促仓库加快处理未发货的订单
5. 工单查询 - 帮助用户查询已提交的工单状态和进度
6. 换货咨询 - 帮助用户了解换货流程（需转人工）

【回答规范】
1. 始终使用简体中文回答
2. 回答要简洁、友好、专业
3. 不要显示技术术语或内部状态码
4. 如果用户询问的功能暂不支持，引导用户联系人工客服
5. 如果订单不满足某项业务条件（如已过退款时限），要友好地解释原因

【记住】
- 你是客服助手，不是搜索引擎
- 始终以帮助用户解决问题为导向
- 保持耐心和友好的服务态度"""

SERVICE_INFO = """您好！我是 RetailGuard 智能客服助手。

我可以帮您处理以下服务：

📦 订单查询
   - 查看订单状态、物流信息、收货地址等

💰 退款申请
   - 提交退款请求，查询退款进度

📍 地址修改
   - 修改未发货订单的收货地址

🚚 催促发货
   - 催促仓库加快处理未发货的订单

🎫 工单查询
   - 查看您提交的服务工单状态

🔄 换货咨询
   - 换货需要联系人工客服处理

请问有什么可以帮助您的？"""

CONTINUATION_RESPONSE = """好的，请问您想继续了解什么？您可以：

📦 查询订单状态或物流信息
💰 申请退款
📍 修改收货地址
🚚 催促发货
🎫 查看工单进度

请告诉我您的需求～"""


class GreetingHandlerAgent:
    @trace_agent_call("greeting_handler")
    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        messages = state.get("messages", [])
        if not messages:
            return state

        user_message = messages[-1].content
        execution_action = state.get("execution_action", "")
        
        if execution_action == "service_info":
            final_response = SERVICE_INFO
        elif any(word in user_message for word in ["继续", "继续说", "上一个问题是啥", "接着上一个", "下一步怎么做", "然后呢", "后来呢", "继续之前的话题", "继续刚才的"]):
            final_response = CONTINUATION_RESPONSE
        else:
            user_lower = user_message.lower()
            if any(word in user_lower for word in ["你好", "您好", "嗨", "嘿", "早上好", "下午好", "晚上好"]):
                final_response = "您好！我是 RetailGuard 智能客服助手。很高兴为您服务！请问有什么可以帮助您的吗？"
            else:
                final_response = SERVICE_INFO

        return {
            **state,
            "final_response": final_response,
            "messages": messages + [{"role": "assistant", "content": final_response}],
        }
