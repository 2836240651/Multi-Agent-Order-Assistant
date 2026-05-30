"""rag/bootstrap.py：评测/测试环境 KB 索引幂等加载（内存 Qdrant + BM25）。

在 APP_ENV=test 或显式调用时，将 docs/knowledge_base 灌入进程内索引，
避免 eval runner 因空索引导致 RAG/e2e 空回答。
"""
from __future__ import annotations

import logging
from pathlib import Path

from config import settings
from rag import embedder, loader, retriever, vectorstore

logger = logging.getLogger(__name__)

_BOOTSTRAPPED = False
_DEFAULT_KB = Path(__file__).resolve().parents[2] / "docs" / "knowledge_base"


def _kb_dir() -> Path:
    env = settings.__dict__.get("KB_DIR")  # optional future setting
    if env:
        return Path(str(env))
    return _DEFAULT_KB


def ensure_kb_indexed(*, kb_dir: Path | None = None, force: bool = False) -> dict:
    """幂等灌库：加载 Markdown → Qdrant（内存）+ BM25。"""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED and not force:
        return {"skipped": True, "chunks": vectorstore.collection_size()}

    kb_path = kb_dir or _kb_dir()
    if not kb_path.is_dir():
        logger.warning("KB directory missing: %s", kb_path)
        return {"skipped": True, "error": "kb_dir_missing"}

    vectorstore.reset_client_for_tests()
    retriever._bm25_index = None  # type: ignore[attr-defined]

    docs = loader.load_directory(kb_path)
    if not docs:
        return {"docs": 0, "chunks": 0}

    texts: list[str] = []
    metas = []
    for d in docs:
        for c in d.child_chunks:
            texts.append(c.chunk_text)
            metas.append(c)

    vectors = embedder.embed_batch(texts)
    points: list[vectorstore.QdrantPoint] = []
    bm25_chunks: list[retriever.Chunk] = []
    for vec, c in zip(vectors, metas):
        payload = {
            "doc_id": c.doc_id,
            "doc_no": c.doc_no,
            "title": c.title,
            "category": c.category,
            "tenant_id": c.tenant_id,
            "parent_text": c.parent_text,
            "chunk_text": c.chunk_text,
            "chunk_id": c.chunk_id,
            "effective_from": c.effective_from,
            "effective_to": c.effective_to,
        }
        points.append(
            vectorstore.QdrantPoint(point_id=c.chunk_id, vector=list(vec), payload=payload)
        )
        bm25_chunks.append(
            retriever.Chunk(
                doc_id=c.doc_id,
                doc_no=c.doc_no,
                title=c.title,
                parent_text=c.parent_text,
                chunk_text=c.chunk_text,
                chunk_id=c.chunk_id,
                score=0.0,
                tenant_id=c.tenant_id,
                category=c.category,
            )
        )

    vectorstore.upsert_points(points)
    retriever.rebuild_bm25(bm25_chunks)
    _BOOTSTRAPPED = True
    n = len(points)
    logger.info("KB bootstrap: %d docs, %d chunks from %s", len(docs), n, kb_path)
    return {"docs": len(docs), "chunks": n, "qdrant": n, "bm25": n}


def reset_bootstrap_flag() -> None:
    """测试用：允许下次重新灌库。"""
    global _BOOTSTRAPPED
    _BOOTSTRAPPED = False


__all__ = ["ensure_kb_indexed", "reset_bootstrap_flag"]
