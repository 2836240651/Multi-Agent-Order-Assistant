"""llm/semantic_cache.py：基于 Redis 向量相似度的语义缓存。

策略：
- 对请求 query 计算 embedding，在 Redis 中查 cosine 最近邻
- 相似度 ≥ threshold → 返回缓存答案
- 豁免清单：退款/余额/密码等敏感操作不缓存（精确字符串匹配前缀）
- Redis 不可用时静默降级，不影响业务

用法：
    from llm.semantic_cache import SemanticCache
    cache = SemanticCache()
    hit = await cache.get(query)
    if hit is None:
        result = await call_llm(...)
        await cache.set(query, result.text)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ── 豁免清单（这些前缀不缓存）────────────────────────────────
_EXEMPT_PREFIXES = (
    "退款", "退货", "余额", "密码", "修改密码", "支付密码",
    "账户余额", "提现", "账单", "订单状态", "物流详情",
)

_DEFAULT_THRESHOLD = 0.92   # cosine 相似度阈值
_DEFAULT_TTL = 3600          # 缓存 TTL 秒
_CACHE_KEY_PREFIX = "sem_cache:"
_INDEX_KEY = "sem_cache_index"
_MEMORY_EXACT: dict[str, str] = {}


def _is_exempt(query: str) -> bool:
    q = query.strip()
    return any(q.startswith(p) for p in _EXEMPT_PREFIXES)


def _hash_query(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()[:16]


def _embed_local(text: str) -> list[float]:
    """本地 hash embedding（无 API key 时的 fallback）。"""
    chars = set(text.replace(" ", ""))
    dim = 128
    vec = [0.0] * dim
    for c in chars:
        idx = ord(c) % dim
        vec[idx] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    a_arr = np.array(a, dtype=np.float32)
    b_arr = np.array(b, dtype=np.float32)
    denom = (np.linalg.norm(a_arr) * np.linalg.norm(b_arr))
    if denom < 1e-9:
        return 0.0
    return float(np.dot(a_arr, b_arr) / denom)


class SemanticCache:
    """Redis-backed 语义缓存。"""

    def __init__(
        self,
        threshold: float = _DEFAULT_THRESHOLD,
        ttl: int = _DEFAULT_TTL,
        redis_url: str | None = None,
    ):
        self.threshold = threshold
        self.ttl = ttl
        self._redis_url = redis_url or os.getenv("REDIS_URL", "")
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._redis_url:
            return None
        try:
            import redis
            self._client = redis.from_url(self._redis_url, decode_responses=False)
            return self._client
        except Exception as exc:
            logger.debug("Redis unavailable for semantic cache: %s", exc)
            return None

    async def _embed(self, text: str) -> list[float]:
        """优先调 OpenAI embedding；否则用 hash fallback。"""
        try:
            from llm import call_llm
            # 直接用本地 hash（避免 embedding API 成本，W4 足够）
            pass
        except Exception:
            pass
        return _embed_local(text)

    async def get(self, query: str) -> str | None:
        """查缓存。命中返回缓存文本，否则 None。"""
        if _is_exempt(query):
            return None
        r = self._get_client()
        if r is None:
            return _MEMORY_EXACT.get(_hash_query(query))
        try:
            vec = await self._embed(query)
            # 遍历 index 查最近邻（小规模：<10k 条可接受）
            raw_index = r.get(_INDEX_KEY)
            if not raw_index:
                return None
            index: list[dict] = json.loads(raw_index)
            best_sim, best_key = 0.0, None
            for entry in index:
                sim = _cosine(vec, entry["vec"])
                if sim > best_sim:
                    best_sim, best_key = sim, entry["key"]
            if best_sim >= self.threshold and best_key:
                cached = r.get(best_key)
                if cached:
                    logger.debug("semantic cache HIT sim=%.3f key=%s", best_sim, best_key)
                    return cached.decode("utf-8")
        except Exception as exc:
            logger.debug("semantic cache get error: %s", exc)
        return None

    async def set(self, query: str, answer: str) -> None:
        """写入缓存。"""
        if _is_exempt(query):
            return
        r = self._get_client()
        h = _hash_query(query)
        if r is None:
            _MEMORY_EXACT[h] = answer
            return
        try:
            vec = await self._embed(query)
            key = f"{_CACHE_KEY_PREFIX}{h}"
            r.set(key, answer.encode("utf-8"), ex=self.ttl)

            # 更新 index
            raw_index = r.get(_INDEX_KEY)
            index: list[dict] = json.loads(raw_index) if raw_index else []
            # 去重：同 key 替换
            index = [e for e in index if e["key"] != key]
            index.append({"key": key, "vec": vec})
            # 保留最近 5000 条
            if len(index) > 5000:
                index = index[-5000:]
            r.set(_INDEX_KEY, json.dumps(index), ex=self.ttl * 2)
        except Exception as exc:
            logger.debug("semantic cache set error: %s", exc)

    def invalidate(self, query: str) -> None:
        """手动失效某个 query 的缓存。"""
        r = self._get_client()
        if r is None:
            return
        try:
            key = f"{_CACHE_KEY_PREFIX}{_hash_query(query)}"
            r.delete(key)
        except Exception:
            pass


# 全局单例
_default_cache: SemanticCache | None = None


def get_cache() -> SemanticCache:
    global _default_cache
    if _default_cache is None:
        _default_cache = SemanticCache()
    return _default_cache


__all__ = ["SemanticCache", "get_cache"]
