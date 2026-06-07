"""熔断器模块 — 防止级联故障

实现简单的三态熔断器：
- CLOSED（关闭）：正常通过，记录失败次数
- OPEN（打开）：快速失败，阻止调用
- HALF_OPEN（半开）：允许单次探测，决定状态转移

Usage:
    from src.utils.circuit_breaker import circuit_breaker

    @circuit_breaker(failure_threshold=5, recovery_timeout=60)
    def call_llm(query):
        ...
"""

import functools
import os
import threading
import time
from enum import Enum

from src.utils.logger import log


class CircuitState(Enum):
    """熔断器状态"""

    CLOSED = "closed"       # 正常
    OPEN = "open"           # 熔断
    HALF_OPEN = "half_open"  # 探测


class CircuitBreaker:
    """熔断器

    环境变量覆盖：
        CIRCUIT_BREAKER_FAILURE_THRESHOLD: 失败阈值（默认 5）
        CIRCUIT_BREAKER_RECOVERY_TIMEOUT: 恢复超时秒数（默认 60）
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int | None = None,
        recovery_timeout: float | None = None,
    ):
        self.name = name
        self.failure_threshold = failure_threshold or int(
            os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5")
        )
        self.recovery_timeout = recovery_timeout or float(
            os.getenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT", "60")
        )

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._lock = threading.RLock()

    @property
    def state(self) -> CircuitState:
        """当前状态（线程安全读取）"""
        with self._lock:
            return self._state

    def _can_attempt(self) -> bool:
        """判断当前是否允许尝试调用"""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                # 检查是否超过恢复超时
                if self._last_failure_time is None:
                    self._state = CircuitState.HALF_OPEN
                    return True
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    log.info("熔断器 %s 进入半开状态，允许探测", self.name)
                    self._state = CircuitState.HALF_OPEN
                    return True
                return False
            # HALF_OPEN：只允许一次探测
            return True

    def record_success(self):
        """记录成功"""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                log.info("熔断器 %s 探测成功，关闭", self.name)
                self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None

    def record_failure(self):
        """记录失败"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                log.warning("熔断器 %s 探测失败，重新打开", self.name)
                self._state = CircuitState.OPEN
            elif self._failure_count >= self.failure_threshold:
                log.warning(
                    "熔断器 %s 打开（连续失败 %d 次）",
                    self.name,
                    self._failure_count,
                )
                self._state = CircuitState.OPEN

    def call(self, func, *args, **kwargs):
        """包装调用

        如果熔断器打开，抛出 CircuitBreakerOpen 异常。
        """
        if not self._can_attempt():
            raise CircuitBreakerOpen(f"熔断器 {self.name} 已打开，请稍后重试")

        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise

    def __call__(self, func):
        """装饰器用法"""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return self.call(func, *args, **kwargs)

        return wrapper


class CircuitBreakerOpen(Exception):
    """熔断器打开异常"""

    pass


# 全局熔断器实例（按名称管理）
_breakers: dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def get_circuit_breaker(
    name: str = "llm",
    failure_threshold: int | None = None,
    recovery_timeout: float | None = None,
) -> CircuitBreaker:
    """获取或创建熔断器实例"""
    with _breakers_lock:
        if name not in _breakers:
            _breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
        return _breakers[name]


def circuit_breaker(
    name: str = "llm",
    failure_threshold: int | None = None,
    recovery_timeout: float | None = None,
):
    """装饰器工厂：为函数添加熔断器保护

    Usage:
        @circuit_breaker(name="llm", failure_threshold=5, recovery_timeout=60)
        def generate_answer(query):
            ...
    """
    breaker = get_circuit_breaker(name, failure_threshold, recovery_timeout)
    return breaker
