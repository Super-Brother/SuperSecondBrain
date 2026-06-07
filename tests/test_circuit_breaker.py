"""熔断器模块测试"""

import pytest
from src.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitState,
    get_circuit_breaker,
)


class TestCircuitBreaker:
    """熔断器单元测试"""

    def test_initial_state_closed(self):
        """初始状态应为关闭"""
        cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout=1)
        assert cb.state == CircuitState.CLOSED

    def test_success_resets_failure_count(self):
        """成功调用应重置失败计数"""
        cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout=1)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold(self):
        """达到失败阈值后应打开"""
        cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_open_blocks_calls(self):
        """打开状态应阻止调用"""
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=60)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        def fail_func():
            raise RuntimeError("boom")

        with pytest.raises(CircuitBreakerOpen):
            cb.call(fail_func)

    def test_half_open_after_recovery_timeout(self):
        """超过恢复超时后进入半开状态"""
        import time

        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # 等待恢复超时
        time.sleep(0.15)
        # _can_attempt 会触发状态转移到 HALF_OPEN
        assert cb._can_attempt()
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes(self):
        """半开状态探测成功应关闭"""
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0)
        cb.record_failure()
        # 手动设置半开
        cb._state = CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        """半开状态探测失败应重新打开"""
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0)
        cb.record_failure()
        cb._state = CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_decorator_pattern(self):
        """装饰器模式应正常工作"""
        cb = CircuitBreaker(name="decorator_test", failure_threshold=2, recovery_timeout=60)

        @cb
        def success_func():
            return "ok"

        assert success_func() == "ok"
        assert cb.state == CircuitState.CLOSED

    def test_get_circuit_breaker_singleton(self):
        """全局熔断器应为单例"""
        cb1 = get_circuit_breaker("singleton_test")
        cb2 = get_circuit_breaker("singleton_test")
        assert cb1 is cb2

    def test_call_success_tracks_metrics(self):
        """成功调用应正常返回结果"""
        cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout=1)

        def success_func(x, y):
            return x + y

        result = cb.call(success_func, 1, 2)
        assert result == 3
        assert cb.state == CircuitState.CLOSED
