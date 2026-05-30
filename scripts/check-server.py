#!/usr/bin/env python3
"""RetailGuard 服務器自檢（≤55 秒）。等同 deploy-server.py --status。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    if not os.environ.get("RETAILGUARD_SSH_PASSWORD"):
        print("請設置 RETAILGUARD_SSH_PASSWORD", file=sys.stderr)
        sys.exit(2)
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "deploy-server.py"
    raise SystemExit(subprocess.call([sys.executable, str(script), "--status"], cwd=str(root)))


if __name__ == "__main__":
    main()
