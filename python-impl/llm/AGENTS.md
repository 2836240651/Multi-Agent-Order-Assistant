# llm/ · 模型路由与语义缓存 AGENTS.md

> 所有 LLM 调用唯一入口。W4 落地。

---

## 1. 模块组成

| 文件 | 职责 |
|---|---|
| `router.py` | 按 profile 选模型 + 降级；统一接口 `call_llm(profile, messages, **kwargs)` |
| `semantic_cache.py` | Redis VSS + 装饰器 `@semantic_cached(profile, threshold, ttl, exempt=[...])` |
| `model_specs.py` | 模型规格表（max_tokens / 价格 / 提供商） |
| `prompt_loader.py` | 从 `prompts/` 加载版本化 prompt 模板 |
| `__init__.py` | 仅 re-export `call_llm` 与缓存装饰器 |

---

## 2. profile 与配置

`python-impl/config/model_routing.yaml`：
```yaml
profiles:
  light:  { primary: qwen-turbo,      backup: deepseek-v3 }
  medium: { primary: glm-4-flash,     backup: deepseek-v3 }
  heavy:  { primary: claude-sonnet-4, backup: gpt-4o }
defaults:
  timeout_s: 30
  retry_on_rate_limit: 2
  jitter_ms: [200, 800]
```

调用方只关心 profile（light/medium/heavy），不关心具体模型。

---

## 3. 不变量（机械化校验）

- **唯一入口**：除本目录外，禁止任何文件 `import openai/anthropic/zhipuai/dashscope/...` 客户端类
  - 拦截器：`scripts/check_no_direct_llm.py`
- 所有 `call_llm` 调用自动包装 Langfuse trace（profile / model / cost）
- LLM 输出涉及结构化时必须 Pydantic 校验，失败重试 ≤ 2 次，再失败抛 `LLM_OUTPUT_INVALID`
- 模型不可用降级链：primary → backup → 全降级 `LLM_ALL_UNAVAILABLE`

---

## 4. 语义缓存契约

- key：`semcache:{profile}:{hash8(embed)}`
- 命中阈值默认 cosine ≥ 0.95（可 per-调用覆盖）
- 豁免清单 `exempt_intents=["refund","risk","address_change"]` 不缓存
- 含订单号 / 金额数字 / 用户标识 的 query 强制不缓存
- 命中 → trace `cache_hit=true` + `cost_saved` 字段

---

## 5. 价格表维护

`model_specs.py` 价格随官方调整定期 review；价格变更必须更新 README 成本面板说明。

---

## 6. 变更记录

| 日期 | 摘要 |
|---|---|
| 2026-05-27 | W4 落地：router.py（profile→ModelSpec→主备降级+echo 兜底）+ model_specs.py + prompt_loader.py + semantic_cache.py 全量实现；SemanticCache 已接入 knowledge_agent + intent_router 路径；豁免清单单测 4 条全绿 |
| 2026-05-25 | 占位，W4 落地 |
