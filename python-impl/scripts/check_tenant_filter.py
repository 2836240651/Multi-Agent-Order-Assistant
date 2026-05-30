"""scripts/check_tenant_filter.py：检查业务查询是否绕过 tenant 过滤（显式 tenant_id ==）。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_BAD = re.compile(r"""tenant_id\s*==\s*[^N]""")
_EXEMPT = re.compile(r"skip_tenant_filter|# tenant-exempt")
_SCAN_DIRS = ("api", "agents", "tasks")
_EXEMPT_FILES = {"tenant.py", "tenant_context.py"}


def check_file(path: Path) -> list[tuple[int, str]]:
    if "test" in path.parts or path.name in _EXEMPT_FILES or path.name == "check_tenant_filter.py":
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    out: list[tuple[int, str]] = []
    for i, line in enumerate(lines, 1):
        if _BAD.search(line) and not _EXEMPT.search(line):
            out.append((i, line.strip()))
    return out


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    found = False
    for sub in _SCAN_DIRS:
        base = root / sub
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            for lineno, line in check_file(path):
                print(f"{path.relative_to(root)}:{lineno}: 禁止显式 tenant_id 比较，请用 ContextVar 中间件")
                print(f"  → {line}")
                found = True
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
