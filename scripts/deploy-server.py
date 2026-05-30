#!/usr/bin/env python3
"""遠端從 GitHub 拉代碼並快速部署（預設不 build）。

代碼目錄：/opt/retailguard/current
後端通過 volume 掛載 python-impl，git pull 後 restart 即可生效（約 1～3 分鐘）。

用法（PowerShell）：
  $env:RETAILGUARD_SSH_PASSWORD='<SSH 密碼>'
  python scripts/deploy-server.py              # 例行：pull + up + restart
  python scripts/deploy-server.py --build      # 首次或 requirements 變更
  python scripts/deploy-server.py --bootstrap  # 首次灌庫（含 alembic/bootstrap/ingest）
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

try:
    import paramiko
except ImportError:
    print("請先安裝: pip install paramiko", file=sys.stderr)
    raise SystemExit(1) from None

REMOTE_ROOT = "/opt/retailguard/current"
COMPOSE_FILE = "deploy/server/docker-compose.yml"
COMPOSE_ENV = "deploy/server/.env"
DEFAULT_REPO = "https://github.com/2836240651/Multi-Agent-Order-Assistant.git"
HTTP_PORT = 10180


def run_remote(ssh: paramiko.SSHClient, cmd: str, timeout: int = 3600) -> None:
    print(f"\n>>> {cmd}")
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out.strip():
        print(out)
    if err.strip():
        print(err, file=sys.stderr)
    if code != 0:
        raise RuntimeError(f"遠端失敗 ({code}): {cmd}")


def remote_git_sync(repo_url: str, branch: str) -> str:
    env_bak = "/opt/retailguard/.env.deploy.bak"
    return f"""
set -e
REPO_URL='{repo_url}'
BRANCH='{branch}'
ROOT='{REMOTE_ROOT}'
ENV_FILE="$ROOT/deploy/server/.env"
mkdir -p /opt/retailguard
if [ -f "$ENV_FILE" ]; then cp -a "$ENV_FILE" '{env_bak}'; fi
if [ -d "$ROOT/.git" ]; then
  cd "$ROOT" && git fetch origin "$BRANCH" && git checkout "$BRANCH" && git pull --ff-only origin "$BRANCH"
else
  rm -rf "$ROOT"
  git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$ROOT"
fi
if [ -f '{env_bak}' ]; then mkdir -p "$ROOT/deploy/server" && cp -a '{env_bak}' "$ENV_FILE"; fi
cd "$ROOT" && git log -1 --oneline
"""


def compose_cmd(build: bool, up_only: bool) -> str:
    base = (
        f"cd {REMOTE_ROOT} && "
        f"docker compose -f {COMPOSE_FILE} --env-file {COMPOSE_ENV}"
    )
    if build:
        return f"{base} build && {base} up -d"
    if up_only:
        return f"{base} up -d"
    return f"{base} up -d && {base} restart python-agent celery-worker"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deploy RetailGuard (GitHub pull, 預設快速重啟不 build)",
    )
    parser.add_argument("--host", default=os.environ.get("RETAILGUARD_SSH_HOST", "8.130.73.76"))
    parser.add_argument("--user", default=os.environ.get("RETAILGUARD_SSH_USER", "root"))
    parser.add_argument(
        "--password",
        default=os.environ.get("RETAILGUARD_SSH_PASSWORD", ""),
    )
    parser.add_argument("--port", type=int, default=int(os.environ.get("RETAILGUARD_HTTP_PORT", HTTP_PORT)))
    parser.add_argument("--skip-pull", action="store_true", help="不 git pull")
    parser.add_argument("--branch", default=os.environ.get("RETAILGUARD_GIT_BRANCH", "main"))
    parser.add_argument("--repo", default=os.environ.get("RETAILGUARD_GIT_REPO", DEFAULT_REPO))
    parser.add_argument(
        "--build",
        action="store_true",
        help="重建鏡像（首次、requirements-docker.txt 或 Dockerfile 變更後）",
    )
    parser.add_argument(
        "--build-frontend",
        action="store_true",
        help="僅重建 frontend 鏡像（與 --build 可同時用）",
    )
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="執行 alembic + bootstrap + ingest_kb（首次部署）",
    )
    parser.add_argument(
        "--no-restart",
        action="store_true",
        help="pull 後不重啟 api/celery（僅 up -d）",
    )
    args = parser.parse_args()

    if not args.password:
        print("請設置 RETAILGUARD_SSH_PASSWORD 或 --password", file=sys.stderr)
        raise SystemExit(2)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"=== SSH {args.user}@{args.host} ===")
    mode = "build" if args.build else ("restart" if not args.no_restart else "up only")
    print(f"=== 模式: {mode} ===")
    ssh.connect(args.host, username=args.user, password=args.password, timeout=30)

    run_remote(
        ssh,
        "command -v git >/dev/null && command -v docker >/dev/null && docker compose version",
        timeout=30,
    )

    if not args.skip_pull:
        run_remote(ssh, remote_git_sync(args.repo, args.branch), timeout=300)

    run_remote(
        ssh,
        f"cd {REMOTE_ROOT} && "
        f"test -f {COMPOSE_ENV} || cp deploy/server/.env.example {COMPOSE_ENV} && "
        f"grep -q '^RG_HTTP_PORT=' {COMPOSE_ENV} || echo 'RG_HTTP_PORT={args.port}' >> {COMPOSE_ENV}",
        timeout=30,
    )

    if args.build:
        run_remote(ssh, compose_cmd(build=True, up_only=False), timeout=3600)
    elif args.build_frontend:
        run_remote(
            ssh,
            f"cd {REMOTE_ROOT} && docker compose -f {COMPOSE_FILE} --env-file {COMPOSE_ENV} "
            f"build frontend && docker compose -f {COMPOSE_FILE} --env-file {COMPOSE_ENV} up -d frontend",
            timeout=1800,
        )
        if not args.no_restart:
            run_remote(
                ssh,
                f"cd {REMOTE_ROOT} && docker compose -f {COMPOSE_FILE} restart python-agent celery-worker",
                timeout=120,
            )
    else:
        run_remote(
            ssh,
            compose_cmd(build=False, up_only=args.no_restart),
            timeout=600,
        )

    if args.bootstrap:
        run_remote(
            ssh,
            f"cd {REMOTE_ROOT} && docker compose -f {COMPOSE_FILE} exec -T python-agent alembic upgrade head",
            timeout=300,
        )
        run_remote(
            ssh,
            f"cd {REMOTE_ROOT} && docker compose -f {COMPOSE_FILE} exec -T python-agent python -m scripts.bootstrap",
            timeout=300,
        )
        run_remote(
            ssh,
            f"cd {REMOTE_ROOT} && docker compose -f {COMPOSE_FILE} exec -T python-agent python -m scripts.ingest_kb --kb /kb",
            timeout=600,
        )

    run_remote(
        ssh,
        f"docker compose -f {REMOTE_ROOT}/{COMPOSE_FILE} ps",
        timeout=60,
    )

    url = f"http://{args.host}:{args.port}"
    print(f"\n=== 完成 ===")
    print(f"訪問: {url}")
    print(f"演示: demo_customer_1 / 123456")
    if not args.build:
        print("提示: 依賴或 Dockerfile 變更後請加 --build；首次部署加 --bootstrap")

    try:
        subprocess.run(["curl.exe", "-sS", "-m", "15", f"{url}/health"], check=False)
    except FileNotFoundError:
        pass

    ssh.close()


if __name__ == "__main__":
    main()
