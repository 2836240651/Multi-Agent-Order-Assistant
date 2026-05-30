"""scripts/drift_scan.py：扫描 requirements.txt 与第三方 import 漂移（轻量版）。"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

_EXTERNAL = {
    "fastapi", "pydantic", "sqlalchemy", "alembic", "httpx", "redis", "celery",
    "qdrant_client", "langgraph", "langchain_openai", "langfuse", "numpy",
    "sentence_transformers", "rank_bm25", "jieba", "yaml", "jwt", "bcrypt",
    "opentelemetry", "mcp", "locust", "matplotlib", "pytest", "aiosqlite",
    "uvicorn", "starlette", "openai", "anthropic",
}

_IMPORT_TO_PKG = {
    "jwt": "python-jose",
    "jose": "python-jose",
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "sentence_transformers": "sentence-transformers",
    "rank_bm25": "rank-bm25",
    "qdrant_client": "qdrant-client",
    "langchain_openai": "langchain-openai",
    "opentelemetry": "opentelemetry-sdk",
}


def _req_packages(req_path: Path) -> set[str]:
    pkgs: set[str] = set()
    for line in req_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!]", line)[0].split("[")[0].strip().lower()
        pkgs.add(name.replace("_", "-"))
    return pkgs


def _collect_imports(root: Path) -> set[str]:
    mods: set[str] = set()
    for path in root.rglob("*.py"):
        if "test" in path.parts or ".venv" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mods.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods.add(node.module.split(".")[0])
    return mods


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    req = root / "requirements.txt"
    if not req.exists():
        print("requirements.txt missing")
        return 1
    installed = _req_packages(req)
    missing: list[str] = []
    for mod in sorted(_collect_imports(root) & _EXTERNAL):
        pkg = _IMPORT_TO_PKG.get(mod, mod).lower().replace("_", "-")
        if pkg not in installed and mod.replace("_", "-") not in installed:
            missing.append(pkg)
    optional_ok = {"locust", "matplotlib", "langchain-openai", "opentelemetry-sdk", "starlette", "bcrypt"}
    missing = [m for m in missing if m not in optional_ok]
    if missing:
        print("requirements.txt 可能缺失：", ", ".join(missing))
        return 1
    print("drift_scan: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
