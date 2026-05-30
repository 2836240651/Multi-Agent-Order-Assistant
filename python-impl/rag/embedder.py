"""Embedding 包装。优先用 sentence-transformers 本地模型，无模型时回退到 hashing。

本地默认模型：paraphrase-multilingual-MiniLM-L12-v2（384 维，~420MB，支持中英文）。
生产可通过 settings.RAG_EMBEDDING_MODEL 指定 bge-large-zh-v1.5（1024 维）。
"""
from __future__ import annotations

import hashlib
import logging
import math
from typing import Sequence

import numpy as np

from config import settings

logger = logging.getLogger(__name__)

_real_model = None

# 本地开发默认用小模型（384维，首次自动下载）
_DEFAULT_LOCAL_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
_DEFAULT_LOCAL_DIM = 384


def _try_load_real_model():
    """尝试加载 sentence-transformers 模型；失败返回 None。"""
    global _real_model
    if settings.RAG_USE_LOCAL_FALLBACK or settings.is_test:
        return None
    if _real_model is not None:
        return _real_model
    try:
        from sentence_transformers import SentenceTransformer

        model_name = settings.RAG_EMBEDDING_MODEL or _DEFAULT_LOCAL_MODEL
        logger.info("loading embedding model: %s", model_name)
        _real_model = SentenceTransformer(model_name)
        logger.info("embedding model loaded: %s (dim=%d)", model_name, _real_model.get_embedding_dimension())
        return _real_model
    except Exception as exc:
        logger.warning("failed to load embedding model, fallback to hashing: %s", exc)
        return None


def _hashing_embed(text: str, dim: int) -> np.ndarray:
    """Fallback embedder：sha256 derivative，归一化到单位长度，仅用于本地 demo / 测试。"""
    # 用每个字符 trigram 哈希到固定 bucket
    vec = np.zeros(dim, dtype=np.float32)
    if not text:
        return vec
    tokens = list(text)
    for i in range(len(tokens)):
        gram = "".join(tokens[i : i + 3])
        h = int(hashlib.sha256(gram.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        vec[idx] += 1.0
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec


def embed_one(text: str) -> list[float]:
    """单条文本 → 1024 维向量。"""
    return embed_batch([text])[0]


def embed_batch(texts: Sequence[str]) -> list[list[float]]:
    """批量 embed。"""
    model = _try_load_real_model()
    if model is not None:
        arr = model.encode(list(texts), normalize_embeddings=True)
        return [v.tolist() for v in arr]
    # 降级：hash embedder（评测/无 GPU 环境）
    dim = settings.RAG_EMBED_DIM
    logger.debug("using hash embedder (dim=%d)", dim)
    return [_hashing_embed(t, dim).tolist() for t in texts]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """便捷余弦相似度。"""
    a_arr = np.asarray(a, dtype=np.float32)
    b_arr = np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(a_arr) * np.linalg.norm(b_arr))
    if denom == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / denom)


__all__ = ["embed_one", "embed_batch", "cosine", "get_dim"]


def get_dim() -> int:
    """返回当前 embedding 维度。"""
    model = _try_load_real_model()
    if model is not None:
        return model.get_embedding_dimension()
    return settings.RAG_EMBED_DIM
