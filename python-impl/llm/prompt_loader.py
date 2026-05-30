"""llm/prompt_loader.py：从版本化 Markdown 文件加载 prompt。

用法：
    from llm.prompt_loader import load_prompt
    system_prompt = load_prompt("risk/llm_scorer")  # → risk/prompts/llm_scorer.md
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_PROMPTS_ROOT = Path(__file__).parents[1]


@lru_cache(maxsize=64)
def load_prompt(name: str) -> str:
    """按名称加载 prompt 文件（带 LRU 缓存）。

    name 格式：模块/文件名（不含 .md），如 "risk/llm_scorer"。
    搜索路径：<root>/{name}/prompts/<basename>.md 或 <root>/{name}.md。
    """
    parts = name.split("/")
    # 优先 <module>/prompts/<file>.md
    if len(parts) == 2:
        candidate = _PROMPTS_ROOT / parts[0] / "prompts" / f"{parts[1]}.md"
        if candidate.exists():
            return candidate.read_text(encoding="utf-8").strip()
    # fallback: 直接 <name>.md
    direct = _PROMPTS_ROOT / f"{name}.md"
    if direct.exists():
        return direct.read_text(encoding="utf-8").strip()
    logger.warning("prompt not found: %s, returning empty string", name)
    return ""


def invalidate_cache() -> None:
    """清空 prompt 缓存（热更新时调用）。"""
    load_prompt.cache_clear()


__all__ = ["load_prompt", "invalidate_cache"]
