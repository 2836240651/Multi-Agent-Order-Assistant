# 測試機部署（與 ziyi-test 並存）

> 服務器：`8.130.73.76`（與 `D:/ziyi-project/AGENTS.md` 同一台）  
> ziyi 佔用：`80`（gateway）、內部 MySQL/Redis 容器  
> RetailGuard **僅映射** `10180 → 前端 nginx`，不暴露 PG/Redis/Qdrant 到宿主端口。

## 一鍵部署（本機 PowerShell）

```powershell
cd D:\智能售后
pip install paramiko
$env:RETAILGUARD_SSH_PASSWORD = '<SSH 密碼>'
python scripts/deploy-server.py
```

訪問：**http://8.130.73.76:10180**  
帳號：`demo_customer_1` / `123456`（tenant-a）

## 端口與隔離

| 項目 | 值 |
|------|-----|
| 部署目錄 | `/opt/retailguard/current` |
| Compose 項目名 | `retailguard` |
| 容器前綴 | `rg-*` |
| 對外 HTTP | `10180`（可改 `deploy/server/.env` 中 `RG_HTTP_PORT`） |
| 不佔用 | `80`、`443`、`3306`、`6379`（ziyi 與系統服務） |

## 日常更新

```powershell
python scripts/deploy-server.py              # 全量上傳 + rebuild
python scripts/deploy-server.py --skip-upload  # 僅遠端 compose build/up
```

## 遠端手動

```bash
cd /opt/retailguard/current
docker compose -f deploy/server/docker-compose.yml ps
docker compose -f deploy/server/docker-compose.yml logs -f python-agent
```

## 可選：綁定域名

在宿主 nginx（勿改 ziyi `80` 默認站）新增獨立 `server_name`，反代到 `127.0.0.1:10180`。
