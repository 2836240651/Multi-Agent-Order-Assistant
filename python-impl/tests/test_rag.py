"""W1 RAG 单元测试（5 用例，覆盖 loader / embedder / vectorstore / retriever / answer_generator）。

所有用例不依赖外部服务：
- Qdrant：用内存版（APP_ENV=test 触发 :memory: 客户端，见 vectorstore._get_client）
- LLM：echo provider 兜底（路由器内置）
- 嵌入：hashing fallback（RAG_USE_LOCAL_FALLBACK=true）
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from config import settings
from rag import (
    answer_generator,
    embedder,
    loader,
    retriever,
    vectorstore,
)


@pytest.fixture(autouse=True)
def _reset_vectorstore():
    """每个用例独立内存 Qdrant + 清空 BM25。"""
    vectorstore.reset_client_for_tests()
    retriever._bm25_index = None  # type: ignore[attr-defined]
    yield
    vectorstore.reset_client_for_tests()


def _write_doc(tmp_path: Path, doc_no: str, title: str, body: str, *, tenant_id: int | None = None, category: str = "refund") -> Path:
    fm = ["---", f"doc_no: {doc_no}", f"title: {title}", f"category: {category}"]
    if tenant_id is not None:
        fm.append(f"tenant_id: {tenant_id}")
    fm.extend(["effective_from: 2026-01-01", "effective_to: 2027-12-31", "---", ""])
    md = "\n".join(fm) + f"# {title}\n\n{body}\n"
    p = tmp_path / f"{doc_no}.md"
    p.write_text(md, encoding="utf-8")
    return p


# ---------- 1. loader：frontmatter + 父子切片 ----------
def test_loader_parses_frontmatter_and_splits_parent_child(tmp_path: Path):
    body = "适用于自营商品。" * 60  # ~480 字，应至少产 1 父片 + 多个子片
    _write_doc(tmp_path, "KB-T-001", "7 天无理由", body, tenant_id=1)

    docs = loader.load_directory(tmp_path)
    assert len(docs) == 1
    d = docs[0]
    assert d.doc_no == "KB-T-001"
    assert d.title == "7 天无理由"
    assert d.category == "refund"
    assert d.tenant_id == 1
    assert d.effective_from is not None
    assert d.parent_chunks, "至少 1 个父片"
    assert d.child_chunks, "至少 1 个子片"
    # 子片继承父片元数据
    c0 = d.child_chunks[0]
    assert c0.doc_no == "KB-T-001"
    assert c0.tenant_id == 1
    assert c0.chunk_id.startswith("KB-T-001::")
    # 子片长度不应超过子片设置（带 strip）
    assert all(len(c.chunk_text) <= settings.RAG_CHILD_CHARS for c in d.child_chunks)


# ---------- 2. embedder：hashing fallback 维度 + 归一化 ----------
def test_embedder_fallback_produces_normalized_vectors():
    vecs = embedder.embed_batch(["7 天无理由退货吗", "运费谁出"])
    assert len(vecs) == 2
    for v in vecs:
        assert len(v) == settings.RAG_EMBED_DIM
        norm_sq = sum(x * x for x in v)
        # 归一化向量模长 ≈ 1（含 0 向量边界情况）
        assert 0.99 < norm_sq < 1.01

    # 同输入 → 同向量（可重复性）
    a = embedder.embed_one("退款几天到账")
    b = embedder.embed_one("退款几天到账")
    assert a == b


# ---------- 3. vectorstore：upsert + 按 tenant_id 过滤 ----------
def test_vectorstore_search_filters_by_tenant_payload(tmp_path: Path):
    _write_doc(tmp_path, "KB-G-T01", "全局退款", "全局适用 7 天无理由。", tenant_id=None)
    _write_doc(tmp_path, "KB-A-T01", "租户 A 专属", "VIP 用户绿色通道 2 小时响应。", tenant_id=1)
    _write_doc(tmp_path, "KB-B-T01", "租户 B 专属", "B 店 30 天无理由退换。", tenant_id=2)
    docs = loader.load_directory(tmp_path)

    points: list[vectorstore.QdrantPoint] = []
    for d in docs:
        for c in d.child_chunks:
            vec = embedder.embed_one(c.chunk_text)
            points.append(
                vectorstore.QdrantPoint(
                    point_id=c.chunk_id,
                    vector=vec,
                    payload={
                        "doc_id": c.doc_id,
                        "doc_no": c.doc_no,
                        "title": c.title,
                        "category": c.category,
                        "tenant_id": c.tenant_id,
                        "parent_text": c.parent_text,
                        "chunk_text": c.chunk_text,
                    },
                )
            )
    vectorstore.upsert_points(points)
    assert vectorstore.collection_size() == len(points)

    # 用 tenant_id=1 检索：应只看到 全局 + A，看不到 B
    qvec = embedder.embed_one("退款")
    hits = vectorstore.search(query_vector=qvec, tenant_id=1, top_k=20)
    tenants_seen = {h["payload"].get("tenant_id") for h in hits}
    assert 2 not in tenants_seen, f"租户 1 看到了租户 2 的数据：{tenants_seen}"
    assert {1, None} & tenants_seen


# ---------- 4. retriever：混合检索 + RRF ----------
def test_retriever_hybrid_returns_chunks_for_tenant(tmp_path: Path):
    _write_doc(tmp_path, "KB-G-T02", "运费规则", "下单满 99 元包邮（偏远地区除外）。", tenant_id=None)
    docs = loader.load_directory(tmp_path)
    points = []
    bm25_chunks: list[retriever.Chunk] = []
    for d in docs:
        for c in d.child_chunks:
            points.append(
                vectorstore.QdrantPoint(
                    point_id=c.chunk_id,
                    vector=embedder.embed_one(c.chunk_text),
                    payload={
                        "doc_id": c.doc_id,
                        "doc_no": c.doc_no,
                        "title": c.title,
                        "category": c.category,
                        "tenant_id": c.tenant_id,
                        "parent_text": c.parent_text,
                        "chunk_text": c.chunk_text,
                        "chunk_id": c.chunk_id,
                    },
                )
            )
            bm25_chunks.append(
                retriever.Chunk(
                    doc_id=c.doc_id, doc_no=c.doc_no, title=c.title,
                    parent_text=c.parent_text, chunk_text=c.chunk_text,
                    chunk_id=c.chunk_id, score=0.0, tenant_id=c.tenant_id,
                    category=c.category,
                )
            )
    vectorstore.upsert_points(points)
    retriever.rebuild_bm25(bm25_chunks)

    chunks = retriever.hybrid_retrieve(query="包邮门槛是多少", tenant_id=1)
    assert chunks, "混合检索至少应返回 1 条命中"
    top = chunks[0]
    assert isinstance(top, retriever.Chunk)
    assert top.doc_no == "KB-G-T02"
    assert top.tenant_id is None  # 全局文档


# ---------- 5. answer_generator：流式 token + citation 事件 ----------
def test_answer_generator_streams_citation_then_tokens():
    chunks = [
        retriever.Chunk(
            doc_id="KB-G-T03", doc_no="KB-G-T03", title="7 天无理由退货",
            parent_text="自营商品支持 7 天无理由退换。", chunk_text="7 天无理由",
            chunk_id="KB-G-T03::p0-c00", score=0.8, tenant_id=None, category="refund",
        )
    ]

    async def _collect():
        events = []
        async for ev in answer_generator.stream_answer("7 天无理由怎么算", chunks):
            events.append(ev)
        return events

    events = asyncio.run(_collect())
    types = [e.type for e in events]
    assert types[0] == "citation", "首事件必须是 citation"
    assert "token" in types, "至少 1 个 token 事件"
    assert types[-1] in {"done", "error"}, "最后是 done 或 error"
    # citation 内容契约
    cit = events[0].data
    assert cit["id"].startswith("cit_")
    assert cit["doc_no"] == "KB-G-T03"
    assert cit["chunk_id"] == "KB-G-T03::p0-c00"


# ---------- 兜底：无召回 → no_match ----------
def test_answer_generator_no_match_when_empty_chunks():
    async def _collect():
        return [ev async for ev in answer_generator.stream_answer("xxx", [])]

    events = asyncio.run(_collect())
    assert len(events) == 1
    assert events[0].type == "no_match"
    assert "未在政策中找到" in events[0].data.get("text", "")
