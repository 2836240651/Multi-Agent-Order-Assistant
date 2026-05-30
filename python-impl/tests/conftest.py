"""pytest 全局配置：确保 python-impl/ 在 sys.path；强制 APP_ENV=test 触发内存版基础设施。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# python-impl/ 不能直接当包名（含连字符），用 sys.path 注入
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 强制 test 环境：Qdrant 用 in-memory、避免连到本地 Postgres
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("RAG_USE_LOCAL_FALLBACK", "true")


def pytest_sessionstart(session) -> None:  # noqa: ARG001
    """评测/回放前灌入内存 KB，避免 RAG 空答。"""
    try:
        from rag.bootstrap import ensure_kb_indexed

        ensure_kb_indexed()
    except Exception:
        pass
