from __future__ import annotations

from concurrent.futures import CancelledError
from dataclasses import dataclass
from datetime import datetime, timezone
import threading
import uuid
from typing import Any, Callable


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _RuntimeTask:
    cancel_event: threading.Event


class TaskManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, dict[str, Any]] = {}
        self._runtime: dict[str, _RuntimeTask] = {}

    def create(self, kind: str, runner: Callable[[str, threading.Event], Any], *, job_id: str | None = None) -> dict[str, Any]:
        task_id = str(uuid.uuid4())
        cancel_event = threading.Event()
        record = {
            "task_id": task_id,
            "kind": kind,
            "status": "queued",
            "stage": "Queued",
            "progress": 0,
            "message": "Waiting to start…",
            "job_id": job_id,
            "result": None,
            "error": None,
            "created_at": _now(),
            "updated_at": _now(),
        }
        with self._lock:
            self._items[task_id] = record
            self._runtime[task_id] = _RuntimeTask(cancel_event=cancel_event)

        thread = threading.Thread(target=self._run, args=(task_id, runner), daemon=True, name=f"clip-ai-{kind}-{task_id[:8]}")
        thread.start()
        return dict(record)

    def _run(self, task_id: str, runner: Callable[[str, threading.Event], Any]) -> None:
        runtime = self._runtime[task_id]
        self.update(task_id, status="running", stage="Starting", progress=1, message="Starting…")
        try:
            result = runner(task_id, runtime.cancel_event)
            if runtime.cancel_event.is_set():
                raise CancelledError()
            if hasattr(result, "model_dump"):
                result = result.model_dump(mode="json")
            self.update(task_id, status="completed", stage="Done", progress=100, message="Finished", result=result)
        except CancelledError:
            self.update(task_id, status="cancelled", stage="Cancelled", message="Cancelled by user")
        except Exception as exc:
            self.update(task_id, status="failed", stage="Failed", message="The task stopped with an error", error=str(getattr(exc, "detail", exc)))
        finally:
            with self._lock:
                self._runtime.pop(task_id, None)

    def update(self, task_id: str, **patch: Any) -> dict[str, Any]:
        with self._lock:
            if task_id not in self._items:
                raise KeyError(task_id)
            record = self._items[task_id]
            if "progress" in patch:
                patch["progress"] = max(0, min(100, int(patch["progress"])))
            record.update(patch)
            record["updated_at"] = _now()
            return dict(record)

    def progress(self, task_id: str, progress: int, stage: str, message: str | None = None) -> None:
        patch: dict[str, Any] = {"progress": progress, "stage": stage}
        if message is not None:
            patch["message"] = message
        self.update(task_id, **patch)

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._items.get(task_id)
            return dict(record) if record else None

    def cancel(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._items.get(task_id)
            if record is None:
                return None
            runtime = self._runtime.get(task_id)
            if runtime is not None:
                runtime.cancel_event.set()
            if record["status"] in {"queued", "running"}:
                record["stage"] = "Cancelling"
                record["message"] = "Stopping safely at the next checkpoint…"
                record["updated_at"] = _now()
            return dict(record)


tasks = TaskManager()
