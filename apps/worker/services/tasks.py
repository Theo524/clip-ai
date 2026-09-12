from __future__ import annotations

from concurrent.futures import CancelledError
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import threading
import uuid
from typing import Any, Callable


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _RuntimeTask:
    cancel_event: threading.Event


class TaskManager:
    """In-process task runner with durable task history.

    Running/queued tasks cannot survive a Python process crash, but their records do.
    On the next launch they are marked as interrupted + recoverable instead of silently
    disappearing. The worker can then resume the associated project from its persisted
    source/transcript/ranking checkpoints.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, dict[str, Any]] = {}
        self._runtime: dict[str, _RuntimeTask] = {}
        self._state_path: Path | None = None

    def configure(self, work_root: Path) -> None:
        state_dir = Path(work_root) / "_state"
        state_dir.mkdir(parents=True, exist_ok=True)
        self._state_path = state_dir / "tasks.json"
        self._load()

    def _load(self) -> None:
        if self._state_path is None or not self._state_path.exists():
            return
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
            records = payload if isinstance(payload, list) else payload.get("tasks", [])
            for record in records:
                if not isinstance(record, dict) or not record.get("task_id"):
                    continue
                item = dict(record)
                if item.get("status") in {"queued", "running"}:
                    item.update({
                        "status": "failed",
                        "stage": "Interrupted",
                        "message": "Clip AI stopped before this task finished. The saved project can be resumed.",
                        "error": "Interrupted by a previous app shutdown or crash.",
                        "recoverable": True,
                        "updated_at": _now(),
                    })
                self._items[str(item["task_id"])] = item
            self._prune_locked()
            self._persist_locked()
        except Exception:
            # A corrupt task-history file must never prevent Clip AI from starting.
            self._items = {}

    def _persist_locked(self) -> None:
        if self._state_path is None:
            return
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self._state_path.with_suffix(".json.tmp")
            ordered = sorted(self._items.values(), key=lambda x: x.get("created_at", ""), reverse=True)
            temp.write_text(json.dumps({"schema": 1, "tasks": ordered}, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(self._state_path)
        except OSError:
            pass

    def _prune_locked(self, limit: int = 250) -> None:
        if len(self._items) <= limit:
            return
        ordered = sorted(self._items.values(), key=lambda x: x.get("created_at", ""), reverse=True)
        keep = {item["task_id"] for item in ordered[:limit]}
        self._items = {k: v for k, v in self._items.items() if k in keep}

    def create(
        self,
        kind: str,
        runner: Callable[[str, threading.Event], Any],
        *,
        job_id: str | None = None,
        spec: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
            "recoverable": bool(job_id),
            "spec": spec or {},
            "created_at": _now(),
            "updated_at": _now(),
        }
        with self._lock:
            self._items[task_id] = record
            self._runtime[task_id] = _RuntimeTask(cancel_event=cancel_event)
            self._prune_locked()
            self._persist_locked()

        thread = threading.Thread(target=self._run, args=(task_id, runner), daemon=True, name=f"clip-ai-{kind}-{task_id[:8]}")
        thread.start()
        return dict(record)

    def _run(self, task_id: str, runner: Callable[[str, threading.Event], Any]) -> None:
        runtime = self._runtime[task_id]
        self.update(task_id, status="running", stage="Starting", progress=1, message="Starting…", error=None)
        try:
            result = runner(task_id, runtime.cancel_event)
            if runtime.cancel_event.is_set():
                raise CancelledError()
            if hasattr(result, "model_dump"):
                result = result.model_dump(mode="json")
            self.update(task_id, status="completed", stage="Done", progress=100, message="Finished", result=result, recoverable=False)
        except CancelledError:
            self.update(task_id, status="cancelled", stage="Cancelled", message="Cancelled by user")
        except Exception as exc:
            self.update(
                task_id,
                status="failed",
                stage="Failed",
                message="The task stopped with an error",
                error=str(getattr(exc, "detail", exc)),
                recoverable=bool(self.get(task_id).get("job_id") if self.get(task_id) else False),
            )
        finally:
            with self._lock:
                self._runtime.pop(task_id, None)
                self._persist_locked()

    def update(self, task_id: str, **patch: Any) -> dict[str, Any]:
        with self._lock:
            if task_id not in self._items:
                raise KeyError(task_id)
            record = self._items[task_id]
            if "progress" in patch:
                patch["progress"] = max(0, min(100, int(patch["progress"])))
            record.update(patch)
            record["updated_at"] = _now()
            self._persist_locked()
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

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            values = sorted(self._items.values(), key=lambda x: x.get("created_at", ""), reverse=True)
            return [dict(item) for item in values[: max(1, min(limit, 250))]]

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
                self._persist_locked()
            return dict(record)


tasks = TaskManager()
