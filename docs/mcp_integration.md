# MCP 集成指南

> RetailGuard Copilot 通过 MCP（Model Context Protocol）对外暴露工具，支持 Claude Desktop / 任��� MCP 客户端直接调用。

---

## 1. 暴露的工具

| 工具名 | 说明 | 必填参数 |
|---|---|---|
| `query_order` | 查询订单详情 | `order_id` |
| `list_refunds` | 列出退款工单 | 无（可选 status/limit） |
| `get_kb_doc` | 知识库检索 | `query` |
| `risk_check` | 风控评分 | `amount`, `reason` |

---

## 2. Claude Desktop 配置

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）
或 `%APPDATA%\Claude\claude_desktop_config.json`（Windows）：

```json
{
  "mcpServers": {
    "retailguard": {
      "command": "python",
      "args": ["-m", "mcp_tools.mcp_server"],
      "cwd": "/path/to/智能售后/python-impl",
      "env": {
        "APP_ENV": "dev",
        "MCP_API_TOKEN": "your-secret-token-here"
      }
    }
  }
}
```

配置后重启 Claude Desktop，工具栏会出现 RetailGuard 的 4 个工具。

---

## 3. 启动方式

### 3.1 stdio 模式（Claude Desktop 自动调用）

```bash
cd python-impl
python -m mcp_tools.mcp_server
```

### 3.2 带 Token 认证

```bash
MCP_API_TOKEN=my-secret python -m mcp_tools.mcp_server
```

### 3.3 从 Claude Code 调用

```bash
claude mcp add retailguard -- python -m mcp_tools.mcp_server
```

---

## 4. 使用示例

在 Claude Desktop 中直接说：

- "帮我查一下订单 ORD-1-A1B2C3D4 的状态"
- "列出所有待审核的退款工单"
- "搜索知识库中关于 7 天无理由退货的政策"
- "对一笔 999 元的退款做风控评分"

Claude 会自动调用对应工具并返回结构化结果。

---

## 5. 认证

若设置了 `MCP_API_TOKEN` 环境变量，调用方需在工具参数中传入 `_token` 字段：

```json
{
  "order_id": "ORD-001",
  "_token": "your-secret-token-here"
}
```

未设置 `MCP_API_TOKEN` 时，所有调用无需认证（开发/演示模式）。

---

## 6. 架构

```
Claude Desktop
    │
    ▼  stdio (JSON-RPC)
┌───────────────────────┐
│  mcp/mcp_server.py    │
│  (官方 mcp SDK)       │
│                       │
│  tools:               │
│  ├─ query_order ──────┼──► db/models.py (Order)
│  ├─ list_refunds ─────┼──► db/models.py (Ticket)
│  ├─ get_kb_doc ───────┼──► rag/retriever.py + reranker.py
│  └─ risk_check ───────┼──► risk/evaluate()
└───────────────────────┘
```

---

## 变更记录

| 日期 | 摘要 |
|---|---|
| 2026-05-27 | W8 初版：官方 mcp SDK stdio 重写，4 工具 + Token 认证 + Claude Desktop 配置 |
