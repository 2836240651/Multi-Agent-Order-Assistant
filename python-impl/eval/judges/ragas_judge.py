"""Ragas 指标 judge：context_precision / context_recall / faithfulness / answer_relevancy。

W2 简化方案：
- 如果 ragas 包已安装 → 调用真实 Ragas（需要 OpenAI/Langfuse key）
- 否则 → 基于 keyword overlap 实现轻量版 4 指标，供测试/本地 demo 使用

生产 usage：
    from eval.judges.ragas_judge import ragas_score
    result = await ragas_score(query, context_list, answer, expected_answer)
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _keyword_overlap(text_a: str, text_b: str) -> float:
    """简易 token overlap（用中文字符集合）。"""
    if not text_a or not text_b:
        return 0.0
    chars_a = set(text_a.replace(" ", ""))
    chars_b = set(text_b.replace(" ", ""))
    if not chars_a or not chars_b:
        return 0.0
    return len(chars_a & chars_b) / max(len(chars_a), len(chars_b))


def _context_precision(answer: str, contexts: list[str]) -> float:
    """答案字符与 contexts 的交集比率（precision：答案中有多少在 context 里有支撑）。"""
    if not answer or not contexts:
        return 0.0
    joined = " ".join(contexts)
    return _keyword_overlap(answer, joined)


def _context_recall(expected: str, contexts: list[str]) -> float:
    """期望答案字符与 contexts 的交集比率（recall：期望信息在 context 里能找到多少）。"""
    if not expected or not contexts:
        return 0.5
    joined = " ".join(contexts)
    return _keyword_overlap(expected, joined)


def _faithfulness(answer: str, contexts: list[str]) -> float:
    """Lightweight proxy：答案字符中有多少能在 context 中找到来源。"""
    return _context_precision(answer, contexts)


def _answer_relevancy(answer: str, query: str) -> float:
    """Lightweight proxy：答案与 query 的 keyword overlap。"""
    return _keyword_overlap(answer, query)


async def ragas_score(
    query: str,
    contexts: list[str],
    answer: str,
    expected_answer: str = "",
) -> dict[str, Any]:
    """计算 Ragas 4 指标。优先使用真实 ragas 包；不可用则走 keyword 轻量版。"""
    try:
        return await _ragas_real(query, contexts, answer, expected_answer)
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("real ragas failed, fallback to lightweight: %s", exc)

    return _ragas_lightweight(query, contexts, answer, expected_answer)


async def _ragas_real(
    query: str, contexts: list[str], answer: str, expected_answer: str
) -> dict[str, Any]:
    """调用真实 ragas 包计算指标（需要 LLM key）。"""
    from datasets import Dataset  # type: ignore[import]
    from ragas import evaluate  # type: ignore[import]
    from ragas.metrics import (  # type: ignore[import]
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    data = {
        "question": [query],
        "answer": [answer],
        "contexts": [contexts],
        "ground_truth": [expected_answer or answer],
    }
    ds = Dataset.from_dict(data)
    result = evaluate(ds, metrics=[context_precision, context_recall, faithfulness, answer_relevancy])
    scores = result.to_pandas().iloc[0].to_dict()
    overall = (
        scores.get("context_precision", 0.5) * 0.25
        + scores.get("context_recall", 0.5) * 0.25
        + scores.get("faithfulness", 0.5) * 0.25
        + scores.get("answer_relevancy", 0.5) * 0.25
    )
    return {
        "context_precision": float(scores.get("context_precision", 0)),
        "context_recall": float(scores.get("context_recall", 0)),
        "faithfulness": float(scores.get("faithfulness", 0)),
        "answer_relevancy": float(scores.get("answer_relevancy", 0)),
        "overall": float(overall),
        "source": "ragas",
    }


def _ragas_lightweight(
    query: str, contexts: list[str], answer: str, expected_answer: str
) -> dict[str, Any]:
    """不依赖 ragas 包的轻量版 4 指标（keyword overlap proxy）。"""
    cp = _context_precision(answer, contexts)
    cr = _context_recall(expected_answer or answer, contexts)
    fa = _faithfulness(answer, contexts)
    ar = _answer_relevancy(answer, query)
    overall = (cp + cr + fa + ar) / 4.0
    return {
        "context_precision": cp,
        "context_recall": cr,
        "faithfulness": fa,
        "answer_relevancy": ar,
        "overall": overall,
        "source": "lightweight_keyword",
    }


__all__ = ["ragas_score"]
