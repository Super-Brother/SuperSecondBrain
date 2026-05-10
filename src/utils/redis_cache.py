"""Redis 分布式缓存 — 与 ResponseCache 接口兼容"""

import hashlib
import json
import os

import redis


class RedisCache:
    """Redis 缓存后端，支持 TTL 和键前缀"""

    def __init__(self, redis_url: str | None = None, ttl_seconds: int = 3600, key_prefix: str = "sb:cache:"):
        redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.client = redis.from_url(redis_url, decode_responses=True)
        self.ttl = ttl_seconds
        self.prefix = key_prefix

    def _key(self, query: str, domain: str | None = None) -> str:
        raw = json.dumps({"q": query, "d": domain}, ensure_ascii=False)
        h = hashlib.md5(raw.encode()).hexdigest()
        return f"{self.prefix}{h}"

    def get(self, query: str, domain: str | None = None) -> dict | None:
        k = self._key(query, domain)
        data = self.client.get(k)
        if data is None:
            return None
        return json.loads(data)

    def put(self, query: str, result: dict, domain: str | None = None):
        k = self._key(query, domain)
        self.client.setex(k, self.ttl, json.dumps(result, ensure_ascii=False))

    def clear(self):
        pattern = f"{self.prefix}*"
        for key in self.client.scan_iter(match=pattern):
            self.client.delete(key)

    @property
    def size(self) -> int:
        pattern = f"{self.prefix}*"
        count = 0
        for _ in self.client.scan_iter(match=pattern):
            count += 1
        return count
