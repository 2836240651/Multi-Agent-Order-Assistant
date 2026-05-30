# 測試機部署（與 ziyi-test 並存）

> 服務器：`8.130.73.76`  
> 代碼：`/opt/retailguard/current`（GitHub pull）  
> 訪問：**http://8.130.73.76:10180**

## 為什麼例行更新只要幾分鐘

| 機制 | 說明 |
|------|------|
| **預設不 `build`** | 只 `git pull` + `up -d` + `restart` api/celery |
| **volume 掛載** | `python-impl` 掛到容器 `/app`，pull 即生效 |
| **精簡依賴** | `requirements-docker.txt` 無 PyTorch / sentence-transformers |
| **僅首次 build** | 裝依賴約 3～8 分鐘（ARM），之後不必重複 |

## 首次部署

```powershell
$env:RETAILGUARD_SSH_PASSWORD = '<SSH 密碼>'
python scripts/deploy-server.py --build --bootstrap
```

或在服務器：

```bash
bash /opt/retailguard/current/deploy/server/pull-and-deploy.sh --build --bootstrap
```

## 例行更新（改後端代碼，推薦）

```powershell
python scripts/deploy-server.py
```

約 **1～3 分鐘**（pull + 重啟容器）。

## 何時加參數

| 參數 | 場景 |
|------|------|
| `--build` | 改了 `requirements-docker.txt` / `Dockerfile.server` |
| `--build-frontend` | 只改了 Vue 前端 |
| `--bootstrap` | 首次灌庫、schema 變更後 |
| `--skip-pull` | 已在服務器 pull 過，只重啟 |
| `--no-restart` | 只 `up -d`，不重啟 api |

## 手動（服務器）

```bash
cd /opt/retailguard/current
git pull --ff-only origin main
docker compose -f deploy/server/docker-compose.yml --env-file deploy/server/.env up -d
docker compose -f deploy/server/docker-compose.yml restart python-agent celery-worker
```

## 文件說明

- `python-impl/requirements-docker.txt` — 服務器鏡像依賴
- `python-impl/Dockerfile.server` — 精簡鏡像構建
- `python-impl/requirements.txt` — 本地完整開發（含 sentence-transformers）
