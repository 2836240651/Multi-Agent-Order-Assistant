from __future__ import annotations

import functools
import os
import time
from collections import defaultdict, deque
from typing import Any, Callable

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False


_tracer = None
_tracer_initialized = False


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def init_tracer(
    service_name: str = "smart-cs-multi-agent",
    otlp_endpoint: str | None = None,
    enable_console_export: bool | None = None,
) -> None:
    global _tracer, _tracer_initialized

    if not _HAS_OTEL or _tracer_initialized:
        return

    if enable_console_export is None:
        enable_console_export = _as_bool(os.getenv("OTEL_ENABLE_CONSOLE_EXPORT"), default=False)

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    exporter = None
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        except ImportError:
            exporter = ConsoleSpanExporter() if enable_console_export else None
    elif enable_console_export:
        exporter = ConsoleSpanExporter()

    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(service_name)
    _tracer_initialized = True


def get_tracer():
    global _tracer
    if _tracer is None:
        if _HAS_OTEL:
            _tracer = trace.get_tracer("smart-cs-multi-agent")
        else:
            return None
    return _tracer


def trace_agent_call(agent_name: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            tracer = get_tracer()

            if tracer is None:
                return await func(*args, **kwargs)

            span_name = f"agent.{agent_name}.{func.__name__}"

            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("agent.name", agent_name)
                span.set_attribute("agent.method", func.__name__)

                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    duration_ms = (time.time() - start_time) * 1000

                    span.set_attribute("agent.duration_ms", duration_ms)
                    span.set_attribute("agent.success", True)

                    if isinstance(result, dict):
                        span.set_attribute("agent.result_keys", str(list(result.keys())))

                    return result

                except Exception as exc:
                    duration_ms = (time.time() - start_time) * 1000
                    span.set_attribute("agent.duration_ms", duration_ms)
                    span.set_attribute("agent.success", False)
                    span.set_attribute("agent.error", str(exc))
                    span.record_exception(exc)
                    raise

        return wrapper

    return decorator


class AgentMetrics:
    def __init__(self):
        self._call_counts: dict[str, int] = {}
        self._total_duration: dict[str, float] = {}
        self._error_counts: dict[str, int] = {}

    def record_call(self, agent_name: str, duration_ms: float, success: bool):
        self._call_counts[agent_name] = self._call_counts.get(agent_name, 0) + 1
        self._total_duration[agent_name] = self._total_duration.get(agent_name, 0.0) + duration_ms
        if not success:
            self._error_counts[agent_name] = self._error_counts.get(agent_name, 0) + 1

    def get_summary(self) -> dict[str, Any]:
        summary = {}
        for agent_name in self._call_counts:
            calls = self._call_counts[agent_name]
            total_ms = self._total_duration[agent_name]
            errors = self._error_counts.get(agent_name, 0)
            summary[agent_name] = {
                "total_calls": calls,
                "avg_duration_ms": round(total_ms / calls, 2) if calls > 0 else 0,
                "error_rate": round(errors / calls, 4) if calls > 0 else 0,
            }
        return summary


class RuntimeObservability:
    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self._requests = 0
        self._errors = 0
        self._degraded = 0
        self._manual_reviews = 0
        self._total_latency_ms = 0.0
        self._estimated_prompt_tokens = 0
        self._estimated_completion_tokens = 0
        self._by_variant: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "requests": 0,
                "errors": 0,
                "degraded": 0,
                "manual_reviews": 0,
                "latency_ms_total": 0.0,
                "estimated_tokens": 0,
                "estimated_cost_usd": 0.0,
            }
        )
        self._by_error_code: dict[str, int] = defaultdict(int)
        self._recent_events: deque[dict[str, Any]] = deque(maxlen=50)

    @staticmethod
    def estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // 4)

    @staticmethod
    def estimate_cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
        prompt_cost = prompt_tokens * 0.0000005
        completion_cost = completion_tokens * 0.0000015
        return round(prompt_cost + completion_cost, 6)

    def record_request(
        self,
        *,
        variant: str,
        action: str,
        status: str,
        success: bool,
        degraded: bool,
        manual_review: bool,
        latency_ms: float,
        prompt_text: str,
        completion_text: str,
        error_code: str = "",
    ) -> None:
        prompt_tokens = self.estimate_tokens(prompt_text)
        completion_tokens = self.estimate_tokens(completion_text)
        estimated_cost = self.estimate_cost_usd(prompt_tokens, completion_tokens)

        self._requests += 1
        self._errors += int(not success)
        self._degraded += int(degraded)
        self._manual_reviews += int(manual_review)
        self._total_latency_ms += latency_ms
        self._estimated_prompt_tokens += prompt_tokens
        self._estimated_completion_tokens += completion_tokens

        bucket = self._by_variant[variant]
        bucket["requests"] += 1
        bucket["errors"] += int(not success)
        bucket["degraded"] += int(degraded)
        bucket["manual_reviews"] += int(manual_review)
        bucket["latency_ms_total"] += latency_ms
        bucket["estimated_tokens"] += prompt_tokens + completion_tokens
        bucket["estimated_cost_usd"] = round(bucket["estimated_cost_usd"] + estimated_cost, 6)

        if error_code:
            self._by_error_code[error_code] += 1

        self._recent_events.appendleft(
            {
                "variant": variant,
                "action": action,
                "status": status,
                "success": success,
                "degraded": degraded,
                "manual_review": manual_review,
                "latency_ms": round(latency_ms, 2),
                "estimated_cost_usd": estimated_cost,
                "error_code": error_code,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        )

    def get_summary(self) -> dict[str, Any]:
        avg_latency_ms = round(self._total_latency_ms / self._requests, 2) if self._requests else 0.0
        total_tokens = self._estimated_prompt_tokens + self._estimated_completion_tokens

        by_variant = {}
        for variant, bucket in self._by_variant.items():
            requests = bucket["requests"]
            by_variant[variant] = {
                "requests": requests,
                "error_rate": round(bucket["errors"] / requests, 4) if requests else 0.0,
                "degraded_rate": round(bucket["degraded"] / requests, 4) if requests else 0.0,
                "manual_review_rate": round(bucket["manual_reviews"] / requests, 4) if requests else 0.0,
                "avg_latency_ms": round(bucket["latency_ms_total"] / requests, 2) if requests else 0.0,
                "estimated_tokens": bucket["estimated_tokens"],
                "estimated_cost_usd": round(bucket["estimated_cost_usd"], 6),
            }

        return {
            "requests": self._requests,
            "error_rate": round(self._errors / self._requests, 4) if self._requests else 0.0,
            "degraded_rate": round(self._degraded / self._requests, 4) if self._requests else 0.0,
            "manual_review_rate": round(self._manual_reviews / self._requests, 4) if self._requests else 0.0,
            "avg_latency_ms": avg_latency_ms,
            "estimated_prompt_tokens": self._estimated_prompt_tokens,
            "estimated_completion_tokens": self._estimated_completion_tokens,
            "estimated_total_tokens": total_tokens,
            "estimated_total_cost_usd": self.estimate_cost_usd(
                self._estimated_prompt_tokens,
                self._estimated_completion_tokens,
            ),
            "by_variant": by_variant,
            "error_breakdown": dict(sorted(self._by_error_code.items(), key=lambda item: item[1], reverse=True)),
            "recent_events": list(self._recent_events),
        }
