"""LRU 响应缓存"""

import hashlib
import json
import time
from collections import OrderedDict


class ResponseCache:
    def __init__(self, max_size: int = 256, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl = ttl_seconds
        self._cache: OrderedDict[str, tuple[dict, float]] = OrderedDict()

    def _key(self, query: str, domain: str | None = None) -> str:
        raw = json.dumps({"q": query, "d": domain}, ensure_ascii=False)
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, query: str, domain: str | None = None) -> dict | None:
        k = self._key(query, domain)
        if k not in self._cache:
            return None
        result, ts = self._cache[k]
        if time.time() - ts > self.ttl:
            del self._cache[k]
            return None
        self._cache.move_to_end(k)
        return result

    def put(self, query: str, result: dict, domain: str | None = None):
        k = self._key(query, domain)
        self._cache[k] = (result, time.time())
        self._cache.move_to_end(k)
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

    def clear(self):
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)
