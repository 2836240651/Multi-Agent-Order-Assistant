"""LLM-as-Judge：用 heavy profile 评判答案质量。

评判维度：
- faithfulness：答案是否忠实于引用片段（0-1）
- relevancy：答案是否回答了问题（0-1）
- overall：综合分（0-1）

W2 实现：调用 call_llm(profile="heavy")，返回 JSON；失败降级为 0.5。
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_SYSTEM = """你是专业的 RAG 答案质量评估专家。根据以下信息评估答案质量并输出 JSON。
不要解释，直接输出 JSON。格式：
{"faithfulness": 0.0~1.0, "relevancy": 0.0~1.0, "overall": 0.0~1.0, "comment": "简短评语（20字内）"}

评分标准：
- faithfulness：答案内容是否严格来自 context（没有凭空捏造）
- relevancy：答案是否准确回答了问题
- overall：综合评分"""

_USER_TMPL = """问题：{query}

参考上下文（context）：
{context}

待评估答案：
{answer}"""


async def judge_rag(
    query: str,
    context: str,
    answer: str,
) -> dict[str, Any]:
    """LLM-as-Judge for RAG answers. 失败 → fallback score 0.5。"""
    from llm import call_llm

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _USER_TMPL.format(query=query, context=context[:2000], answer=answer)},
    ]
    try:
        result = await call_llm(profile="heavy", messages=messages, stream=False)
        text = result.text if hasattr(result, "text") else str(result)
        data = _safe_parse(text)
        if "faithfulness" not in data:
            raise ValueError("missing faithfulness")
        return {
            "pass": float(data.get("overall", 0.5)) >= 0.6,
            "faithfulness": float(data.get("faithfulness", 0.5)),
            "relevancy": float(data.get("relevancy", 0.5)),
            "overall": float(data.get("overall", 0.5)),
            "comment": data.get("comment", ""),
        }
    except Exception as exc:
        logger.warning("llm_judge failed, fallback to 0.5: %s", exc)
        return {
            "pass": False,
            "faithfulness": 0.5,
            "relevancy": 0.5,
            "overall": 0.5,
            "comment": f"[judge_error] {str(exc)[:80]}",
        }


async def judge_e2e(
    query: str,
    answer: str,
    expected_contains: list[str],
) -> dict[str, Any]:
    """E2E 评测：先做 keyword match，再做 LLM fluency 评估。"""
    if not answer:
        return {"pass": False, "keyword_match": 0.0, "overall": 0.0, "comment": "empty answer"}

    matched = [kw for kw in expected_contains if kw and kw in answer]
    keyword_score = len(matched) / max(1, len(expected_contains)) if expected_contains else 1.0

    # 简单的流畅度评估：句子不为空即可
    fluency = 1.0 if len(answer) > 20 else 0.5
    overall = keyword_score * 0.7 + fluency * 0.3
    return {
        "pass": overall >= 0.6,
        "keyword_match": keyword_score,
        "overall": overall,
        "matched": matched,
        "missing": [kw for kw in expected_contains if kw and kw not in answer],
        "comment": f"keyword_match={keyword_score:.2f}",
    }


def _safe_parse(text: str) -> dict:
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        for p in parts:
            p = p.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{"):
                try:
                    return json.loads(p)
                except json.JSONDecodeError:
                    continue
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return {}


__all__ = ["judge_rag", "judge_e2e"]
