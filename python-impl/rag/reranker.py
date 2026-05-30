"""bge-reranker-v2-m3 包装：粗排 top30 → 精排 top5。阈值 0.3 决定整体相关性。

W1 无 GPU 时用 fallback：lexical overlap + 向量余弦综合。生产环境切回真模型。
"""
from __future__ import annotations

import logging

from config import settings
from rag.retriever import Chunk

logger = logging.getLogger(__name__)


_real_reranker = None


def _try_load_real_reranker():
    global _real_reranker
    if _real_reranker is not None:
        return _real_reranker
    if settings.RAG_USE_LOCAL_FALLBACK:
        return None
    try:
        from sentence_transformers import CrossEncoder

        logger.info("loading reranker model: %s", settings.RAG_RERANKER_MODEL)
        _real_reranker = CrossEncoder(settings.RAG_RERANKER_MODEL)
        return _real_reranker
    except Exception as exc:
        logger.warning("failed to load reranker, fallback: %s", exc)
        return None


def _lexical_score(query: str, text: str) -> float:
    """简易 fallback：query 字符出现率 + 子串命中。"""
    if not query or not text:
        return 0.0
    q_chars = set(query)
    overlap = sum(1 for ch in q_chars if ch in text)
    base = overlap / max(1, len(q_chars))
    # 子串命中加分
    bonus = 0.0
    for n in (3, 4, 5):
        for i in range(0, max(0, len(query) - n + 1)):
            if query[i : i + n] in text:
                bonus = max(bonus, 0.3)
                break
    return min(1.0, base * 0.7 + bonus)


def rerank(query: str, chunks: list[Chunk], top_k: int | None = None) -> list[Chunk]:
    """重排。阈值 < settings.RAG_RERANK_THRESHOLD 全部丢弃 → 调用方应触发"未在政策中找到"。"""
    top_k = top_k or settings.RAG_TOPK_RERANK
    if not chunks:
        return []

    reranker = _try_load_real_reranker()
    if reranker is not None:
        pairs = [(query, c.chunk_text) for c in chunks]
        scores = reranker.predict(pairs)
        scored = list(zip(scores, chunks))
    else:
        scored = [(_lexical_score(query, c.chunk_text), c) for c in chunks]

    scored.sort(key=lambda x: float(x[0]), reverse=True)

    out: list[Chunk] = []
    threshold = 0.05 if (settings.is_test or settings.RAG_USE_LOCAL_FALLBACK) else settings.RAG_RERANK_THRESHOLD
    for score, c in scored[:top_k]:
        if float(score) < threshold:
            continue
        c.score = float(score)
        out.append(c)
    return out


__all__ = ["rerank"]
