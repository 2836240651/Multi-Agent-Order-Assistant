"""混合检索：向量 top20 + BM25 top20，按 RRF 合并去重。

BM25 在内存维护索引。生产环境可换 ES，但 W1 用 rank_bm25 + jieba 足够。
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from config import settings
from db import current_tenant_id
from rag import embedder, vectorstore

logger = logging.getLogger(__name__)


class Chunk(BaseModel):
    """检索结果。rag/AGENTS.md §2 契约。"""

    doc_id: str
    doc_no: str
    title: str
    parent_text: str
    chunk_text: str
    chunk_id: str
    score: float
    tenant_id: int | None = None
    category: str | None = None


@dataclass
class _BM25Index:
    """内存 BM25 索引。按 (tenant_id, None) 联合存。"""

    docs: list[dict[str, Any]]
    tokenized: list[list[str]]
    bm25: Any  # rank_bm25.BM25Okapi instance


_bm25_lock = threading.Lock()
_bm25_index: _BM25Index | None = None


def _tokenize(text: str) -> list[str]:
    import jieba

    return [t for t in jieba.lcut(text) if t.strip()]


def rebuild_bm25(chunks: list[Any]) -> None:
    """触发 BM25 重建。chunks 可为 dict 或 retriever.Chunk（自动归一化）。"""
    from rank_bm25 import BM25Okapi

    normalized: list[dict[str, Any]] = []
    for c in chunks:
        if isinstance(c, Chunk):
            normalized.append(c.model_dump())
        elif isinstance(c, dict):
            normalized.append(c)
        else:
            # 兜底：dataclass / 普通对象
            normalized.append({k: getattr(c, k, None) for k in (
                "doc_id", "doc_no", "title", "parent_text", "chunk_text",
                "chunk_id", "tenant_id", "category",
            )})

    tokenized = [_tokenize(d.get("chunk_text") or "") for d in normalized]
    if not tokenized:
        logger.warning("rebuild_bm25 called with empty chunks")
        return
    bm25 = BM25Okapi(tokenized)
    global _bm25_index
    with _bm25_lock:
        _bm25_index = _BM25Index(docs=normalized, tokenized=tokenized, bm25=bm25)
    logger.info("BM25 index rebuilt with %d chunks", len(normalized))


def _bm25_search(query: str, top_k: int, tenant_id: int | None) -> list[tuple[float, dict[str, Any]]]:
    if _bm25_index is None:
        return []
    tokens = _tokenize(query)
    scores = _bm25_index.bm25.get_scores(tokens)
    paired = [
        (float(s), doc)
        for s, doc in zip(scores, _bm25_index.docs)
        if doc.get("tenant_id") in (None, tenant_id)
    ]
    paired.sort(key=lambda x: x[0], reverse=True)
    return paired[:top_k]


def _rrf_merge(
    vector_hits: list[tuple[float, dict[str, Any]]],
    bm25_hits: list[tuple[float, dict[str, Any]]],
    k: int = 60,
) -> list[tuple[float, dict[str, Any]]]:
    """Reciprocal Rank Fusion，合并去重。"""
    fused: dict[str, dict[str, Any]] = {}
    scores: dict[str, float] = {}
    for rank, (_, doc) in enumerate(vector_hits):
        key = doc.get("chunk_id") or f"{doc['doc_id']}-{rank}"
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
        fused[key] = doc
    for rank, (_, doc) in enumerate(bm25_hits):
        key = doc.get("chunk_id") or f"{doc['doc_id']}-{rank}"
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
        fused.setdefault(key, doc)
    out = [(scores[k_], fused[k_]) for k_ in fused]
    out.sort(key=lambda x: x[0], reverse=True)
    return out


def hybrid_retrieve(
    query: str,
    tenant_id: int | None = None,
    top_k_vector: int | None = None,
    top_k_bm25: int | None = None,
    *,
    category: str | None = None,
) -> list[Chunk]:
    """混合检索入口。tenant_id 未传则从 ContextVar 取。"""
    if tenant_id is None:
        tenant_id = current_tenant_id()
    top_k_vector = top_k_vector or settings.RAG_TOPK_VECTOR
    top_k_bm25 = top_k_bm25 or settings.RAG_TOPK_BM25

    # BM25 检索（评测/本地 fallback 时为主力）
    bm25_hits = _bm25_search(query, top_k=top_k_bm25, tenant_id=tenant_id)

    vector_hits: list[tuple[float, dict[str, Any]]] = []
    if not settings.is_test and not settings.RAG_USE_LOCAL_FALLBACK:
        query_vec = embedder.embed_one(query)
        vector_raw = vectorstore.search(
            query_vector=query_vec, tenant_id=tenant_id, top_k=top_k_vector, category=category
        )
        vector_hits = [(h["score"], h["payload"]) for h in vector_raw]

    fused = _rrf_merge(vector_hits, bm25_hits) if vector_hits else bm25_hits
    chunks: list[Chunk] = []
    for score, payload in fused:
        try:
            chunks.append(
                Chunk(
                    doc_id=str(payload.get("doc_id") or payload.get("doc_no") or ""),
                    doc_no=str(payload.get("doc_no", "")),
                    title=str(payload.get("title", "")),
                    parent_text=str(payload.get("parent_text", "")),
                    chunk_text=str(payload.get("chunk_text", "")),
                    chunk_id=str(payload.get("chunk_id", "")),
                    score=float(score),
                    tenant_id=payload.get("tenant_id"),
                    category=payload.get("category"),
                )
            )
        except Exception as exc:
            logger.warning("retriever skip malformed payload: %s", exc)
            continue
    return chunks


def get_bm25_index() -> _BM25Index | None:
    return _bm25_index


__all__ = ["Chunk", "hybrid_retrieve", "rebuild_bm25", "get_bm25_index"]
