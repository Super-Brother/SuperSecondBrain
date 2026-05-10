"""Obsidian Vault 文件监控器

使用 watchdog 监听 vault 目录的文件系统事件，自动触发增量索引重建。

特性：
- 防抖：连续变更后等待指定时间再触发
- 过滤：只响应 .md 文件，忽略 .obsidian/.trash 等目录
- 线程安全：索引重建加锁保护
- 错误隔离：单次重建失败不中断监控
"""

import logging
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

log = logging.getLogger(__name__)


class VaultEventHandler(FileSystemEventHandler):
    """处理 vault 文件系统事件"""

    EXCLUDE_DIRS = frozenset({".obsidian", ".trash", ".git", ".idea", ".vscode"})

    def __init__(self, watcher: "VaultWatcher"):
        self.watcher = watcher

    def on_created(self, event):
        if self._should_handle(event):
            self.watcher._schedule_rebuild()

    def on_modified(self, event):
        if self._should_handle(event):
            self.watcher._schedule_rebuild()

    def on_deleted(self, event):
        if self._should_handle(event):
            self.watcher._schedule_rebuild()

    def on_moved(self, event):
        if self._should_handle(event):
            self.watcher._schedule_rebuild()

    def _should_handle(self, event) -> bool:
        """判断是否应该处理该事件"""
        # 忽略目录事件
        if event.is_directory:
            return False

        path = Path(event.src_path)

        # 只处理 .md 文件
        if path.suffix.lower() != ".md":
            return False

        # 排除特定目录
        for part in path.parts:
            if part in self.EXCLUDE_DIRS:
                return False

        return True


class VaultWatcher:
    """Obsidian Vault 文件监控器，自动触发增量索引重建"""

    def __init__(
        self,
        vault_path: str,
        pipeline,
        debounce_seconds: float = 5.0,
    ):
        """
        Args:
            vault_path: Obsidian vault 根目录路径
            pipeline: SecondBrainPipeline 实例
            debounce_seconds: 防抖等待秒数
        """
        self.vault_path = Path(vault_path).resolve()
        self.pipeline = pipeline
        self.debounce_seconds = debounce_seconds

        self._observer: Observer | None = None
        self._debounce_timer: threading.Timer | None = None
        self._rebuild_lock = threading.Lock()
        self._started = False
        self._last_rebuild_time: float = 0.0
        self._rebuild_count = 0

    @property
    def is_running(self) -> bool:
        """监控器是否正在运行"""
        return self._started and self._observer is not None and self._observer.is_alive()

    @property
    def stats(self) -> dict:
        """返回监控统计信息"""
        return {
            "rebuild_count": self._rebuild_count,
            "last_rebuild_time": self._last_rebuild_time,
            "is_running": self.is_running,
            "vault_path": str(self.vault_path),
            "debounce_seconds": self.debounce_seconds,
        }

    def start(self) -> None:
        """启动文件监控"""
        if self._started:
            log.warning("VaultWatcher 已经在运行")
            return

        if not self.vault_path.exists():
            raise FileNotFoundError(f"Vault 路径不存在: {self.vault_path}")

        self._observer = Observer()
        handler = VaultEventHandler(self)
        self._observer.schedule(handler, str(self.vault_path), recursive=True)
        self._observer.start()
        self._started = True

        log.info("VaultWatcher 已启动: %s (debounce=%.1fs)", self.vault_path, self.debounce_seconds)

    def stop(self) -> None:
        """停止文件监控"""
        if not self._started:
            return

        # 取消待执行的重建任务
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
            self._debounce_timer = None

        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None

        self._started = False
        log.info("VaultWatcher 已停止")

    def _schedule_rebuild(self) -> None:
        """调度一次索引重建（带防抖）"""
        # 取消已存在的定时器
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()

        # 创建新定时器
        self._debounce_timer = threading.Timer(self.debounce_seconds, self._do_rebuild)
        self._debounce_timer.daemon = True
        self._debounce_timer.start()

    def _do_rebuild(self) -> None:
        """执行增量索引重建"""
        with self._rebuild_lock:
            log.info("[VaultWatcher] 开始增量索引重建...")
            start_time = time.time()

            try:
                stats = self.pipeline.build_index(incremental=True)
                elapsed = time.time() - start_time

                self._rebuild_count += 1
                self._last_rebuild_time = time.time()

                log.info(
                    "[VaultWatcher] 增量重建完成: notes=%d chunks=%d (%.2fs)",
                    stats.get("total_notes", 0),
                    stats.get("total_chunks", 0),
                    elapsed,
                )
            except Exception:
                log.exception("[VaultWatcher] 增量重建失败，将继续监听文件变更")
