"""统一错误码枚举与业务异常基类。设计.md §5.2 对应实现。

任何业务抛错必须使用 ErrorCode 枚举；新增异常先补枚举，再 raise。
"""
from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """错误码统一登记表。命名约定 <模块>_<编号>。"""

    # === 鉴权 1xxx ===
    AUTH_INVALID_CREDENTIALS = "AUTH_1001"
    AUTH_TOKEN_EXPIRED = "AUTH_1002"
    AUTH_TOKEN_INVALID = "AUTH_1003"
    AUTH_USER_LOCKED = "AUTH_1004"
    AUTH_TENANT_DISABLED = "AUTH_1005"

    # === 权限 2xxx ===
    PERM_FORBIDDEN = "PERM_2001"
    PERM_TENANT_MISMATCH = "PERM_2002"

    # === 业务 3xxx ===
    BIZ_ORDER_NOT_FOUND = "BIZ_3001"
    BIZ_ORDER_NOT_ELIGIBLE = "BIZ_3002"
    BIZ_REFUND_EXPIRED = "BIZ_3003"
    BIZ_REFUND_DUPLICATE = "BIZ_3004"
    BIZ_TICKET_NOT_FOUND = "BIZ_3005"
    BIZ_TICKET_STATE_INVALID = "BIZ_3006"
    BIZ_KB_NOT_FOUND = "BIZ_3007"
    BIZ_PARAM_INVALID = "BIZ_3008"
    BIZ_NOT_FOUND = "BIZ_3009"
    BIZ_CONFLICT = "BIZ_3010"

    # === 风控 4xxx ===
    RISK_HIGH_NEED_REVIEW = "RISK_4001"
    RISK_LLM_UNAVAILABLE = "RISK_4002"

    # === 模型 5xxx ===
    LLM_ALL_UNAVAILABLE = "LLM_5001"
    LLM_RATE_LIMIT = "LLM_5002"
    LLM_OUTPUT_INVALID = "LLM_5003"
    LLM_PROFILE_UNKNOWN = "LLM_5004"

    # === 限流 6xxx ===
    RATE_LIMIT_USER = "RATE_6001"
    RATE_LIMIT_TENANT = "RATE_6002"

    # === RAG 7xxx ===
    RAG_NO_RELEVANT = "RAG_7001"
    RAG_VECTORSTORE_DOWN = "RAG_7002"

    # === 系统 9xxx ===
    SYS_DB_ERROR = "SYS_9001"
    SYS_DEPENDENCY_DOWN = "SYS_9002"
    SYS_CONFIG_INVALID = "SYS_9003"
    SYS_INTERNAL_ERROR = "SYS_9004"


_DEFAULT_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.AUTH_INVALID_CREDENTIALS: "账号或密码错误",
    ErrorCode.AUTH_TOKEN_EXPIRED: "登录已过期",
    ErrorCode.AUTH_TOKEN_INVALID: "登录态无效",
    ErrorCode.AUTH_USER_LOCKED: "账号已锁定，请稍后再试",
    ErrorCode.AUTH_TENANT_DISABLED: "租户已停用",
    ErrorCode.PERM_FORBIDDEN: "无权限执行该操作",
    ErrorCode.PERM_TENANT_MISMATCH: "未找到资源",  # 防枚举：返 404 文案
    ErrorCode.BIZ_ORDER_NOT_FOUND: "未找到该订单",
    ErrorCode.BIZ_ORDER_NOT_ELIGIBLE: "订单当前状态不可执行",
    ErrorCode.BIZ_REFUND_EXPIRED: "已超过 7 天无理由期",
    ErrorCode.BIZ_REFUND_DUPLICATE: "该订单已申请过退款",
    ErrorCode.BIZ_TICKET_NOT_FOUND: "未找到该工单",
    ErrorCode.BIZ_TICKET_STATE_INVALID: "工单状态不允许此操作",
    ErrorCode.BIZ_KB_NOT_FOUND: "未找到知识文档",
    ErrorCode.BIZ_PARAM_INVALID: "请求参数无效",
    ErrorCode.BIZ_NOT_FOUND: "资源不存在",
    ErrorCode.BIZ_CONFLICT: "资源冲突，操作无法完成",
    ErrorCode.RISK_HIGH_NEED_REVIEW: "命中高风险，需人工审核",
    ErrorCode.RISK_LLM_UNAVAILABLE: "风控 LLM 不可用，已降级",
    ErrorCode.LLM_ALL_UNAVAILABLE: "系统繁忙，建议稍后或转人工",
    ErrorCode.LLM_RATE_LIMIT: "模型限流，请稍后重试",
    ErrorCode.LLM_OUTPUT_INVALID: "模型输出不合规",
    ErrorCode.LLM_PROFILE_UNKNOWN: "未知模型 profile",
    ErrorCode.RATE_LIMIT_USER: "请求过快，请稍后再试",
    ErrorCode.RATE_LIMIT_TENANT: "租户限流",
    ErrorCode.RAG_NO_RELEVANT: "未在政策中找到相关内容",
    ErrorCode.RAG_VECTORSTORE_DOWN: "向量库暂不可用",
    ErrorCode.SYS_DB_ERROR: "数据库异常",
    ErrorCode.SYS_DEPENDENCY_DOWN: "依赖服务异常",
    ErrorCode.SYS_CONFIG_INVALID: "配置无效",
    ErrorCode.SYS_INTERNAL_ERROR: "服务内部异常",
}


# 错误码 → HTTP 状态映射
_HTTP_STATUS_MAP: dict[ErrorCode, int] = {
    ErrorCode.AUTH_INVALID_CREDENTIALS: 401,
    ErrorCode.AUTH_TOKEN_EXPIRED: 401,
    ErrorCode.AUTH_TOKEN_INVALID: 401,
    ErrorCode.AUTH_USER_LOCKED: 403,
    ErrorCode.AUTH_TENANT_DISABLED: 403,
    ErrorCode.PERM_FORBIDDEN: 403,
    ErrorCode.PERM_TENANT_MISMATCH: 404,  # 防枚举：跨租户返 404
    ErrorCode.BIZ_ORDER_NOT_FOUND: 404,
    ErrorCode.BIZ_TICKET_NOT_FOUND: 404,
    ErrorCode.BIZ_KB_NOT_FOUND: 404,
    ErrorCode.BIZ_ORDER_NOT_ELIGIBLE: 409,
    ErrorCode.BIZ_REFUND_EXPIRED: 409,
    ErrorCode.BIZ_REFUND_DUPLICATE: 409,
    ErrorCode.BIZ_TICKET_STATE_INVALID: 409,
    ErrorCode.BIZ_PARAM_INVALID: 400,
    ErrorCode.BIZ_NOT_FOUND: 404,
    ErrorCode.BIZ_CONFLICT: 409,
    ErrorCode.RISK_HIGH_NEED_REVIEW: 202,
    ErrorCode.RISK_LLM_UNAVAILABLE: 503,
    ErrorCode.LLM_ALL_UNAVAILABLE: 503,
    ErrorCode.LLM_RATE_LIMIT: 429,
    ErrorCode.LLM_OUTPUT_INVALID: 502,
    ErrorCode.RATE_LIMIT_USER: 429,
    ErrorCode.RATE_LIMIT_TENANT: 429,
    ErrorCode.RAG_NO_RELEVANT: 200,
    ErrorCode.RAG_VECTORSTORE_DOWN: 503,
    ErrorCode.SYS_DB_ERROR: 500,
    ErrorCode.SYS_DEPENDENCY_DOWN: 503,
    ErrorCode.SYS_CONFIG_INVALID: 500,
    ErrorCode.SYS_INTERNAL_ERROR: 500,
    ErrorCode.LLM_PROFILE_UNKNOWN: 500,
}


def default_message(code: ErrorCode) -> str:
    return _DEFAULT_MESSAGES.get(code, code.value)


def http_status_for(code: ErrorCode) -> int:
    return _HTTP_STATUS_MAP.get(code, 500)


class BusinessException(Exception):
    """业务异常基类。捕获后由 api/main.py 全局 handler 转 JSON。"""

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        **extra: Any,
    ):
        self.code = code
        self.message = message or default_message(code)
        self.extra = extra
        super().__init__(f"[{code.value}] {self.message}")

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code.value, "message": self.message, **self.extra}


__all__ = [
    "ErrorCode",
    "BusinessException",
    "default_message",
    "http_status_for",
]
