"""W1 多租户隔离测试（5 用例）。

覆盖：
- tenant_context ContextVar 行为
- skip_tenant_filter 上下文管理器（含 reason 必填）
- Qdrant payload 过滤（vectorstore.search）
- BM25 过滤（retriever._bm25_search 仅返回当前 tenant + 全局）
- /api/v1/chat SSE 端点带 X-Tenant-Id 时不泄漏跨租户内容
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from db import (
    current_tenant_id,
    is_tenant_filter_skipped,
    set_current_tenant,
    skip_filter_reason,
    skip_tenant_filter,
)
from rag import embedder, loader, retriever, vectorstore


@pytest.fixture(autouse=True)
def _reset_state():
    """每个用例独立内存 Qdrant + 清空 BM25 + 清空 tenant context。"""
    vectorstore.reset_client_for_tests()
    retriever._bm25_index = None  # type: ignore[attr-defined]
    set_current_tenant(None, None)
    yield
    vectorstore.reset_client_for_tests()
    set_current_tenant(None, None)


def _seed_multi_tenant_kb(tmp_path: Path) -> None:
    """灌入：全局 + 租户1 + 租户2 各 1 篇，文本可区分。"""
    docs_def = [
        ("KB-G-X01", "全局退款政策", "自营商品 7 天无理由退换货。", None),
        ("KB-A-X01", "租户A售后专属", "TENANT_A VIP 用户 2 小时响应。", 1),
        ("KB-B-X01", "租户B售后专属", "TENANT_B 商品支持 30 天无理由退换。", 2),
    ]
    for doc_no, title, body, tid in docs_def:
        fm = ["---", f"doc_no: {doc_no}", f"title: {title}", "category: refund"]
        if tid is not None:
            fm.append(f"tenant_id: {tid}")
        fm.extend(["effective_from: 2026-01-01", "effective_to: 2027-12-31", "---", ""])
        md = "\n".join(fm) + f"# {title}\n\n{body}\n"
        (tmp_path / f"{doc_no}.md").write_text(md, encoding="utf-8")

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
                        "doc_id": c.doc_id, "doc_no": c.doc_no,
                        "title": c.title, "category": c.category,
                        "tenant_id": c.tenant_id,
                        "parent_text": c.parent_text, "chunk_text": c.chunk_text,
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


# ---------- 1. ContextVar + skip_tenant_filter 行为 ----------
def test_skip_tenant_filter_requires_reason_and_resets():
    set_current_tenant(1, "tenant-a")
    assert current_tenant_id() == 1
    assert not is_tenant_filter_skipped()

    # reason 必填
    with pytest.raises(ValueError):
        with skip_tenant_filter(""):
            pass

    with skip_tenant_filter("ingest_kb 全租户写入"):
        assert is_tenant_filter_skipped()
        assert skip_filter_reason() == "ingest_kb 全租户写入"

    # 离开 with 后状态自动恢复
    assert not is_tenant_filter_skipped()
    assert skip_filter_reason() is None
    assert current_tenant_id() == 1


# ---------- 2. Qdrant 向量检索严格按 payload 过滤 ----------
def test_vectorstore_excludes_other_tenant_payload(tmp_path: Path):
    _seed_multi_tenant_kb(tmp_path)

    # 用 tenant A (id=1) 检索一个 "TENANT_B" 特征词
    qvec = embedder.embed_one("TENANT_B 30 天无理由")
    hits_a = vectorstore.search(query_vector=qvec, tenant_id=1, top_k=20)
    doc_nos_a = {h["payload"]["doc_no"] for h in hits_a}
    assert "KB-B-X01" not in doc_nos_a, "租户 A 不应看到租户 B 的文档"

    # 用 tenant B (id=2) 反之
    hits_b = vectorstore.search(query_vector=qvec, tenant_id=2, top_k=20)
    doc_nos_b = {h["payload"]["doc_no"] for h in hits_b}
    assert "KB-A-X01" not in doc_nos_b


# ---------- 3. retriever 混合检索结果不混入跨租户 ----------
def test_retriever_hybrid_excludes_cross_tenant(tmp_path: Path):
    _seed_multi_tenant_kb(tmp_path)

    chunks_a = retriever.hybrid_retrieve(query="售后", tenant_id=1)
    for c in chunks_a:
        assert c.tenant_id in (None, 1), f"租户 A 命中跨租户文档：{c.doc_no} tenant={c.tenant_id}"

    chunks_b = retriever.hybrid_retrieve(query="售后", tenant_id=2)
    for c in chunks_b:
        assert c.tenant_id in (None, 2), f"租户 B 命中跨租户文档：{c.doc_no} tenant={c.tenant_id}"


# ---------- 4. BM25 索引按 tenant 过滤 ----------
def test_bm25_search_filters_by_tenant(tmp_path: Path):
    _seed_multi_tenant_kb(tmp_path)

    # 直接打到内部 BM25 search，绕过向量
    paired_a = retriever._bm25_search(  # type: ignore[attr-defined]
        query="TENANT_B 30 天", top_k=10, tenant_id=1,
    )
    doc_nos = {d.get("doc_no") for _, d in paired_a}
    assert "KB-B-X01" not in doc_nos
    # 全局文档对所有租户可见
    paired_global = retriever._bm25_search(  # type: ignore[attr-defined]
        query="7 天无理由", top_k=10, tenant_id=2,
    )
    doc_nos_g = {d.get("doc_no") for _, d in paired_global}
    assert "KB-G-X01" in doc_nos_g
    # 租户 1 的文档对租户 2 不可见
    assert "KB-A-X01" not in doc_nos_g


# ---------- 5. /api/v1/chat SSE 端点带 X-Tenant-Id 时不泄漏跨租户 ----------
def test_api_chat_streams_with_tenant_header(tmp_path: Path):
    _seed_multi_tenant_kb(tmp_path)

    # 延迟导入：保证 conftest 已设置 APP_ENV=test
    from api.main import app
    from auth.jwt import create_access_token

    token = create_access_token(user_id=1, tenant_id=1, roles=["customer"], permissions=["chat:send"])

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/chat",
            headers={
                "X-Tenant-Id": "tenant-a",
                "Accept": "text/event-stream",
                "Authorization": f"Bearer {token}",
            },
            json={"messages": [{"role": "user", "content": "我要了解售后政策"}], "version": "v3"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.text

    # SSE 协议字段
    assert "event: start" in body
    assert "event: done" in body or "event: no_match" in body or "event: error" in body

    # 收集所有 citation 事件，断言不含 tenant B 专属 doc_no
    cit_doc_nos: set[str] = set()
    for frame in body.split("\n\n"):
        if "event: citation" not in frame:
            continue
        for line in frame.split("\n"):
            if line.startswith("data:"):
                try:
                    payload = json.loads(line[5:].strip())
                    cit_doc_nos.add(payload.get("doc_no", ""))
                except json.JSONDecodeError:
                    pass
    assert "KB-B-X01" not in cit_doc_nos, f"tenant-a 看到了 tenant-b 的引用：{cit_doc_nos}"
