# RetailGuard Copilot

基于多智能体的电商售后风控客服系统，支持查单、退款、改地址等业务闭环。

## 功能特性

### 核心功能
- **订单查询** - 查询订单状态、物流信息
- **退款申请** - 退款金额校验、时限检查、风险审核
- **地址修改** - 收货地址变更（需要用户确认）
- **工单管理** - 工单创建、状态流转、历史记录

### 风控机制
- **风险预审** - 高风险请求自动进入人工复核
- **PII检测** - 敏感信息自动识别
- **退款时限** - 订单送达7天后禁止在线退款
- **审计日志** - 完整操作记录可追溯

### 工程化
- **灰度发布** - 支持多版本切换 (baseline_v1 / optimized_v2 / current_v3)
- **降级保护** - 服务不可用时自动降级
- **实时监控** - 请求量、延迟、错误率、成本估算
- **WebSocket通知** - 工单状态变更实时推送

## 技术栈

### 后端
- **Python 3.11+**
- FastAPI - API网关
- LangGraph - 多智能体编排
- SQLite - 本地数据库
- WebSocket - 实时通信

### 前端
- **Vue 3** + Composition API
- Vite - 构建工具
- 响应式设计

## 快速启动

### 后端启动

```bash
cd python-impl
pip install -r requirements.txt
python -m uvicorn api.main:app --host 0.0.0.0 --port 8002
```

### 前端启动

```bash
cd frontend
npm install
npm run dev
```

### 访问地址

- 前端: http://127.0.0.1:5173
- 后端API: http://127.0.0.1:8002
- API文档: http://127.0.0.1:8002/docs

## 项目结构

```
smart-cs-multi-agent/
├── python-impl/           # Python后端
│   ├── agents/            # 智能体实现
│   │   ├── supervisor.py      # 主管智能体（LangGraph编排）
│   │   ├── intent_router.py   # 意图识别
│   │   ├── ticket_handler.py # 工单处理
│   │   ├── risk_review.py     # 风险审核
│   │   └── greeting_handler.py # 问候处理
│   ├── api/               # API层
│   │   └── main.py            # FastAPI应用
│   ├── mcp/               # MCP工具
│   │   ├── mcp_server.py     # 工具服务器
│   │   └── db.py             # 数据库连接管理
│   ├── governance/         # 治理组件
│   │   ├── review.py          # 人工复核管理
│   │   ├── webhook.py         # Webhook通知
│   │   ├── websocket_manager.py # WebSocket管理
│   │   └── ticket_status.py   # 工单状态机
│   └── memory/             # 记忆组件
│       ├── working_memory.py   # 工作记忆
│       ├── short_term.py      # 短期记忆
│       └── long_term.py       # 长期记忆
├── frontend/              # Vue3前端
│   └── src/
│       ├── views/            # 页面组件
│       │   ├── DashboardView.vue   # 员工仪表盘
│       │   ├── ReviewView.vue      # 复核队列
│       │   ├── AuditView.vue      # 审计日志
│       │   └── UserDashboardView.vue # 用户中心
│       ├── composables/     # Vue组合式函数
│       │   ├── useChatWebSocket.js # 聊天WebSocket
│       │   └── useNotifications.js   # 通知订阅
│       └── api.js           # API调用封装
└── README.md
```

## 核心API

### 对话接口

```http
POST /api/chat
{
  "message": "我要退款，订单号 ORD-20260402-001",
  "user_id": "user_001",
  "session_id": "session_xxx",
  "order_id": "ORD-20260402-001"
}
```

### 人工复核

```http
GET /api/reviews/pending          # 获取待复核列表
POST /api/reviews/{id}/approve     # 批准
POST /api/reviews/{id}/reject      # 拒绝
```

### WebSocket

```javascript
// 聊天WebSocket
ws://localhost:8002/ws/chat

// 通知订阅
ws://localhost:8002/ws/notifications
// 发送 {"user_id": "xxx"} 订阅该用户的通知
```

## 业务流程

### 退款流程

```
用户发起退款请求
    ↓
系统检查退款资格（时限、金额）
    ↓
风险评估（高金额→人工复核）
    ↓
├─ 低风险 → 直接执行
├─ 高风险 → 人工复核
│   ├─ 批准 → 执行退款
│   └─ 拒绝 → 通知用户
└─ 资格不符 → 直接拒绝（带原因）
```

### 状态机

```
created → pending → pending_manual_review → resolved
                   ↘ pending_user_confirm → pending → ...
                   ↘ rejected → closed
```

## 关键文件说明

| 文件 | 职责 |
|------|------|
| `agents/supervisor.py` | LangGraph图定义，编排各智能体 |
| `agents/ticket_handler.py` | 工单业务逻辑（退款、改地址等） |
| `agents/risk_review.py` | 风险评估与人工复核触发 |
| `mcp/mcp_server.py` | MCP工具实现（订单、工单、风险检查） |
| `governance/review.py` | 人工复核管理器 |
| `governance/websocket_manager.py` | WebSocket连接管理 |
| `api/main.py` | FastAPI应用，API端点定义 |

## 配置说明

环境变量（`.env`）:

```bash
# 数据库
MYSQL_HOST=localhost        # 可选，使用MySQL
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=xxx
MYSQL_DATABASE=smart_cs

# Redis（可选）
REDIS_URL=redis://localhost:6379/0

# LLM配置
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1

# 灰度发布权重
ROLLOUT_BASELINE_V1=10
ROLLOUT_OPTIMIZED_V2=20
ROLLOUT_CURRENT_V3=70
```

## 测试

```bash
cd python-impl
python -m pytest tests/ -v
```

## 简历关键词

- **多智能体编排** - LangGraph状态机、意图路由、工具调用
- **风控系统** - 风险评估、人工复核、PII检测
- **实时通信** - WebSocket双向通信、实时通知
- **工程化** - 灰度发布、降级保护、审计日志
- **电商闭环** - 订单查询、退款处理、地址修改、工单流转
