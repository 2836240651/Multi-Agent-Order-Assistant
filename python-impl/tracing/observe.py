"""tracing/observe.py：Langfuse 全链路观测装饰器。

策略：
- 若 langfuse 包已安装且 LANGFUSE_PUBLIC_KEY 已配置 → 真实上报
- 否则 → no-op 装饰器（不报错、不影响业务逻辑）

用法：
    from tracing.observe import observe, flush_langfuse

    @observe(name="knowledge_agent.retrieve")
    async def _retrieve_for_state(state):
        ...
"""
from __future__ import annotations

import functools
import logging
import os
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

_langfuse_client = None
_langfuse_initialized = False


def _get_langfuse():
    """懒加载 Langfuse 客户端；未配置或未安装时返回 None。"""
    global _langfuse_client, _langfuse_initialized
    if _langfuse_initialized:
        return _langfuse_client

    _langfuse_initialized = True
    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    sk = os.getenv("LANGFUSE_SECRET_KEY", "")
    host = os.getenv("LANGFUSE_HOST", "http://localhost:13000")

    if not pk or not sk:
        logger.debug("LANGFUSE_PUBLIC_KEY/SECRET_KEY not set — Langfuse disabled")
        return None

    try:
        from langfuse import Langfuse  # type: ignore[import]
        _langfuse_client = Langfuse(public_key=pk, secret_key=sk, host=host)
        logger.info("Langfuse client initialized (host=%s)", host)
    except ImportError:
        logger.debug("langfuse package not installed — tracing disabled")
    except Exception as exc:
        logger.warning("Langfuse init failed: %s", exc)

    return _langfuse_client


def observe(
    name: str | None = None,
    *,
    capture_input: bool = True,
    capture_output: bool = True,
    as_type: str = "span",
) -> Callable:
    """通用观测装饰器，可用于同步或异步函数。

    :param name: trace/span 名称，默认为函数的 __qualname__。
    :param capture_input: 是否记录输入参数（大 state 建议关闭以节省带宽）。
    :param capture_output: 是否记录返回值。
    :param as_type: "span"（默认）或 "generation"（LLM 调用专用）。
    """
    import asyncio

    def decorator(func: Callable) -> Callable:
        span_name = name or func.__qualname__

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            lf = _get_langfuse()
            if lf is None:
                return await func(*args, **kwargs)

            trace = lf.trace(name=span_name)
            span = trace.span(name=span_name)

            if capture_input:
                try:
                    _safe_set_input(span, args, kwargs)
                except Exception:
                    pass

            t0 = time.monotonic()
            try:
                result = await func(*args, **kwargs)
                elapsed = (time.monotonic() - t0) * 1000
                span.update(metadata={"latency_ms": round(elapsed, 1)})
                if capture_output and result is not None:
                    try:
                        _safe_set_output(span, result)
                    except Exception:
                        pass
                span.end()
                return result
            except Exception as exc:
                elapsed = (time.monotonic() - t0) * 1000
                span.update(
                    level="ERROR",
                    status_message=str(exc)[:200],
                    metadata={"latency_ms": round(elapsed, 1)},
                )
                span.end()
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            lf = _get_langfuse()
            if lf is None:
                return func(*args, **kwargs)

            trace = lf.trace(name=span_name)
            span = trace.span(name=span_name)

            if capture_input:
                try:
                    _safe_set_input(span, args, kwargs)
                except Exception:
                    pass

            t0 = time.monotonic()
            try:
                result = func(*args, **kwargs)
                elapsed = (time.monotonic() - t0) * 1000
                span.update(metadata={"latency_ms": round(elapsed, 1)})
                if capture_output and result is not None:
                    try:
                        _safe_set_output(span, result)
                    except Exception:
                        pass
                span.end()
                return result
            except Exception as exc:
                elapsed = (time.monotonic() - t0) * 1000
                span.update(
                    level="ERROR",
                    status_message=str(exc)[:200],
                    metadata={"latency_ms": round(elapsed, 1)},
                )
                span.end()
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def observe_llm(
    name: str | None = None,
    *,
    model: str = "unknown",
) -> Callable:
    """LLM 调用专用装饰器，记录 generation 类型 span 和 token 用量。

    被装饰的函数需返回 LLMResult（含 .text / .usage / .model 字段）。
    """
    import asyncio

    def decorator(func: Callable) -> Callable:
        span_name = name or func.__qualname__

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            lf = _get_langfuse()
            if lf is None:
                return await func(*args, **kwargs)

            trace = lf.trace(name=span_name)
            gen = trace.generation(name=span_name, model=model)

            t0 = time.monotonic()
            try:
                result = await func(*args, **kwargs)
                elapsed = (time.monotonic() - t0) * 1000
                usage = getattr(result, "usage", {}) or {}
                gen.end(
                    output=getattr(result, "text", str(result))[:1000],
                    usage={
                        "input": usage.get("input_tokens", 0),
                        "output": usage.get("output_tokens", 0),
                    },
                    metadata={"latency_ms": round(elapsed, 1), "model": getattr(result, "model", model)},
                )
                return result
            except Exception as exc:
                gen.end(
                    level="ERROR",
                    status_message=str(exc)[:200],
                    metadata={"latency_ms": round((time.monotonic() - t0) * 1000, 1)},
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            lf = _get_langfuse()
            if lf is None:
                return func(*args, **kwargs)

            trace = lf.trace(name=span_name)
            gen = trace.generation(name=span_name, model=model)

            t0 = time.monotonic()
            try:
                result = func(*args, **kwargs)
                elapsed = (time.monotonic() - t0) * 1000
                usage = getattr(result, "usage", {}) or {}
                gen.end(
                    output=getattr(result, "text", str(result))[:1000],
                    usage={
                        "input": usage.get("input_tokens", 0),
                        "output": usage.get("output_tokens", 0),
                    },
                    metadata={"latency_ms": round(elapsed, 1), "model": getattr(result, "model", model)},
                )
                return result
            except Exception as exc:
                gen.end(
                    level="ERROR",
                    status_message=str(exc)[:200],
                    metadata={"latency_ms": round((time.monotonic() - t0) * 1000, 1)},
                )
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def flush_langfuse() -> None:
    """在进程退出前调用，确保所有 span 上报完毕。"""
    lf = _get_langfuse()
    if lf is not None:
        try:
            lf.flush()
        except Exception as exc:
            logger.warning("Langfuse flush error: %s", exc)


def _safe_set_input(span: Any, args: tuple, kwargs: dict) -> None:
    serializable: dict[str, Any] = {}
    for i, a in enumerate(args):
        try:
            import json
            json.dumps(a)
            serializable[f"arg{i}"] = a
        except (TypeError, ValueError):
            serializable[f"arg{i}"] = repr(a)[:200]
    for k, v in kwargs.items():
        try:
            import json
            json.dumps(v)
            serializable[k] = v
        except (TypeError, ValueError):
            serializable[k] = repr(v)[:200]
    span.update(input=serializable)


def _safe_set_output(span: Any, result: Any) -> None:
    try:
        import json
        json.dumps(result)
        span.update(output=result)
    except (TypeError, ValueError):
        span.update(output=repr(result)[:500])


__all__ = ["observe", "observe_llm", "flush_langfuse"]
