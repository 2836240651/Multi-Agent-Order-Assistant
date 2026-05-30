#!/usr/bin/env python3
"""上傳 RetailGuard 到測試機並 docker compose 啟動（與 ziyi-test 端口隔離）。

預設目錄：/opt/retailguard/current
對外入口：http://<host>:10180（僅映射 frontend，不佔 80/443）

用法（PowerShell）：
  $env:RETAILGUARD_SSH_PASSWORD='你的密碼'
  python scripts/deploy-server.py

可選：
  python scripts/deploy-server.py --skip-upload   # 僅遠端 rebuild/up
  python scripts/deploy-server.py --host 8.130.73.76
"""
from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

try:
    import paramiko
except ImportError:
    print("請先安裝: pip install paramiko", file=sys.stderr)
    raise SystemExit(1) from None

REMOTE_ROOT = "/opt/retailguard/current"
COMPOSE_FILE = "deploy/server/docker-compose.yml"
HTTP_PORT = 10180

EXCLUDE_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    "dist",
    "html1.html",
}
EXCLUDE_FILE_SUFFIXES = (".pyc", ".pyo", ".log")


def _should_skip(arcname: str) -> bool:
    parts = arcname.replace("\\", "/").split("/")
    for part in parts:
        if part in EXCLUDE_DIR_NAMES:
            return True
    if arcname.endswith(EXCLUDE_FILE_SUFFIXES):
        return True
    if "/python-impl/data/" in f"/{arcname}/":
        return True
    if "/docs/eval_reports/" in f"/{arcname}/" and arcname.endswith(".md"):
        return True
    return False


def make_archive(project_root: Path, dest: Path) -> None:
    print(f"=== 打包 {project_root} ===")
    with tarfile.open(dest, "w:gz") as tar:
        for item in project_root.iterdir():
            if item.name in EXCLUDE_DIR_NAMES:
                continue

            def filt(ti: tarfile.TarInfo) -> tarfile.TarInfo | None:
                name = ti.name.replace("\\", "/")
                if _should_skip(name):
                    return None
                return ti

            tar.add(item, arcname=item.name, filter=filt)
    size_mb = dest.stat().st_size / (1024 * 1024)
    print(f"OK: {dest} ({size_mb:.1f} MB)")


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy RetailGuard to test server")
    parser.add_argument("--host", default=os.environ.get("RETAILGUARD_SSH_HOST", "8.130.73.76"))
    parser.add_argument("--user", default=os.environ.get("RETAILGUARD_SSH_USER", "root"))
    parser.add_argument(
        "--password",
        default=os.environ.get("RETAILGUARD_SSH_PASSWORD", ""),
        help="SSH 密碼（建議用環境變數 RETAILGUARD_SSH_PASSWORD）",
    )
    parser.add_argument("--port", type=int, default=int(os.environ.get("RETAILGUARD_HTTP_PORT", HTTP_PORT)))
    parser.add_argument("--skip-upload", action="store_true")
    parser.add_argument(
        "--project-root",
        default=str(Path(__file__).resolve().parents[1]),
    )
    args = parser.parse_args()

    if not args.password:
        print("請設置 RETAILGUARD_SSH_PASSWORD 或 --password", file=sys.stderr)
        raise SystemExit(2)

    project_root = Path(args.project_root)
    env_example = project_root / "deploy" / "server" / ".env.example"
    env_local = project_root / "deploy" / "server" / ".env"

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"=== SSH {args.user}@{args.host} ===")
    ssh.connect(args.host, username=args.user, password=args.password, timeout=30)

    run_remote(
        ssh,
        f"mkdir -p {REMOTE_ROOT} && "
        f"(ss -tln | grep -q ':{args.port} ' && echo 'WARN: port {args.port} in use' || echo 'port {args.port} free') && "
        "docker ps --format '{{.Names}}' | head -20",
        timeout=60,
    )

    if not args.skip_upload:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "retailguard.tgz"
            make_archive(project_root, archive)
            sftp = ssh.open_sftp()
            remote_tar = f"{REMOTE_ROOT}/retailguard.tgz"
            print(f"=== 上傳 {remote_tar} ===")
            sftp.put(str(archive), remote_tar)
            sftp.close()
            run_remote(
                ssh,
                f"cd {REMOTE_ROOT} && "
                "find . -mindepth 1 -maxdepth 1 ! -name 'retailguard.tgz' ! -name '.env' -exec rm -rf {{}} + 2>/dev/null; "
                "tar -xzf retailguard.tgz && rm -f retailguard.tgz",
                timeout=600,
            )

    # 確保 .env 存在
    if not env_local.is_file():
        print("本地無 deploy/server/.env，遠端將用 .env.example 生成")
    run_remote(
        ssh,
        f"cd {REMOTE_ROOT} && "
        f"test -f deploy/server/.env || cp deploy/server/.env.example deploy/server/.env && "
        f"grep -q '^RG_HTTP_PORT=' deploy/server/.env || echo 'RG_HTTP_PORT={args.port}' >> deploy/server/.env",
        timeout=30,
    )

    run_remote(
        ssh,
        f"cd {REMOTE_ROOT} && "
        f"export RG_HTTP_PORT={args.port} && "
        f"docker compose -f {COMPOSE_FILE} --env-file deploy/server/.env build && "
        f"docker compose -f {COMPOSE_FILE} --env-file deploy/server/.env up -d",
        timeout=3600,
    )

    run_remote(
        ssh,
        f"cd {REMOTE_ROOT} && "
        f"docker compose -f {COMPOSE_FILE} exec -T python-agent alembic upgrade head",
        timeout=300,
    )
    run_remote(
        ssh,
        f"cd {REMOTE_ROOT} && "
        f"docker compose -f {COMPOSE_FILE} exec -T python-agent python -m scripts.bootstrap",
        timeout=300,
    )
    run_remote(
        ssh,
        f"cd {REMOTE_ROOT} && "
        f"docker compose -f {COMPOSE_FILE} exec -T python-agent python -m scripts.ingest_kb --kb /kb",
        timeout=600,
    )

    run_remote(
        ssh,
        f"docker compose -f {REMOTE_ROOT}/{COMPOSE_FILE} ps",
        timeout=60,
    )

    url = f"http://{args.host}:{args.port}"
    print(f"\n=== 部署完成 ===")
    print(f"訪問: {url}")
    print(f"演示帳號: demo_customer_1 / 123456 （tenant-a）")
    print(f"健康檢查: curl.exe -sS {url}/health")

    # 本地探活
    try:
        subprocess.run(
            ["curl.exe", "-sS", "-m", "15", f"{url}/health"],
            check=False,
        )
    except FileNotFoundError:
        pass

    ssh.close()


if __name__ == "__main__":
    main()
