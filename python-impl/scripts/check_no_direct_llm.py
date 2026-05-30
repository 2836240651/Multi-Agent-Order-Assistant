"""scripts/check_no_direct_llm.py：pre-commit hook，禁止直调原生 LLM SDK。

检测文件中是否存在直接导入 openai / anthropic / dashscope / zhipuai 的语句，
llm/ 目录自身豁免（合法封装层）。

用法（pre-commit）：
    python scripts/check_no_direct_llm.py [file1.py file2.py ...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_BANNED_PATTERNS = [
    re.compile(r"^\s*(import|from)\s+openai\b"),
    re.compile(r"^\s*(import|from)\s+anthropic\b"),
    re.compile(r"^\s*(import|from)\s+dashscope\b"),
    re.compile(r"^\s*(import|from)\s+zhipuai\b"),
    re.compile(r"^\s*(import|from)\s+langchain_openai\b"),
    re.compile(r"^\s*(import|from)\s+langchain_anthropic\b"),
]

_EXEMPT_DIRS = {"llm", "scripts"}


def _is_exempt(path: Path) -> bool:
    parts = path.parts
    return any(exempt in parts for exempt in _EXEMPT_DIRS)


def check_file(path: Path) -> list[tuple[int, str]]:
    if _is_exempt(path):
        return []
    violations: list[tuple[int, str]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    for lineno, line in enumerate(lines, 1):
        for pat in _BANNED_PATTERNS:
            if pat.match(line):
                violations.append((lineno, line.strip()))
                break
    return violations


def main(argv: list[str] | None = None) -> int:
    files = argv if argv is not None else sys.argv[1:]
    if not files:
        return 0

    found_any = False
    for f in files:
        path = Path(f)
        if not path.suffix == ".py":
            continue
        violations = check_file(path)
        for lineno, line in violations:
            print(f"{path}:{lineno}: 禁止直调原生 LLM SDK，请走 llm.router.call_llm()")
            print(f"  → {line}")
            found_any = True

    return 1 if found_any else 0


if __name__ == "__main__":
    sys.exit(main())
