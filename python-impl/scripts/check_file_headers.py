"""scripts/check_file_headers.py：检查 .py 首行 docstring 含中文说明。"""
from __future__ import annotations

import ast
import sys
from pathlib import Path


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def check_file(path: Path) -> str | None:
    if "test" in path.parts or path.name.startswith("check_"):
        return None
    try:
        src = path.read_text(encoding="utf-8")
        mod = ast.parse(src, filename=str(path))
    except SyntaxError:
        return None
    doc = ast.get_docstring(mod)
    if not doc or not _has_cjk(doc):
        return "缺少中文文件头 docstring"
    return None


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    found = False
    for path in root.rglob("*.py"):
        if ".venv" in path.parts or "alembic/versions" in str(path):
            continue
        err = check_file(path)
        if err:
            print(f"{path.relative_to(root)}: {err}")
            found = True
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
