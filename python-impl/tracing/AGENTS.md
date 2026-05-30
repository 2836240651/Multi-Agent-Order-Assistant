# tracing/ · 可观测性 AGENTS.md

> OTEL span 追踪 + Langfuse 全链路观测，两套可独立启用。

---

## 1. 模块组成

| 文件 | 职责 |
|---|---|
| `otel_config.py` | OpenTelemetry TracerProvider 初始化；`@trace_agent_call` 装饰器；`AgentMetrics` + `RuntimeObservability` |
| `observe.py` | Langfuse `@observe` / `@observe_llm` 装饰器；`flush_langfuse()` |

---

## 2. Langfuse 接入

### 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `LANGFUSE_PUBLIC_KEY` | 项目公钥 | `pk-lf-demo`（docker-compose 内） |
| `LANGFUSE_SECRET_KEY` | 项目私钥 | `sk-lf-demo` |
| `LANGFUSE_HOST` | 服务地址 | `http://localhost:13000` |

未配置时自动降级为 no-op，不影响业务。

### 已装饰的函数

| 函数 | 装饰器 | 位置 |
|---|---|---|
| `run_intent_router` | `@observe(name="intent_router.run")` | `agents/intent_router.py` |
| `_retrieve_for_state` | `@observe(name="knowledge_agent.retrieve")` | `agents/knowledge_agent.py` |
| `run_knowledge_agent` | `@observe(name="knowledge_agent.run")` | `agents/knowledge_agent.py` |
| `call_llm` | `@observe_llm(name="llm.call_llm")` | `llm/router.py` |

### 本地启动 Langfuse

```bash
make up          # 启动全栈（含 langfuse 容器）
make langfuse    # 打开 http://localhost:13000
# 默认账号：admin@retailguard.local / admin123
```

---

## 3. OTEL

`init_tracer()` 在 `api/main.py` 启动时调用，`OTEL_ENABLE_CONSOLE_EXPORT=true` 可打印 span 到 stdout，`OTEL_EXPORTER_OTLP_ENDPOINT` 指向 Jaeger/Tempo 实例。

---

## 4. 变更记录

| 日期 | 摘要 |
|---|---|
| 2026-05-26 | W2 添加 `observe.py`（Langfuse 装饰器），装饰 intent_router / knowledge_agent / call_llm |
