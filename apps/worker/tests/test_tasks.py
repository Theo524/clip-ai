import time
from concurrent.futures import CancelledError

from services.tasks import TaskManager


def wait_done(manager: TaskManager, task_id: str):
    for _ in range(100):
        item = manager.get(task_id)
        if item and item["status"] in {"completed", "failed", "cancelled"}:
            return item
        time.sleep(0.01)
    raise AssertionError("task did not finish")


def test_task_completes_and_returns_result():
    manager = TaskManager()

    def runner(task_id, cancel_event):
        manager.progress(task_id, 50, "Halfway", "Working")
        return {"ok": True}

    created = manager.create("test", runner)
    finished = wait_done(manager, created["task_id"])
    assert finished["status"] == "completed"
    assert finished["progress"] == 100
    assert finished["result"] == {"ok": True}


def test_task_can_be_cancelled():
    manager = TaskManager()

    def runner(_task_id, cancel_event):
        for _ in range(100):
            if cancel_event.is_set():
                raise CancelledError()
            time.sleep(0.01)
        return {"ok": True}

    created = manager.create("test", runner)
    manager.cancel(created["task_id"])
    finished = wait_done(manager, created["task_id"])
    assert finished["status"] == "cancelled"
