"""Run slow jobs (searching, contact lookup, sending) in a background thread.

The web UI starts a task, then polls GET /api/tasks/{id} for progress.
Only one task of each kind runs at a time.
"""

import threading
import traceback
import uuid
from datetime import datetime, timezone
from typing import Callable


class Cancelled(Exception):
    pass


class Task:
    def __init__(self, kind: str, label: str):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.label = label
        self.state = "running"  # running | done | error | cancelled
        self.done = 0
        self.total = 0
        self.message = "Starting…"
        self.error = ""
        self.result: dict = {}
        self.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._cancel = threading.Event()

    def step(self, message: str, done: int | None = None, total: int | None = None) -> None:
        if self._cancel.is_set():
            raise Cancelled()
        self.message = message
        if done is not None:
            self.done = done
        if total is not None:
            self.total = total

    def sleep(self, seconds: float) -> None:
        """Wait, but wake up straight away if the task is cancelled."""
        if self._cancel.wait(seconds):
            raise Cancelled()

    def cancel(self) -> None:
        self._cancel.set()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "state": self.state,
            "done": self.done,
            "total": self.total,
            "message": self.message,
            "error": self.error,
            "result": self.result,
            "started_at": self.started_at,
        }


class TaskManager:
    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()

    def running(self, kind: str) -> Task | None:
        return next((t for t in self._tasks.values() if t.kind == kind and t.state == "running"), None)

    def start(self, kind: str, label: str, fn: Callable[[Task], dict | None]) -> Task:
        with self._lock:
            if busy := self.running(kind):
                return busy
            task = Task(kind, label)
            self._tasks[task.id] = task

        def run():
            try:
                task.result = fn(task) or {}
                task.state = "done"
            except Cancelled:
                task.state = "cancelled"
                task.message = "Stopped."
            except Exception as e:  # surface any failure to the UI instead of dying silently
                task.state = "error"
                task.error = str(e) or e.__class__.__name__
                traceback.print_exc()

        threading.Thread(target=run, daemon=True).start()
        return task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def active(self) -> list[Task]:
        return [t for t in self._tasks.values() if t.state == "running"]

    def recent(self) -> list[Task]:
        """The latest task of each kind, finished or not - so results survive a page reload."""
        latest: dict[str, Task] = {}
        for t in self._tasks.values():
            if t.kind not in latest or t.started_at >= latest[t.kind].started_at:
                latest[t.kind] = t
        return list(latest.values())
