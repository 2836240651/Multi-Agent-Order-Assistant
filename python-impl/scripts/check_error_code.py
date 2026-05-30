"""scripts/check_error_code.py：pre-commit hook，检查异常抛出是否使用 ErrorCode 枚举。

检测 `raise BusinessException(` 中是否传入了裸字符串而非 ErrorCode 枚举。
exceptions/ 和 tests/ 目录豁免。

用法：
    python scripts/check_error_code.py [file1.py file2.py ...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# 匹配 raise BusinessException("xxx") — 裸字符串，不含 ErrorCode
_BAD_PATTERN = re.compile(r"""raise\s+BusinessException\s*\(\s*["']""")
# 匹配 raise BusinessException(ErrorCode. — 正确用法
_GOOD_PATTERN = re.compile(r"""raise\s+BusinessException\s*\(\s*ErrorCode\.""")

_EXEMPT_DIRS = {"exceptions", "tests"}


def _is_exempt(path: Path) -> bool:
    return any(exempt in path.parts for exempt in _EXEMPT_DIRS)


def check_file(path: Path) -> list[tuple[int, str]]:
    if _is_exempt(path):
        return []
    violations: list[tuple[int, str]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    for lineno, line in enumerate(lines, 1):
        if _BAD_PATTERN.search(line) and not _GOOD_PATTERN.search(line):
            violations.append((lineno, line.strip()))
    return violations


def main(argv: list[str] | None = None) -> int:
    files = argv if argv is not None else sys.argv[1:]
    if not files:
        return 0
    found = False
    for f in files:
        path = Path(f)
        if not path.suffix == ".py":
            continue
        for lineno, line in check_file(path):
            print(f"{path}:{lineno}: 异常必须使用 ErrorCode 枚举，禁止裸字符串")
            print(f"  → {line}")
            found = True
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
