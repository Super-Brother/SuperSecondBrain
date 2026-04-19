"""测试工具模块"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils.cache import ResponseCache


class TestResponseCache:
    def test_miss_returns_none(self):
        cache = ResponseCache()
        assert cache.get("不存在的查询") is None

    def test_put_and_get(self):
        cache = ResponseCache()
        result = {"answer": "测试", "sources": []}
        cache.put("查询", result)
        assert cache.get("查询") == result

    def test_domain_isolation(self):
        cache = ResponseCache()
        r1 = {"answer": "A"}
        r2 = {"answer": "B"}
        cache.put("q", r1, domain="编程")
        cache.put("q", r2, domain="AI")
        assert cache.get("q", domain="编程")["answer"] == "A"
        assert cache.get("q", domain="AI")["answer"] == "B"
        assert cache.get("q") is None  # 无 domain 不命中

    def test_ttl_expiry(self):
        cache = ResponseCache(ttl_seconds=0)
        cache.put("q", {"answer": "过期"})
        assert cache.get("q") is None

    def test_max_size_eviction(self):
        cache = ResponseCache(max_size=2)
        cache.put("a", {"answer": "A"})
        cache.put("b", {"answer": "B"})
        cache.put("c", {"answer": "C"})
        assert cache.get("a") is None  # 被淘汰
        assert cache.get("c") is not None

    def test_clear(self):
        cache = ResponseCache()
        cache.put("q", {"answer": "x"})
        cache.clear()
        assert cache.get("q") is None
        assert cache.size == 0

    def test_size_property(self):
        cache = ResponseCache()
        assert cache.size == 0
        cache.put("q1", {"a": 1})
        cache.put("q2", {"a": 2})
        assert cache.size == 2
