"""KB Markdown loader：解析 frontmatter + 父子切片。

切片策略：
- 优先按 Markdown ## / ### 小节切分（适合短政策 FAQ）
- 单节超长再按字符滑窗；整篇过短则整篇一片
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from config import settings

logger = logging.getLogger(__name__)

_SECTION_RE = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)


@dataclass
class ParentChunk:
    parent_id: str
    text: str
    start: int
    end: int


@dataclass
class ChildChunk:
    chunk_id: str
    parent_id: str
    parent_text: str
    chunk_text: str
    doc_id: str
    doc_no: str
    title: str
    category: str
    tenant_id: int | None
    effective_from: str | None
    effective_to: str | None
    extra_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoadedDoc:
    """单个 KB Markdown 文档解析结果。"""

    doc_no: str
    title: str
    category: str
    tenant_id: int | None
    effective_from: str | None
    effective_to: str | None
    raw_path: str | None
    body: str
    parent_chunks: list[ParentChunk]
    child_chunks: list[ChildChunk]
    extra: dict[str, Any]


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return {}, raw
    fm_text, body = match.group(1), match.group(2)
    try:
        meta = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        logger.warning("frontmatter parse failed: %s", exc)
        meta = {}
    return meta, body


def _split_parent(text: str, size: int, overlap: int) -> list[ParentChunk]:
    if size <= overlap:
        raise ValueError("size must > overlap")
    chunks: list[ParentChunk] = []
    n = len(text)
    if n == 0:
        return chunks
    start = 0
    idx = 0
    while start < n:
        end = min(start + size, n)
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(
                ParentChunk(parent_id=f"p{idx:04d}", text=chunk_text, start=start, end=end)
            )
            idx += 1
        if end >= n:
            break
        start = end - overlap
    return chunks


def _split_child(parent: ParentChunk, size: int) -> list[tuple[str, str]]:
    text = parent.text
    out: list[tuple[str, str]] = []
    if len(text) <= size:
        if text:
            out.append((f"{parent.parent_id}-c00", text))
        return out
    for i in range(0, len(text), size):
        seg = text[i : i + size].strip()
        if seg:
            out.append((f"{parent.parent_id}-c{i // size:02d}", seg))
    return out


def _split_by_sections(body: str, doc_title: str) -> list[tuple[str, str]]:
    """按 ## / ### 切分，返回 [(section_title, section_body), ...]。"""
    matches = list(_SECTION_RE.finditer(body))
    if not matches:
        stripped = body.strip()
        return [(doc_title, stripped)] if stripped else []

    sections: list[tuple[str, str]] = []
    # 文档标题下、第一个 ## 之前的内容
    pre = body[: matches[0].start()].strip()
    if pre:
        sections.append((doc_title, pre))

    for i, m in enumerate(matches):
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content = body[start:end].strip()
        if content:
            sections.append((title, content))
    return sections


def _build_chunks_from_sections(
    sections: list[tuple[str, str]],
    doc_no: str,
    title: str,
    category: str,
    tenant_id: int | None,
    effective_from: str | None,
    effective_to: str | None,
    extra_meta: dict[str, Any],
) -> tuple[list[ParentChunk], list[ChildChunk]]:
    parents: list[ParentChunk] = []
    children: list[ChildChunk] = []
    parent_size = settings.RAG_PARENT_CHARS
    child_size = settings.RAG_CHILD_CHARS
    overlap = settings.RAG_OVERLAP_CHARS
    short_limit = getattr(settings, "RAG_SHORT_DOC_CHARS", 400)

    p_idx = 0
    for sec_title, sec_body in sections:
        prefix = f"{title} · {sec_title}\n\n"
        full_text = prefix + sec_body
        if len(full_text) <= short_limit:
            parent_list = [ParentChunk(parent_id=f"p{p_idx:04d}", text=full_text, start=0, end=len(full_text))]
            p_idx += 1
        else:
            parent_list = _split_parent(full_text, parent_size, overlap)
            for j, p in enumerate(parent_list):
                p.parent_id = f"p{p_idx + j:04d}"
            p_idx += len(parent_list)

        for parent in parent_list:
            for child_id, child_text in _split_child(parent, child_size):
                children.append(
                    ChildChunk(
                        chunk_id=f"{doc_no}::{child_id}",
                        parent_id=parent.parent_id,
                        parent_text=parent.text,
                        chunk_text=child_text,
                        doc_id=doc_no,
                        doc_no=doc_no,
                        title=title,
                        category=category,
                        tenant_id=tenant_id,
                        effective_from=effective_from,
                        effective_to=effective_to,
                        extra_metadata={**extra_meta, "section": sec_title},
                    )
                )
        parents.extend(parent_list)

    return parents, children


def _norm_dt(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


def load_markdown(path: str | Path) -> LoadedDoc:
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(raw)

    doc_no = str(meta.get("doc_no") or p.stem)
    title = str(meta.get("title") or _extract_first_heading(body) or p.stem)
    category = str(meta.get("category") or "policy")
    tenant_id = meta.get("tenant_id")
    if tenant_id is not None:
        tenant_id = int(tenant_id)

    extra_meta = {
        k: v
        for k, v in meta.items()
        if k not in {"doc_no", "title", "category", "tenant_id", "effective_from", "effective_to"}
    }

    sections = _split_by_sections(body, title)
    if len(sections) > 1 or (sections and len(sections[0][1]) > getattr(settings, "RAG_SHORT_DOC_CHARS", 400)):
        parents, children = _build_chunks_from_sections(
            sections, doc_no, title, category, tenant_id,
            _norm_dt(meta.get("effective_from")),
            _norm_dt(meta.get("effective_to")),
            extra_meta,
        )
    else:
        parents = _split_parent(body, settings.RAG_PARENT_CHARS, settings.RAG_OVERLAP_CHARS)
        children = []
        for parent in parents:
            for child_id, child_text in _split_child(parent, settings.RAG_CHILD_CHARS):
                children.append(
                    ChildChunk(
                        chunk_id=f"{doc_no}::{child_id}",
                        parent_id=parent.parent_id,
                        parent_text=parent.text,
                        chunk_text=child_text,
                        doc_id=doc_no,
                        doc_no=doc_no,
                        title=title,
                        category=category,
                        tenant_id=tenant_id,
                        effective_from=_norm_dt(meta.get("effective_from")),
                        effective_to=_norm_dt(meta.get("effective_to")),
                        extra_metadata=extra_meta,
                    )
                )

    return LoadedDoc(
        doc_no=doc_no,
        title=title,
        category=category,
        tenant_id=tenant_id,
        effective_from=_norm_dt(meta.get("effective_from")),
        effective_to=_norm_dt(meta.get("effective_to")),
        raw_path=str(p),
        body=body,
        parent_chunks=parents,
        child_chunks=children,
        extra=meta,
    )


def _extract_first_heading(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return None


def load_directory(directory: str | Path) -> list[LoadedDoc]:
    p = Path(directory)
    if not p.exists():
        logger.warning("KB directory does not exist: %s", p)
        return []
    docs: list[LoadedDoc] = []
    for md in sorted(p.rglob("*.md")):
        try:
            docs.append(load_markdown(md))
        except Exception as exc:
            logger.exception("load %s failed: %s", md, exc)
    return docs


__all__ = ["load_markdown", "load_directory", "LoadedDoc", "ParentChunk", "ChildChunk"]
