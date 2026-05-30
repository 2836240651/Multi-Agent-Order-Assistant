#!/usr/bin/env bash
# 服務器背景構建（由 deploy-server.py --build 觸發，勿前台阻塞）
set -euo pipefail

ROOT="${RG_ROOT:-/opt/retailguard/current}"
DEPLOY_DIR="/opt/retailguard/.deploy"
LOG="$DEPLOY_DIR/build.log"
PID_FILE="$DEPLOY_DIR/build.pid"
COMPOSE_FILE="deploy/server/docker-compose.yml"
COMPOSE_ENV="deploy/server/.env"

mkdir -p "$DEPLOY_DIR"
echo $$ > "$PID_FILE"
exec >>"$LOG" 2>&1

echo "=== build started $(date -Iseconds) ==="
cd "$ROOT"
export RG_HTTP_PORT="${RG_HTTP_PORT:-10180}"
DC="docker compose -f $COMPOSE_FILE --env-file $COMPOSE_ENV"

$DC build --progress=plain python-agent
$DC build --progress=plain frontend
$DC up -d
$DC exec -T python-agent alembic upgrade head || true
$DC exec -T python-agent python -m scripts.bootstrap || true
$DC exec -T python-agent python -m scripts.ingest_kb --kb /kb || true
$DC ps
echo "=== build finished $(date -Iseconds) ==="
rm -f "$PID_FILE"
