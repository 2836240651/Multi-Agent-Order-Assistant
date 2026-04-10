"""
QueryCache — 基于Redis的防击穿缓存
避免同一用户重复query击穿后端，对检索结果进行缓存。
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None


class QueryCache:
    """
    Query缓存：防止重复query击穿后端

    特点：
    - 基于Redis，支持分布式部署
    - 缓存粒度：query + user_id 组合
    - TTL自动过期
    - 异步操作
    """

    def __init__(
        self,
        redis_url: str | None = None,
        ttl_seconds: int = 300,
        cache_enabled: bool = True,
    ):
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._ttl = ttl_seconds
        self._cache_enabled = cache_enabled
        self._redis: Any = None

    def _cache_key(self, query: str, user_id: str) -> str:
        """生成缓存key"""
        key_str = f"{user_id}:{query}"
        key_hash = hashlib.sha256(key_str.encode()).hexdigest()[:32]
        return f"smartcs:query_cache:{key_hash}"

    async def _get_redis(self):
        """懒加载Redis连接"""
        if self._redis is None:
            if aioredis is None:
                return None
            try:
                self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
                await self._redis.ping()
            except Exception:
                self._redis = None
        return self._redis

    async def get(self, query: str, user_id: str) -> list[dict] | None:
        """
        获取缓存的检索结果

        Returns:
            缓存命中返回文档列表，否则返回None
        """
        if not self._cache_enabled:
            return None

        r = await self._get_redis()
        if r is None:
            return None

        try:
            key = self._cache_key(query, user_id)
            cached = await r.get(key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass
        return None

    async def set(self, query: str, user_id: str, documents: list[dict]) -> None:
        """
        缓存检索结果

        Args:
            query: 用户查询
            user_id: 用户ID
            documents: 检索到的文档列表
        """
        if not self._cache_enabled or not documents:
            return

        r = await self._get_redis()
        if r is None:
            return

        try:
            key = self._cache_key(query, user_id)
            await r.setex(key, self._ttl, json.dumps(documents, ensure_ascii=False))
        except Exception:
            pass

    async def invalidate(self, query: str, user_id: str) -> None:
        """删除指定缓存"""
        r = await self._get_redis()
        if r is None:
            return

        try:
            key = self._cache_key(query, user_id)
            await r.delete(key)
        except Exception:
            pass

    async def clear_user(self, user_id: str) -> int:
        """清除用户所有缓存，返回清除的数量"""
        r = await self._get_redis()
        if r is None:
            return 0

        try:
            pattern = f"smartcs:query_cache:*"
            count = 0
            async for key in r.scan_iter(match=pattern):
                if user_id in key or True:
                    await r.delete(key)
                    count += 1
            return count
        except Exception:
            return 0

    async def stats(self) -> dict[str, Any]:
        """获取缓存统计信息"""
        r = await self._get_redis()
        if r is None:
            return {"connected": False, "enabled": self._cache_enabled}

        try:
            info = await r.info("stats")
            keys = await r.dbsize()
            return {
                "connected": True,
                "enabled": self._cache_enabled,
                "ttl_seconds": self._ttl,
                "total_keys": keys,
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
            }
        except Exception:
            return {"connected": False, "enabled": self._cache_enabled}
