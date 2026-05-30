"""scripts/bench/quick_perf.py：无 Docker 的轻量性能采样（知识问答路径）。"""
from __future__ import annotations

import asyncio
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("RAG_USE_LOCAL_FALLBACK", "true")


async def _one(query: str) -> float:
    from agents.knowledge_agent import stream_knowledge
    from agents.state import initial_state
    from db import set_current_tenant
    from rag.bootstrap import ensure_kb_indexed

    ensure_kb_indexed()
    set_current_tenant(1)
    state = initial_state(
        messages=[{"role": "user", "content": query}],
        thread_id="bench",
        user_id=None,
        tenant_id=1,
    )
    t0 = time.monotonic()
    async for ev in stream_knowledge(state):
        if ev.type in {"done", "no_match", "error"}:
            break
    return (time.monotonic() - t0) * 1000


async def main() -> None:
    queries = ["7天无理由退货的条件是什么", "退款多久到账", "包邮门槛是多少"] * 7
    latencies: list[float] = []
    for q in queries:
        latencies.append(await _one(q))
    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[int(len(latencies) * 0.95) - 1]
    print(f"samples={len(latencies)} p50_ms={p50:.0f} p95_ms={p95:.0f} avg_ms={statistics.mean(latencies):.0f}")


if __name__ == "__main__":
    asyncio.run(main())
