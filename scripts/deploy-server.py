#!/usr/bin/env python3
"""遠端 GitHub 拉代碼 + 快速部署。

規則：本機每步 SSH 同步等待 ≤55 秒；超時即自檢並退出。
docker build 等長任務在服務器背景執行，用 check-server.py 查看進度。

用法：
  python scripts/deploy-server.py              # pull + up + restart（≤1 分鐘）
  python scripts/deploy-server.py --build      # 背景 build，立即返回 + 自檢
  python scripts/deploy-server.py --status     # 僅自檢
  python scripts/check-server.py               # 同上
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any

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
CMD_TIMEOUT = 55  # 單步最長等待（秒）


def run_remote(
    ssh: paramiko.SSHClient,
    cmd: str,
    *,
    timeout: int = CMD_TIMEOUT,
    allow_fail: bool = False,
) -> tuple[int, str]:
    print(f"\n>>> {cmd[:240]}")
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    merged = (out + "\n" + err).strip()
    if merged:
        tail = merged[-4000:] if len(merged) > 4000 else merged
        print(tail)
    if code != 0 and not allow_fail:
        raise RuntimeError(f"遠端失敗 ({code})")
    return code, merged


def self_check(ssh: paramiko.SSHClient, host: str, port: int) -> dict[str, Any]:
    """服務器自檢，≤55 秒。"""
    script = f"""
cd {REMOTE_ROOT} 2>/dev/null && git log -1 --oneline 2>/dev/null || echo "git: none"
echo "---images---"
docker images 2>/dev/null | grep retailguard || echo "no retailguard image"
echo "---containers---"
docker ps -a --filter name=rg- --format '{{{{.Names}}}} {{{{.Status}}}}' || true
echo "---build---"
if [ -f /opt/retailguard/.deploy/build.pid ]; then
  echo "build_running pid=$(cat /opt/retailguard/.deploy/build.pid)"
  tail -5 /opt/retailguard/.deploy/build.log 2>/dev/null || true
elif [ -f /opt/retailguard/.deploy/build.log ]; then
  echo "build_idle"
  tail -3 /opt/retailguard/.deploy/build.log 2>/dev/null || true
else
  echo "no_build_log"
fi
echo "---port---"
ss -tln | grep ':{port} ' || echo "port {port} down"
echo "---health---"
curl -sS -m 5 http://127.0.0.1:{port}/health 2>/dev/null || echo "health failed"
"""
    _, out = run_remote(ssh, script, timeout=CMD_TIMEOUT, allow_fail=True)
    return {
        "host": host,
        "port": port,
        "url": f"http://{host}:{port}",
        "raw": out,
        "healthy": "health failed" not in out and f"port {port} down" not in out,
        "build_running": "build_running" in out,
    }


def remote_git_sync(repo_url: str, branch: str) -> str:
    env_bak = "/opt/retailguard/.env.deploy.bak"
    return f"""
set -e
ROOT='{REMOTE_ROOT}'
ENV_FILE="$ROOT/deploy/server/.env"
mkdir -p /opt/retailguard
[ -f "$ENV_FILE" ] && cp -a "$ENV_FILE" '{env_bak}'
if [ -d "$ROOT/.git" ]; then
  cd "$ROOT" && git fetch origin '{branch}' && git checkout '{branch}' && git pull --ff-only origin '{branch}'
else
  rm -rf "$ROOT"
  git clone --branch '{branch}' --depth 1 '{repo_url}' "$ROOT"
fi
[ -f '{env_bak}' ] && mkdir -p "$ROOT/deploy/server" && cp -a '{env_bak}' "$ENV_FILE"
cd "$ROOT" && git log -1 --oneline
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="RetailGuard 遠端部署（每步≤55s）")
    parser.add_argument("--host", default=os.environ.get("RETAILGUARD_SSH_HOST", "8.130.73.76"))
    parser.add_argument("--user", default=os.environ.get("RETAILGUARD_SSH_USER", "root"))
    parser.add_argument("--password", default=os.environ.get("RETAILGUARD_SSH_PASSWORD", ""))
    parser.add_argument("--port", type=int, default=int(os.environ.get("RETAILGUARD_HTTP_PORT", HTTP_PORT)))
    parser.add_argument("--skip-pull", action="store_true")
    parser.add_argument("--branch", default=os.environ.get("RETAILGUARD_GIT_BRANCH", "main"))
    parser.add_argument("--repo", default=os.environ.get("RETAILGUARD_GIT_REPO", DEFAULT_REPO))
    parser.add_argument("--build", action="store_true", help="背景 docker build（不阻塞）")
    parser.add_argument("--bootstrap", action="store_true", help="容器已起時執行灌庫")
    parser.add_argument("--no-restart", action="store_true")
    parser.add_argument("--status", action="store_true", help="僅自檢")
    args = parser.parse_args()

    if not args.password:
        print("請設置 RETAILGUARD_SSH_PASSWORD", file=sys.stderr)
        raise SystemExit(2)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(args.host, username=args.user, password=args.password, timeout=30)

    if args.status:
        st = self_check(ssh, args.host, args.port)
        print(json.dumps({k: v for k, v in st.items() if k != "raw"}, ensure_ascii=False, indent=2))
        print(st["raw"])
        ssh.close()
        return

    run_remote(ssh, "command -v git && command -v docker && docker compose version", timeout=CMD_TIMEOUT)

    if not args.skip_pull:
        run_remote(ssh, remote_git_sync(args.repo, args.branch), timeout=CMD_TIMEOUT)

    run_remote(
        ssh,
        f"cd {REMOTE_ROOT} && test -f {COMPOSE_ENV} || cp deploy/server/.env.example {COMPOSE_ENV}",
        timeout=CMD_TIMEOUT,
    )

    if args.build:
        run_remote(
            ssh,
            f"mkdir -p /opt/retailguard/.deploy && "
            f"if [ -f /opt/retailguard/.deploy/build.pid ] && kill -0 $(cat /opt/retailguard/.deploy/build.pid) 2>/dev/null; then "
            f"echo 'build already running'; else "
            f"nohup bash {REMOTE_ROOT}/deploy/server/background-build.sh </dev/null >/opt/retailguard/.deploy/nohup.out 2>&1 & "
            f"echo started_pid=$!; fi",
            timeout=CMD_TIMEOUT,
        )
        st = self_check(ssh, args.host, args.port)
        print("\n=== 背景 build 已觸發（本機不再等待）===")
        print(f"查看進度: python scripts/check-server.py")
        print(f"訪問: {st['url']}")
        print(st["raw"])
        ssh.close()
        return

    base = f"cd {REMOTE_ROOT} && docker compose -f {COMPOSE_FILE} --env-file {COMPOSE_ENV}"
    run_remote(ssh, f"{base} up -d", timeout=CMD_TIMEOUT)
    if not args.no_restart:
        run_remote(ssh, f"{base} restart python-agent celery-worker", timeout=CMD_TIMEOUT, allow_fail=True)

    if args.bootstrap:
        for cmd in (
            f"{base} exec -T python-agent alembic upgrade head",
            f"{base} exec -T python-agent python -m scripts.bootstrap",
            f"{base} exec -T python-agent python -m scripts.ingest_kb --kb /kb",
        ):
            run_remote(ssh, cmd, timeout=CMD_TIMEOUT, allow_fail=True)

    st = self_check(ssh, args.host, args.port)
    print(f"\n=== 完成（≤{CMD_TIMEOUT}s/步）===")
    print(f"訪問: {st['url']}")
    print(st["raw"])
    if not st["healthy"]:
        print("提示: 若鏡像未建，執行 python scripts/deploy-server.py --build")

    try:
        subprocess.run(["curl.exe", "-sS", "-m", "10", st["url"] + "/health"], check=False)
    except FileNotFoundError:
        pass
    ssh.close()


if __name__ == "__main__":
    main()
