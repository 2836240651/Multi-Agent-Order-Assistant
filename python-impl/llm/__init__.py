"""llm 模块对外接口。仅 re-export 统一入口。"""
from .router import LLMResult, call_llm

__all__ = ["call_llm", "LLMResult"]
