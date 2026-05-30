"""异常模块对外接口。"""
from .error_code import (
    BusinessException,
    ErrorCode,
    default_message,
    http_status_for,
)

__all__ = ["BusinessException", "ErrorCode", "default_message", "http_status_for"]
