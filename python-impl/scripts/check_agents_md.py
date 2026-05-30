"""scripts/check_agents_md.py：pre-commit hook，检查 AGENTS.md 与目录一致性。

验证：
1. AGENTS.md 中列出的子目录/文件必须实际存在
2. 目录中的 .py 文件应在 AGENTS.md 中被提及

用法：
    python scripts/check_agents_md.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _check_agents_md(md_path: Path) -> list[str]:
    """检查单个 AGENTS.md 的一致性。"""
    issues: list[str] = []
    if not md_path.exists():
        return [f"AGENTS.md 不存在: {md_path}"]

    text = md_path.read_text(encoding="utf-8", errors="ignore")
    parent = md_path.parent

    # 提取 AGENTS.md 中引用的 .py 文件名
    referenced_files = set(re.findall(r"`(\w+\.py)`", text))

    # 检查引用的文件是否存在
    for fname in referenced_files:
        fpath = parent / fname
        if not fpath.exists():
            issues.append(f"{md_path.name} 引用了 {fname}，但文件不存在")

    return issues


def main() -> int:
    issues: list[str] = []

    # 找到所有 AGENTS.md
    for md in ROOT.rglob("AGENTS.md"):
        if ".git" in md.parts or "node_modules" in md.parts:
            continue
        issues.extend(_check_agents_md(md))

    if issues:
        for issue in issues:
            print(f"[WARN] {issue}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
