"""Query 改写：把口语化 query 改写成 2 个变体。

W1 简化：用 light profile 调 call_llm；提示词内置。失败 / 无 key → 退回返回原 query。
"""
from __future__ import annotations

import json
import logging

from llm import call_llm

logger = logging.getLogger(__name__)


_PROMPT = """你是检索查询改写器。把用户原始问题改写成 2 个搜索友好的同义变体（保留核心实体），仅输出 JSON：
{{"variants": ["变体1", "变体2"]}}

原始问题：{query}
"""


async def rewrite(query: str, n: int = 2) -> list[str]:
    """返回包含原 query 在内的去重列表（≤ n+1 个）。"""
    query = (query or "").strip()
    if not query:
        return []
    try:
        result = await call_llm(
            profile="light",
            messages=[{"role": "user", "content": _PROMPT.format(query=query)}],
            stream=False,
        )
        text = result.text if hasattr(result, "text") else ""
        data = _safe_parse(text)
        variants = [v for v in data.get("variants", []) if isinstance(v, str) and v.strip()]
        # 去重保留顺序
        out: list[str] = []
        for q in [query] + variants[:n]:
            if q not in out:
                out.append(q)
        return out
    except Exception as exc:
        logger.warning("query rewrite failed, fallback to original: %s", exc)
        return [query]


def _safe_parse(text: str) -> dict:
    """容忍 markdown code fence / 多余文字。"""
    text = text.strip()
    if "```" in text:
        # 取第一个 code block 内容
        parts = text.split("```")
        for p in parts:
            p = p.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{") and p.endswith("}"):
                try:
                    return json.loads(p)
                except json.JSONDecodeError:
                    continue
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return {}


__all__ = ["rewrite"]
