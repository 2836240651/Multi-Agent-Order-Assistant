# RetailGuard 性能优化记录

> W7 性能优化跟踪。记录发现的瓶颈、改动和前后对比。

---

## 1. 数据库索引优化

### 1.1 复合索引

| 表 | 索引 | 列 | 目的 |
|---|---|---|---|
| `orders` | `ix_orders_tenant_status_created` | `(tenant_id, status, created_at)` | 租户级订单查询加速 |
| `tickets` | `ix_tickets_tenant_status_created` | `(tenant_id, status, created_at)` | 租户级工单查询加速 |

### 1.2 已有索引

| 表 | 索引 | 列 |
|---|---|---|
| `users` | `ix_users_tenant_id` | `tenant_id` |
| `users` | `uq_users_tenant_username` | `(tenant_id, username)` |
| `knowledge_docs` | `ix_knowledge_docs_tenant_id` | `tenant_id` |
| `audit_logs` | `ix_audit_logs_tenant_id` | `tenant_id` |
| `audit_logs` | `ix_audit_logs_action` | `action` |

---

## 2. Redis 缓存

### 2.1 用户权限缓存

- **位置**：`auth/user_service.py :: get_user_roles_and_perms()`
- **Key**：`perms:{tenant_id}:{user_id}`
- **TTL**：60s
- **效果**：登录后 60s 内重复请求跳过 DB 查询

### 2.2 语义缓存

- **位置**：`llm/semantic_cache.py`
- **Key**：`sem_cache:{hash}`
- **TTL**：3600s
- **阈值**：cosine ≥ 0.92
- **豁免**：退款/余额/密码等敏感操作不缓存

### 2.3 灰度权重缓存

- **位置**：`agents/rollout.py`
- **Key**：`rollout:weights`
- **方式**：Redis 直接存储，每次请求读取

---

## 3. N+1 排查

### 3.1 已优化

| 位置 | 问题 | 改动 |
|---|---|---|
| `db/models.py :: Role` | `permissions` 关系默认 lazy load | 已改为 `lazy="selectin"` |
| `db/models.py :: Permission` | `roles` 关系默认 lazy load | 已改为 `lazy="selectin"` |

### 3.2 待优化（压测后确认）

- `auth/user_service.py :: get_user_roles_and_perms` — 若缓存未命中，2 次 DB 查询（roles + permissions）可合并为 1 次 joinedload
- `api/main.py :: list_tenants` — 当前无分页，大量租户时需加 LIMIT

---

## 4. Worker 调优

### 4.1 uvicorn workers

```bash
# 开发
uvicorn api.main:app --reload --port 8000

# 生产（4 workers）
uvicorn api.main:app --workers 4 --port 8000 --loop uvloop
```

### 4.2 Celery workers

```bash
# 3 队列各 1-2 worker
celery -A tasks.celery_app worker --loglevel=info -Q review -c 2
celery -A tasks.celery_app worker --loglevel=info -Q ingest -c 1
celery -A tasks.celery_app worker --loglevel=info -Q eval -c 1
```

---

## 5. Qdrant HNSW 参数

当前默认参数适用于 < 10k 文档规模。规模增大后可调：

| 参数 | 当前值 | 建议范围 | 说明 |
|---|---|---|---|
| `m` | 16 | 16-64 | 每节点连接数 |
| `ef_construct` | 100 | 100-200 | 构建时搜索宽度 |
| `ef` | 128 | 128-256 | 查询时搜索宽度 |

---

## 6. 前端优化

### 6.1 已实施

- 路由懒加载（所有视图 `() => import(...)`）
- SSE 流式渲染（不等全部响应再显示）

### 6.2 待实施

- 组件级代码分割
- 静态资源 CDN
- Service Worker 离线缓存

---

## 变更记录

| 日期 | 摘要 |
|---|---|
| 2026-05-27 | W7 初版：索引 + Redis 缓存 + N+1 排查 + Worker 调优 + Qdrant 参数 |
