# 測試機部署（與 ziyi-test 並存）

> 服務器：`8.130.73.76`  
> 代碼：`/opt/retailguard/current`（GitHub pull）  
> 訪問：**http://8.130.73.76:10180**

## 本機每步 ≤55 秒（不再阻塞十幾分鐘）

| 命令 | 耗時 | 說明 |
|------|------|------|
| `python scripts/deploy-server.py` | ≤1 分鐘 | pull + up + restart |
| `python scripts/deploy-server.py --build` | ≤1 分鐘返回 | **背景 build**，日誌在服務器 |
| `python scripts/check-server.py` | ≤1 分鐘 | 自檢 build 進度 / 健康 |

Build 日誌：`/opt/retailguard/.deploy/build.log`（服務器）

## 首次部署

```powershell
$env:RETAILGUARD_SSH_PASSWORD = '<SSH 密碼>'
python scripts/deploy-server.py --build    # 觸發背景 build
python scripts/check-server.py             # 重複執行直到 health OK
```

## 例行更新

```powershell
python scripts/deploy-server.py            # 只 pull + 重啟（≤1 分鐘）
```

## 參數

| 參數 | 場景 |
|------|------|
| `--build` | 首次 / 依賴或 Dockerfile 變更（背景執行） |
| `--bootstrap` | 容器已起，補跑 alembic/bootstrap/ingest |
| `--status` | 僅自檢 |
| `--skip-pull` | 不 pull |

## 手動（服務器）

```bash
cd /opt/retailguard/current
git pull --ff-only origin main
bash deploy/server/background-build.sh     # 前台 build（會很久）
# 或
docker compose -f deploy/server/docker-compose.yml --env-file deploy/server/.env up -d
docker compose -f deploy/server/docker-compose.yml restart python-agent celery-worker
```
