#!/usr/bin/env python3
"""快速查看測試機 RetailGuard 部署狀態。"""
import os
import sys

import paramiko

host = os.environ.get("RETAILGUARD_SSH_HOST", "8.130.73.76")
password = os.environ.get("RETAILGUARD_SSH_PASSWORD", "")
if not password:
    print("設置 RETAILGUARD_SSH_PASSWORD", file=sys.stderr)
    sys.exit(2)

cmds = [
    "ls -la /opt/retailguard/current 2>/dev/null | head -8",
    "cd /opt/retailguard/current && git log -1 --oneline 2>/dev/null || echo 'no git'",
    "docker ps -a --filter name=rg- --format '{{.Names}} {{.Status}}'",
    "ss -tln | grep 10180 || echo 'port 10180 not listening'",
    "curl -sS -m 5 http://127.0.0.1:10180/health 2>/dev/null || echo health failed",
]

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, username="root", password=password, timeout=30)
for cmd in cmds:
    _, o, _ = ssh.exec_command(cmd, timeout=30)
    o.channel.recv_exit_status()
    print(f">>> {cmd}\n{o.read().decode()}")
ssh.close()
