# eval/ · 评测体系 AGENTS.md

> 5 维度评测 + LLM-as-Judge + Ragas 指标 + Markdown/图表报告。W2 落地。

---

## 1. 模块组成

| 路径 | 职责 |
|---|---|
| `datasets/intent.jsonl` | 意图识别 50 条 |
| `datasets/tool_call.jsonl` | 工具调用 40 条（参数完整性） |
| `datasets/rag.jsonl` | 知识问答 50 条（含 ground truth + 应引用 doc_no） |
| `datasets/risk.jsonl` | 风控 30 条（含正常 / 边缘 / 攻击） |
| `datasets/e2e.jsonl` | 端到端业务 30 条 |
| `judges/exact_match.py` | 精确匹配（`judge_intent` / `judge_tool_call` / `judge_risk_decision`） |
| `judges/ragas_judge.py` | Ragas 4 指标（context_precision/recall/faithfulness/answer_relevancy），有 ragas 包时走真实计算，否则 keyword overlap 轻量版 |
| `judges/llm_judge.py` | LLM-as-Judge（`judge_rag` / `judge_e2e`），失败降级为 0.5 |
| `runner.py` | 加载数据集 → 分类派发 runner → 并发评测（asyncio.Semaphore） → 聚合结果 |
| `report.py` | Markdown 报告 + matplotlib 折线/柱状图（未安装 matplotlib 则静默跳过） |

---

## 2. 数据契约

```json
{
  "id": "rag-001",
  "category": "rag",
  "input": {"query": "...", "tenant_id": 1},
  "expected": {
    "answer_contains": ["关键词1"],
    "citations": ["KB-G-001"]
  },
  "metadata": {"difficulty": "easy", "source": "manual"}
}
```

不同 category 的 expected schema：

| category | expected 字段 |
|---|---|
| intent | `intent` |
| rag | `answer_contains`, `citations` |
| tool_call | `tool`, `args_contains` |
| risk | `decision`, `score_lt` / `score_gte` |
| e2e | `intent`, `answer_contains`, `has_citations` |

---

## 3. 评分公式

**RAG 用例**：`score = keyword_match×0.5 + cit_hit×0.2 + ragas_overall×0.3`；pass 条件 `score≥0.5 且 cit_hit>0`（有期望引用时）

**Intent 用例**：精确匹配，1.0/0.0

**E2E 用例**：`score = keyword_overall×0.6 + intent_ok×0.2 + cit_ok×0.2`；pass 条件 `score≥0.5 且 intent_ok`

---

## 4. 用法

```bash
# 全量 200 条
make eval

# smoke（每数据集 10 条，CI 专用）
python -m eval.runner --smoke

# 单类别
python -m eval.runner --dataset rag --sample 20

# 输出 JSON + Markdown 报告
python -m eval.runner --all --output results.json --report
```

---

## 5. 不变量

- 数据集变更走 PR，禁止直接 push
- LLM judge 调用走 `llm.router` profile=heavy
- 报告目录 `docs/eval_reports/eval_{YYYYMMDD_HHMMSS}.md`
- CI smoke 每 PR 自动运行（`.github/workflows/eval.yml`）

---

## 6. 变更记录

| 日期 | 摘要 |
|---|---|
| 2026-05-26 | W2 完成：datasets×5 + judges×3 + runner + report；Langfuse observe 装饰器接入 |
| 2026-05-25 | 占位建目录 |
