import time
from threading import Event

from src.utils.background_tasks import TaskRegistry


def wait_for_done(registry: TaskRegistry, task_id: str):
    for _ in range(50):
        task = registry.get(task_id)
        if task and task.status in {"succeeded", "failed"}:
            return task
        time.sleep(0.02)
    raise AssertionError("task did not finish")


def test_task_registry_records_success():
    registry = TaskRegistry()

    task = registry.start("demo", lambda: {"ok": True})
    finished = wait_for_done(registry, task.task_id)

    assert finished.status == "succeeded"
    assert finished.result == {"ok": True}
    assert finished.progress == 1.0


def test_task_registry_records_failure():
    registry = TaskRegistry()

    def boom():
        raise RuntimeError("bad task")

    task = registry.start("demo", boom)
    finished = wait_for_done(registry, task.task_id)

    assert finished.status == "failed"
    assert finished.error == "bad task"
    assert finished.progress == 1.0


def test_start_unique_reuses_active_task():
    registry = TaskRegistry()
    started = Event()
    release = Event()

    def blocked_task():
        started.set()
        release.wait(timeout=2)
        return {"ok": True}

    first = registry.start_unique("index_build", blocked_task)
    assert started.wait(timeout=1)

    duplicate = registry.start_unique("index_build", blocked_task)
    assert duplicate.task_id == first.task_id

    release.set()
    wait_for_done(registry, first.task_id)

    next_task = registry.start_unique("index_build", lambda: {"ok": True})
    assert next_task.task_id != first.task_id
