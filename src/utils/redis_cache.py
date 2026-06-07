"""Redis 分布式缓存 — 与 ResponseCache 接口兼容"""

import hashlib
import json
import os

import redis

from src.utils.logger import log


class RedisCache:
    """Redis 缓存后端，支持 TTL、键前缀、连接健康检查和故障回退"""

    def __init__(
        self,
        redis_url: str | None = None,
        ttl_seconds: int = 3600,
        key_prefix: str = "sb:cache:",
        socket_connect_timeout: float = 5.0,
        socket_timeout: float = 5.0,
        health_check: bool = True,
    ):
        redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.ttl = ttl_seconds
        self.prefix = key_prefix

        self.client = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=socket_timeout,
        )

        if health_check:
            try:
                self.client.ping()
            except redis.ConnectionError as e:
                raise redis.ConnectionError(
                    f"Redis 连接失败 ({redis_url}): {e}"
                ) from e

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
