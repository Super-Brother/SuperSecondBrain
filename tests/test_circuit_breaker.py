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


class TestCircuitBreakerPerNameConfig:
    """按名称独立配置测试"""

    def test_name_specific_env_var(self, monkeypatch):
        """按名称的环境变量应生效"""
        monkeypatch.setenv("CIRCUIT_BREAKER_SUMMARIZER_FAILURE_THRESHOLD", "3")
        monkeypatch.setenv("CIRCUIT_BREAKER_SUMMARIZER_RECOVERY_TIMEOUT", "30")

        cb = CircuitBreaker(name="summarizer")
        assert cb.failure_threshold == 3
        assert cb.recovery_timeout == 30.0

    def test_fallback_to_generic_env_var(self, monkeypatch):
        """没有名称特定配置时回退到通用配置"""
        monkeypatch.delenv("CIRCUIT_BREAKER_OTHER_FAILURE_THRESHOLD", raising=False)
        monkeypatch.setenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "7")

        cb = CircuitBreaker(name="other")
        assert cb.failure_threshold == 7

    def test_explicit_param_overrides_env(self, monkeypatch):
        """显式参数应覆盖环境变量"""
        monkeypatch.setenv("CIRCUIT_BREAKER_SUMMARIZER_FAILURE_THRESHOLD", "10")

        cb = CircuitBreaker(name="summarizer", failure_threshold=2)
        assert cb.failure_threshold == 2

    def test_summarizer_is_independent_from_llm(self, monkeypatch):
        """summarizer 和 llm 熔断器应相互独立"""
        monkeypatch.setenv("CIRCUIT_BREAKER_SUMMARIZER_FAILURE_THRESHOLD", "2")
        monkeypatch.setenv("CIRCUIT_BREAKER_LLM_FAILURE_THRESHOLD", "5")

        cb_summarizer = CircuitBreaker(name="summarizer")
        cb_llm = CircuitBreaker(name="llm")

        assert cb_summarizer.failure_threshold == 2
        assert cb_llm.failure_threshold == 5
