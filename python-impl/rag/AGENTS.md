# rag/ · 检索增强生成 AGENTS.md

> RAG 流水线：loader → embedder → vectorstore → retriever → reranker → answer_gen。W1 建模块；后续仅扩展。

---

## 1. 模块组成

| 文件 | 职责 |
|---|---|
| `loader.py` | Markdown 解析 + frontmatter + 父子切片（父 2k chars / 子 400 chars / overlap 200） |
| `embedder.py` | bge-large-zh-v1.5 包装；批量/流式两种调用 |
| `vectorstore.py` | Qdrant 客户端封装；单 collection `kb_v1` + payload filter 多租户 |
| `retriever.py` | 混合检索：向量 top20 + BM25 (rank_bm25 + jieba) top20 → 合并去重 |
| `reranker.py` | bge-reranker-v2-m3；阈值 0.3 决定整体相关性 |
| `query_rewriter.py` | 轻量模型把口语化 query 改写 2 个变体 |
| `answer_generator.py` | 父片拼接 → medium 模型 → 流式生成 + 引用标记 |

---

## 2. 数据契约

- 索引输入：`docs/knowledge_base/{global,tenant_a,tenant_b}/*.md`（frontmatter: doc_no/title/category/tenant_id?/effective_from/effective_to）
- Qdrant payload：`{doc_id, doc_no, tenant_id (nullable=全局), category, parent_text, chunk_text, effective_*}`
- 检索输出 `Chunk`（rag/retriever.py 中 `pydantic.BaseModel`）：
  ```python
  class Chunk(BaseModel):
      doc_id: str
      doc_no: str
      title: str
      parent_text: str
      chunk_text: str
      chunk_id: str
      score: float
      tenant_id: int | None = None
      category: str | None = None
  ```

---

## 3. 不变量

- 检索时**必须**带 `tenant_id ∈ (current, NULL)` 的 payload filter；漏带视为安全漏洞
- LLM 调用走 `llm.router`，profile=light（rewriter）/ medium（answer）
- 父片在拼接前去重（同 doc_id 合并相邻 chunk）
- Reranker 阈值低于 0.3 → 返回"未在政策中找到" 而非编造

---

## 4. 评测口径

- Top1 准确率 ≥ 80%（`docs/eval/datasets/rag.jsonl` 50 条）
- 引用一致率 ≥ 95%（答案中提到的事实在引用块里能找到）
- 整体由 `eval/judges/ragas_judge.py` 跑 Ragas 4 指标

---

## 5. 灌库脚本

- `scripts/generate_kb.py` — 模板拼接生成 W1 演示用 KB（15 全局 + 3 tenant_a + 3 tenant_b），不调真实 LLM
- `scripts/ingest_kb.py` — 解析 + 切片 + embed + upsert 到 Qdrant + 元数据写 PG + 顺手构建 BM25

```bash
# 生成种子文档
python -m scripts.generate_kb
# 灌库（Qdrant + PG + BM25）
python -m scripts.ingest_kb --kb ../docs/knowledge_base
```

---

## 6. 测试

W1 在 `python-impl/tests/` 下提供 RAG 单测（共 6 用例）：

| 文件 | 用例 |
|---|---|
| `test_rag.py` | loader 父子切片 / embedder 归一化 / vectorstore tenant 过滤 / retriever 混合检索 / answer_generator 流式 + 引用 / 空召回兜底 |
| `test_tenant_isolation.py` | ContextVar + skip_tenant_filter / Qdrant payload 隔离 / hybrid 跨租户不泄漏 / BM25 tenant 过滤 / /api/v1/chat SSE 端到端隔离 |

```bash
cd python-impl && python -m pytest tests/ -v
# 11 passed
```

无外部依赖：Qdrant 走 `:memory:`、embedder/reranker 走 hashing/lexical fallback、LLM 走 echo provider。

---

## 7. 变更记录

| 日期 | 摘要 |
|---|---|
| 2026-05-25 | 占位，W1 落地 |
| 2026-05-26 | W1.8 完成：6 用例 RAG + 5 用例租户隔离全绿；Chunk 契约同步；rebuild_bm25 接受 Chunk/dict 归一化 |
