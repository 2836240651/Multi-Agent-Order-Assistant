#!/usr/bin/env bash
# 在測試機執行。預設快速部署（不 build）；首次：bash pull-and-deploy.sh --build --bootstrap
set -euo pipefail

ROOT="${RG_ROOT:-/opt/retailguard/current}"
REPO_URL="${RG_REPO:-https://github.com/2836240651/Multi-Agent-Order-Assistant.git}"
BRANCH="${RG_BRANCH:-main}"
COMPOSE_FILE="deploy/server/docker-compose.yml"
COMPOSE_ENV="deploy/server/.env"
ENV_BAK="/opt/retailguard/.env.deploy.bak"
HTTP_PORT="${RG_HTTP_PORT:-10180}"

DO_BUILD=0
DO_BOOTSTRAP=0
DO_FRONTEND_BUILD=0
SKIP_PULL=0

for arg in "$@"; do
  case "$arg" in
    --build) DO_BUILD=1 ;;
    --bootstrap) DO_BOOTSTRAP=1 ;;
    --build-frontend) DO_FRONTEND_BUILD=1 ;;
    --skip-pull) SKIP_PULL=1 ;;
    *) echo "未知參數: $arg"; exit 1 ;;
  esac
done

command -v git >/dev/null
command -v docker >/dev/null

if [ "$SKIP_PULL" = "0" ]; then
  mkdir -p /opt/retailguard
  [ -f "$ROOT/$COMPOSE_ENV" ] && cp -a "$ROOT/$COMPOSE_ENV" "$ENV_BAK"
  if [ -d "$ROOT/.git" ]; then
    cd "$ROOT" && git fetch origin "$BRANCH" && git checkout "$BRANCH" && git pull --ff-only origin "$BRANCH"
  else
    rm -rf "$ROOT"
    git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$ROOT"
  fi
  [ -f "$ENV_BAK" ] && mkdir -p "$ROOT/deploy/server" && cp -a "$ENV_BAK" "$ROOT/$COMPOSE_ENV"
fi

cd "$ROOT"
git log -1 --oneline
test -f "$COMPOSE_ENV" || cp deploy/server/.env.example "$COMPOSE_ENV"
grep -q '^RG_HTTP_PORT=' "$COMPOSE_ENV" || echo "RG_HTTP_PORT=$HTTP_PORT" >> "$COMPOSE_ENV"

export RG_HTTP_PORT="$HTTP_PORT"
DC="docker compose -f $COMPOSE_FILE --env-file $COMPOSE_ENV"

if [ "$DO_BUILD" = "1" ]; then
  $DC build
  $DC up -d
elif [ "$DO_FRONTEND_BUILD" = "1" ]; then
  $DC build frontend
  $DC up -d
  $DC restart python-agent celery-worker
else
  $DC up -d
  $DC restart python-agent celery-worker
fi

if [ "$DO_BOOTSTRAP" = "1" ]; then
  $DC exec -T python-agent alembic upgrade head
  $DC exec -T python-agent python -m scripts.bootstrap
  $DC exec -T python-agent python -m scripts.ingest_kb --kb /kb
fi

$DC ps
echo "OK: http://127.0.0.1:${HTTP_PORT}/health"
