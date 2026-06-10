"""监控指标模块

核心指标：
- 请求延迟（P50/P95/P99）
- 检索延迟
- LLM 调用延迟
- Token 使用量
- 缓存命中率
- 错误率

支持 SQLite 持久化：计数器和 Token 使用量在进程重启后自动恢复。

Usage:
    from src.utils.metrics import MetricsCollector

    metrics = MetricsCollector()
    metrics.record_latency("retrieval", duration_ms)
    metrics.record_token_usage(prompt_tokens, completion_tokens)
"""

import os
import sqlite3
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
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
    """指标收集器 — 支持 SQLite 持久化（计数器 + Token 使用量）"""

    def __init__(self, db_path: str = "data/metrics.db"):
        self.latency_histograms: dict[str, Histogram] = defaultdict(Histogram)
        self.counters: dict[str, int] = defaultdict(int)
        self.token_usage = {"prompt": 0, "completion": 0}
        self._start_times: dict[str, float] = {}

        # SQLite 持久化
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()
        self._load_persistent()

        # 告警阈值（从环境变量读取）
        self.alert_thresholds = {
            "p95_latency_ms": float(os.getenv("METRICS_ALERT_P95_LATENCY_MS", "5000")),
            "p99_latency_ms": float(os.getenv("METRICS_ALERT_P99_LATENCY_MS", "10000")),
            "error_rate": float(os.getenv("METRICS_ALERT_ERROR_RATE", "0.05")),
        }

    # ---- SQLite 持久化 ----

    def _init_db(self):
        """初始化 SQLite 表结构"""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metrics_counters (
                    name TEXT PRIMARY KEY,
                    value INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metrics_token_usage (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    prompt INTEGER NOT NULL,
                    completion INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

    def _persist(self):
        """将计数器和 Token 使用量持久化到 SQLite"""
        with self._lock:
            now = datetime.now().isoformat()
            with sqlite3.connect(self._db_path) as conn:
                # 保存计数器
                for name, value in self.counters.items():
                    conn.execute(
                        """INSERT INTO metrics_counters (name, value, updated_at)
                           VALUES (?, ?, ?)
                           ON CONFLICT(name) DO UPDATE SET
                           value = excluded.value,
                           updated_at = excluded.updated_at""",
                        (name, value, now),
                    )
                # 保存 Token 使用量
                conn.execute(
                    """INSERT INTO metrics_token_usage (id, prompt, completion, updated_at)
                       VALUES (1, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                       prompt = excluded.prompt,
                       completion = excluded.completion,
                       updated_at = excluded.updated_at""",
                    (self.token_usage["prompt"], self.token_usage["completion"], now),
                )

    def _load_persistent(self):
        """从 SQLite 恢复持久化数据"""
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                # 恢复计数器
                rows = conn.execute("SELECT name, value FROM metrics_counters").fetchall()
                for row in rows:
                    self.counters[row["name"]] = row["value"]
                # 恢复 Token 使用量
                row = conn.execute(
                    "SELECT prompt, completion FROM metrics_token_usage WHERE id = 1"
                ).fetchone()
                if row:
                    self.token_usage["prompt"] = row["prompt"]
                    self.token_usage["completion"] = row["completion"]
        except Exception:
            # 首次启动或数据库损坏时静默忽略，从零开始收集
            pass

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

    def _check_alerts(self) -> list[dict[str, Any]]:
        """检查是否触发告警阈值，返回告警列表"""
        alerts: list[dict[str, Any]] = []

        # 延迟告警
        for name, hist in self.latency_histograms.items():
            if not hist.values:
                continue
            p95 = hist.percentile(95)
            p99 = hist.percentile(99)
            if p95 > self.alert_thresholds["p95_latency_ms"]:
                alerts.append({
                    "severity": "warning",
                    "metric": f"latency.{name}.p95",
                    "value": round(p95, 2),
                    "threshold": self.alert_thresholds["p95_latency_ms"],
                    "message": f"{name} P95 延迟 {p95:.0f}ms 超过阈值 {self.alert_thresholds['p95_latency_ms']:.0f}ms",
                })
            if p99 > self.alert_thresholds["p99_latency_ms"]:
                alerts.append({
                    "severity": "critical",
                    "metric": f"latency.{name}.p99",
                    "value": round(p99, 2),
                    "threshold": self.alert_thresholds["p99_latency_ms"],
                    "message": f"{name} P99 延迟 {p99:.0f}ms 超过阈值 {self.alert_thresholds['p99_latency_ms']:.0f}ms",
                })

        # 错误率告警
        total_requests = sum(
            self.counters.get(f"request_{code}xx", 0)
            for code in (2, 3, 4, 5)
        )
        error_requests = self.counters.get("request_5xx", 0)
        if total_requests > 0:
            error_rate = error_requests / total_requests
            if error_rate > self.alert_thresholds["error_rate"]:
                alerts.append({
                    "severity": "critical",
                    "metric": "error_rate",
                    "value": round(error_rate, 4),
                    "threshold": self.alert_thresholds["error_rate"],
                    "message": f"错误率 {error_rate*100:.2f}% 超过阈值 {self.alert_thresholds['error_rate']*100:.2f}%",
                })

        return alerts

    def get_summary(self) -> dict[str, Any]:
        """获取指标摘要（自动触发持久化）"""
        self._persist()

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
            "token_usage": dict(self.token_usage),
            "alerts": self._check_alerts(),
            "alert_thresholds": self.alert_thresholds,
        }

    def reset(self):
        """重置所有指标（同时清空持久化数据）"""
        self.latency_histograms.clear()
        self.counters.clear()
        self.token_usage = {"prompt": 0, "completion": 0}
        self._start_times.clear()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM metrics_counters")
            conn.execute("DELETE FROM metrics_token_usage")

    # ---- Prometheus 导出 ----

    def to_prometheus(self) -> str:
        """生成 Prometheus text exposition format"""
        lines: list[str] = []

        # 延迟直方图 —— 按 name 输出 summary 分位数
        for name, hist in self.latency_histograms.items():
            if not hist.values:
                continue
            safe_name = name.replace("-", "_").replace(" ", "_")
            metric_base = f"secondbrain_latency_ms_{safe_name}"
            lines.append(f"# HELP {metric_base} Latency in ms for {name}")
            lines.append(f"# TYPE {metric_base} summary")
            lines.append(f'{metric_base}{{quantile="0.5"}} {hist.percentile(50):.3f}')
            lines.append(f'{metric_base}{{quantile="0.95"}} {hist.percentile(95):.3f}')
            lines.append(f'{metric_base}{{quantile="0.99"}} {hist.percentile(99):.3f}')
            lines.append(f"{metric_base}_count {len(hist.values)}")
            lines.append(f"{metric_base}_sum {sum(hist.values):.3f}")

        # 计数器
        if self.counters:
            lines.append("# HELP secondbrain_counter Counter values")
            lines.append("# TYPE secondbrain_counter counter")
            for name, value in self.counters.items():
                safe_name = name.replace("-", "_").replace(" ", "_")
                lines.append(f'secondbrain_counter{{name="{safe_name}"}} {value}')

        # Token 使用量
        lines.append("# HELP secondbrain_token_usage_total Total token usage")
        lines.append("# TYPE secondbrain_token_usage_total counter")
        lines.append(f'secondbrain_token_usage_total{{type="prompt"}} {self.token_usage["prompt"]}')
        lines.append(f'secondbrain_token_usage_total{{type="completion"}} {self.token_usage["completion"]}')

        return "\n".join(lines) + "\n"


# 全局实例（单例模式）
_metrics_instance: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    """获取全局指标收集器"""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = MetricsCollector()
    return _metrics_instance
