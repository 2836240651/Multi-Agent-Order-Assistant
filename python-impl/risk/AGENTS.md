# risk/ · 三层融合风控 AGENTS.md

> 拆解 risk_review Agent 的"黑盒打分" 为可解释三层：规则 → 特征 → LLM → 融合。W4 实现。

---

## 1. 模块组成

| 文件 | 职责 |
|---|---|
| `rules.py` | 10 条左右硬规则（金额阈值/频次/超期/黑名单/...）；每条独立可单测 |
| `features.py` | 在线/离线特征：用户退款率、金额 z-score、地址跳变 km、设备频次 |
| `llm_scorer.py` | 中等模型语义风险判定；Pydantic 强约束输出 |
| `fusion.py` | 加权融合 + 决策（pass/review/reject）+ 可解释决策链 |
| `prompts/llm_scorer.md` | LLM 评分 prompt（版本化，commit 锁定） |
| `__init__.py` | 暴露 `evaluate(refund) -> RiskDecision` 单一入口 |

---

## 2. 配置

`python-impl/config/risk_weights.yaml`：
```yaml
default:
  rules: 0.40
  features: 0.30
  llm: 0.30
  thresholds: {pass: 30, review: 60, reject: 90}
```

- 权重运行时可通过 `/admin/risk/weights` 改，写 Redis 热加载
- 每次变更写 `audit_logs`

---

## 3. 数据契约

```python
class RulesResult(BaseModel):
    score: float           # 0-100
    hits: list[RuleHit]

class FeaturesResult(BaseModel):
    score: float
    evidence: dict         # 各特征值 + 是否异常

class LLMResult(BaseModel):
    score: float
    reason: str
    confidence: float
    unavailable: bool = False

class RiskDecision(BaseModel):
    fusion_score: float
    decision: Literal["pass", "review", "reject"]
    rules: RulesResult
    features: FeaturesResult
    llm: LLMResult
    weights: dict
    explanation: str       # 自然语言总结，给前端显示
```

存表 `risk_decisions`（DDL 见 设计.md §4.2）。

---

## 4. 不变量

- 任一层"全 0 但融合非 0" → 视为 bug，CI 单测拦截
- LLM 不可用 → 重归一化 rules+features，trace 打 tag `llm_unavailable=true`
- 决策链字段不可被前端伪造篡改：前端展示用，决定由后端 source of truth
- 单测必含 30 条边缘 case（含攻击样本：模板化描述 / 异常金额 / 跨省跳变）

---

## 5. 评测口径

- F1 ≥ 0.85（`docs/eval/datasets/risk.jsonl`）
- FP 率（正常单被误判 review/reject）≤ 10%
- LLM 不可用降级后 F1 不低于 0.75

---

## 6. 变更记录

| 日期 | 摘要 |
|---|---|
| 2026-05-27 | W4 落地：rules.py + features.py + llm_scorer.py + fusion.py + prompts/llm_scorer.md + __init__.py 全量实现；30 条风控单测全绿（test_risk.py）；evaluate() 入口可用；Redis 热加载权重路径已实现 |
| 2026-05-25 | 占位，W4 落地 |
