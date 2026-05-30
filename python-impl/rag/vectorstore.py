"""Qdrant 客户端封装：collection 管理 + payload filter 多租户。

设计.md §4.2 Qdrant schema：
- collection: kb_v1 (1024 dim)
- payload: {doc_id, doc_no, tenant_id, category, parent_text, chunk_text, effective_*}
- 检索时 must: tenant_id ∈ {current, NULL}
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from config import settings
from exceptions import BusinessException, ErrorCode

logger = logging.getLogger(__name__)


_client = None


def _get_client():
    """懒加载 Qdrant 客户端。

    若 Qdrant 不可达且处于 dev / test：自动使用内存版（QdrantClient(":memory:")），
    保证测试和本地开发不依赖外部服务。
    """
    global _client
    if _client is not None:
        return _client
    try:
        from qdrant_client import QdrantClient

        url = settings.QDRANT_URL
        if settings.is_test or os.environ.get("RAG_QDRANT_MEMORY") == "1":
            logger.info("using in-memory Qdrant client")
            _client = QdrantClient(":memory:")
        else:
            api_key = settings.QDRANT_API_KEY.get_secret_value() if settings.QDRANT_API_KEY else None
            _client = QdrantClient(url=url, api_key=api_key, timeout=10.0)
        return _client
    except Exception as exc:
        if settings.is_dev or settings.is_test:
            # 自动退回内存
            try:
                from qdrant_client import QdrantClient

                logger.warning("Qdrant remote failed, fallback to in-memory: %s", exc)
                _client = QdrantClient(":memory:")
                return _client
            except Exception:
                pass
        raise BusinessException(ErrorCode.RAG_VECTORSTORE_DOWN, message=str(exc)) from exc


@dataclass
class QdrantPoint:
    """upsert 用结构。"""

    point_id: str | int
    vector: list[float]
    payload: dict[str, Any]


def ensure_collection(name: str | None = None, vector_dim: int | None = None) -> None:
    """幂等创建 collection。"""
    from qdrant_client.http import models as rest
    from rag.embedder import get_dim

    client = _get_client()
    name = name or settings.RAG_COLLECTION
    vector_dim = vector_dim or get_dim()
    try:
        client.get_collection(name)
        return
    except Exception:
        pass
    client.create_collection(
        collection_name=name,
        vectors_config=rest.VectorParams(size=vector_dim, distance=rest.Distance.COSINE),
    )
    logger.info("created qdrant collection: %s (dim=%d)", name, vector_dim)


def upsert_points(points: list[QdrantPoint], collection: str | None = None) -> None:
    """批量 upsert。"""
    from qdrant_client.http import models as rest

    if not points:
        return
    client = _get_client()
    name = collection or settings.RAG_COLLECTION
    ensure_collection(name)
    payload_pts = [
        rest.PointStruct(id=_to_qdrant_id(p.point_id), vector=p.vector, payload=p.payload)
        for p in points
    ]
    client.upsert(collection_name=name, points=payload_pts, wait=True)


def _to_qdrant_id(raw: str | int) -> int:
    """Qdrant id 只接受 uint64 或 UUID。把字符串 id hash 成 64-bit int。"""
    if isinstance(raw, int):
        return raw
    import hashlib

    h = hashlib.sha1(raw.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") & ((1 << 63) - 1)


def search(
    query_vector: list[float],
    tenant_id: int | None,
    top_k: int,
    *,
    collection: str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """向量检索。tenant_id None / 全局文档默认全部可见；具体租户 → match (tenant_id or NULL)。

    返回 [{"score": float, "payload": {...}}]
    """
    from qdrant_client.http import models as rest

    client = _get_client()
    name = collection or settings.RAG_COLLECTION

    must: list[Any] = []
    if category:
        must.append(rest.FieldCondition(key="category", match=rest.MatchValue(value=category)))

    # tenant filter：当前 tenant_id 或全局（payload.tenant_id == None）
    tenant_filter = None
    if tenant_id is not None:
        tenant_filter = rest.Filter(
            should=[
                rest.FieldCondition(key="tenant_id", match=rest.MatchValue(value=tenant_id)),
                rest.IsNullCondition(is_null=rest.PayloadField(key="tenant_id")),
            ]
        )

    query_filter = None
    if must or tenant_filter:
        query_filter = rest.Filter(must=must)
        if tenant_filter:
            query_filter.should = tenant_filter.should
            # 注意：must + should 同时生效（should 内任一命中即可）

    try:
        # 优先用新版 API：query_points（1.10+）；老版兜底走 search
        if hasattr(client, "query_points"):
            resp = client.query_points(
                collection_name=name,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )
            hits = resp.points
        else:  # pragma: no cover
            hits = client.search(
                collection_name=name,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )
    except Exception as exc:
        logger.warning("qdrant search failed: %s", exc)
        return []

    return [
        {"score": float(h.score), "payload": h.payload or {}, "id": h.id}
        for h in hits
    ]


def collection_size(name: str | None = None) -> int:
    client = _get_client()
    try:
        info = client.get_collection(name or settings.RAG_COLLECTION)
        return int(info.points_count or 0)
    except Exception:
        return 0


def reset_client_for_tests() -> None:
    """测试用：重置 client（每个测试用独立内存实例）。"""
    global _client
    _client = None


__all__ = [
    "ensure_collection",
    "upsert_points",
    "search",
    "collection_size",
    "QdrantPoint",
    "reset_client_for_tests",
]
