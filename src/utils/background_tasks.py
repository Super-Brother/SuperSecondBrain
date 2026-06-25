"""Simple in-process background task registry for desktop workflows."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable


@dataclass
class BackgroundTask:
    task_id: str
    kind: str
    status: str = "queued"
    message: str = ""
    progress: float = 0.0
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class TaskRegistry:
    def __init__(self):
        self._tasks: dict[str, BackgroundTask] = {}
        self._lock = threading.Lock()

    def start(self, kind: str, fn: Callable[[], dict[str, Any]]) -> BackgroundTask:
        task = BackgroundTask(task_id=str(uuid.uuid4()), kind=kind)
        with self._lock:
            self._tasks[task.task_id] = task

        thread = threading.Thread(target=self._run, args=(task.task_id, fn), daemon=True)
        thread.start()
        return task

    def start_unique(self, kind: str, fn: Callable[[], dict[str, Any]]) -> BackgroundTask:
        with self._lock:
            for task in self._tasks.values():
                if task.kind == kind and task.status in {"queued", "running"}:
                    return task

            task = BackgroundTask(task_id=str(uuid.uuid4()), kind=kind)
            self._tasks[task.task_id] = task

        thread = threading.Thread(target=self._run, args=(task.task_id, fn), daemon=True)
        thread.start()
        return task

    def get(self, task_id: str) -> BackgroundTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def as_dict(self, task_id: str) -> dict[str, Any] | None:
        task = self.get(task_id)
        return asdict(task) if task else None

    def _update(self, task_id: str, **changes: Any) -> None:
        with self._lock:
            task = self._tasks[task_id]
            for key, value in changes.items():
                setattr(task, key, value)
            task.updated_at = time.time()

    def _run(self, task_id: str, fn: Callable[[], dict[str, Any]]) -> None:
        self._update(task_id, status="running", message="任务运行中", progress=0.1)
        try:
            result = fn()
        except Exception as exc:
            self._update(task_id, status="failed", message="任务失败", error=str(exc), progress=1.0)
            return
        self._update(task_id, status="succeeded", message="任务完成", result=result, progress=1.0)


task_registry = TaskRegistry()
