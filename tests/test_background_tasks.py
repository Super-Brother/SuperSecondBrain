import time

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
