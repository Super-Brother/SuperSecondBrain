"""监控指标模块

核心指标：
- 请求延迟（P50/P95/P99）
- 检索延迟
- LLM 调用延迟
- Token 使用量
- 缓存命中率
- 错误率

Usage:
    from src.utils.metrics import MetricsCollector

    metrics = MetricsCollector()
    metrics.record_latency("retrieval", duration_ms)
    metrics.record_token_usage(prompt_tokens, completion_tokens)
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Histogram:
    """简单直方图（用于计算分位数）"""
    values: list[float] = field(default_factory=list)
    max_size: int = 10000

    def record(self, value: float):
        self.values.append(value)
        if len(self.values) > self.max_size:
            self.values = self.values[-self.max_size:]

    def percentile(self, p: float) -> float:
        if not self.values:
            return 0.0
        sorted_vals = sorted(self.values)
        idx = int(len(sorted_vals) * p / 100)
        return sorted_vals[min(idx, len(sorted_vals) - 1)]

    def mean(self) -> float:
        if not self.values:
            return 0.0
        return sum(self.values) / len(self.values)


class MetricsCollector:
    """指标收集器"""

    def __init__(self):
        self.latency_histograms: dict[str, Histogram] = defaultdict(Histogram)
        self.counters: dict[str, int] = defaultdict(int)
        self.token_usage = {"prompt": 0, "completion": 0}
        self._start_times: dict[str, float] = {}

    # ---- 延迟指标 ----

    def start_timer(self, name: str):
        """开始计时"""
        self._start_times[name] = time.time()

    def stop_timer(self, name: str) -> float:
        """停止计时并记录（返回毫秒）"""
        start = self._start_times.pop(name, None)
        if start is None:
            return 0.0
        duration_ms = (time.time() - start) * 1000
        self.record_latency(name, duration_ms)
        return duration_ms

    def record_latency(self, name: str, duration_ms: float):
        """记录延迟"""
        self.latency_histograms[name].record(duration_ms)

    # ---- 计数器 ----

    def increment(self, name: str, value: int = 1):
        """增加计数器"""
        self.counters[name] += value

    # ---- Token 使用 ----

    def record_token_usage(self, prompt_tokens: int, completion_tokens: int):
        """记录 Token 使用量"""
        self.token_usage["prompt"] += prompt_tokens
        self.token_usage["completion"] += completion_tokens

    # ---- 汇总 ----

    def get_summary(self) -> dict[str, Any]:
        """获取指标摘要"""
        latency_summary = {}
        for name, hist in self.latency_histograms.items():
            latency_summary[name] = {
                "count": len(hist.values),
                "mean_ms": round(hist.mean(), 2),
                "p50_ms": round(hist.percentile(50), 2),
                "p95_ms": round(hist.percentile(95), 2),
                "p99_ms": round(hist.percentile(99), 2),
            }

        return {
            "latency": latency_summary,
            "counters": dict(self.counters),
            "token_usage": self.token_usage,
        }

    def reset(self):
        """重置所有指标"""
        self.latency_histograms.clear()
        self.counters.clear()
        self.token_usage = {"prompt": 0, "completion": 0}
        self._start_times.clear()


# 全局实例（单例模式）
_metrics_instance: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    """获取全局指标收集器"""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = MetricsCollector()
    return _metrics_instance
