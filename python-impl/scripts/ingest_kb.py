"""KB 灌库：扫描 docs/knowledge_base/*.md → 切片 → 向量化 → upsert Qdrant + 写 PG。

幂等：相同 doc_no 重复执行只覆盖；以 chunk_id 作 point_id。
独立可执行：python -m scripts.ingest_kb --kb docs/knowledge_base
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from config import settings
from db import KnowledgeDoc, async_session, skip_tenant_filter
from rag import embedder, loader, retriever, vectorstore

logger = logging.getLogger(__name__)


async def _upsert_pg_metadata(docs: list[loader.LoadedDoc], chunk_counts: dict[str, int]) -> int:
    """把文档级元数据写入 PG。失败不阻塞（用于无 PG 的本地演示）。"""
    from datetime import datetime

    from sqlalchemy import select

    def _to_dt(v: str | None) -> datetime | None:
        if not v:
            return None
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None

    try:
        async with async_session() as session, skip_tenant_filter("ingest_kb 全租户写入"):
            n = 0
            for d in docs:
                stmt = select(KnowledgeDoc).where(KnowledgeDoc.doc_no == d.doc_no)
                res = await session.execute(stmt)
                row = res.scalar_one_or_none()
                if row is None:
                    row = KnowledgeDoc(doc_no=d.doc_no)
                    session.add(row)
                row.title = d.title
                row.category = d.category
                row.tenant_id = d.tenant_id
                row.effective_from = _to_dt(d.effective_from)
                row.effective_to = _to_dt(d.effective_to)
                row.raw_path = d.raw_path or ""
                row.chunk_count = chunk_counts.get(d.doc_no, 0)
                n += 1
            await session.commit()
            return n
    except Exception as exc:
        logger.warning("PG metadata upsert skipped (db unavailable?): %s", exc)
        return 0


def _build_points(docs: list[loader.LoadedDoc]) -> list[vectorstore.QdrantPoint]:
    """向量化所有子片 → QdrantPoint。"""
    points: list[vectorstore.QdrantPoint] = []
    texts = []
    metas = []
    for d in docs:
        for c in d.child_chunks:
            texts.append(c.chunk_text)
            metas.append(c)

    if not texts:
        return points

    logger.info("embedding %d chunks (model=%s, fallback=%s)",
                len(texts), settings.RAG_EMBEDDING_MODEL, settings.RAG_USE_LOCAL_FALLBACK)
    vectors = embedder.embed_batch(texts)

    for vec, c in zip(vectors, metas):
        payload = {
            "doc_id": c.doc_id,
            "doc_no": c.doc_no,
            "title": c.title,
            "category": c.category,
            "tenant_id": c.tenant_id,  # None 表示全局
            "parent_text": c.parent_text,
            "chunk_text": c.chunk_text,
            "effective_from": c.effective_from,
            "effective_to": c.effective_to,
        }
        points.append(vectorstore.QdrantPoint(point_id=c.chunk_id, vector=list(vec), payload=payload))
    return points


def _build_bm25(docs: list[loader.LoadedDoc]) -> int:
    """灌库时顺手构建 BM25 索引（in-memory，进程重启需重建）。"""
    chunks: list[retriever.Chunk] = []
    for d in docs:
        for c in d.child_chunks:
            chunks.append(
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
    retriever.rebuild_bm25(chunks)
    return len(chunks)


async def ingest(kb_dir: Path) -> dict:
    docs = loader.load_directory(kb_dir)
    logger.info("loaded %d docs from %s", len(docs), kb_dir)
    if not docs:
        return {"docs": 0, "chunks": 0, "qdrant": 0, "pg": 0, "bm25": 0}

    points = _build_points(docs)
    vectorstore.ensure_collection()
    vectorstore.upsert_points(points)
    qdrant_size = vectorstore.collection_size()

    bm25_n = _build_bm25(docs)

    chunk_counts: dict[str, int] = {}
    for d in docs:
        chunk_counts[d.doc_no] = len(d.child_chunks)
    pg_n = await _upsert_pg_metadata(docs, chunk_counts)

    return {
        "docs": len(docs),
        "chunks": len(points),
        "qdrant": qdrant_size,
        "pg": pg_n,
        "bm25": bm25_n,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb", default=settings.KB_DIR, help="知识库目录")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    stats = asyncio.run(ingest(Path(args.kb)))
    print(f"[ingest_kb] {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
