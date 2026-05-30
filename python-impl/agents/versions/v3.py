"""agents/versions/v3.py：V3 — 全 7 Agent + 三层风控 + Planner + Critic（当前主版本）。

复用 supervisor.build_graph()，此文件只做薄封装便于 GRAPHS 统一引用。
"""
from __future__ import annotations

from typing import Any


def build_v3(checkpointer=None) -> Any:
    from agents.supervisor import build_graph
    return build_graph(checkpointer=checkpointer)


__all__ = ["build_v3"]
