"""Directory watcher lifecycle and automatic resume ingestion."""

from __future__ import annotations

import threading
import time
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from backend.filesystem_service import FileSystemService, SUPPORTED_EXTENSIONS


Ingestor = Callable[[str | Path], dict[str, Any]]
ObserverFactory = Callable[[], Any]


def _failure(code: str, message: str) -> dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message},
    }


class _WatchEventHandler(FileSystemEventHandler):
    def __init__(self, manager: "DirectoryWatchManager", watcher_id: str) -> None:
        self.manager = manager
        self.watcher_id = watcher_id

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.manager.record_event(self.watcher_id, event.src_path, "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.manager.record_event(self.watcher_id, event.src_path, "modified")


class DirectoryWatchManager:
    """Manage Watchdog observers and expose serializable watcher status."""

    def __init__(
        self,
        service: FileSystemService,
        *,
        ingestor: Ingestor,
        observer_factory: ObserverFactory = Observer,
        executor: Executor | None = None,
        debounce_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.service = service
        self.ingestor = ingestor
        self.observer_factory = observer_factory
        self.executor = executor or ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="resume-ingest"
        )
        self.debounce_seconds = debounce_seconds
        self.clock = clock
        self._watchers: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def start(
        self, directory: str | Path, *, auto_ingest: bool = True
    ) -> dict[str, Any]:
        listed = self.service.list_files(directory)
        if not listed["success"]:
            return listed

        resolved = Path(listed["data"]["directory"])
        watcher_id = uuid4().hex
        observer = self.observer_factory()
        handler = _WatchEventHandler(self, watcher_id)
        observer.schedule(handler, str(resolved), recursive=False)

        state = {
            "watcher_id": watcher_id,
            "directory": resolved,
            "auto_ingest": auto_ingest,
            "state": "running",
            "started_at": time.time(),
            "stopped_at": None,
            "counts": {"detected": 0, "pending": 0, "processed": 0, "failed": 0},
            "events": [],
            "last_seen": {},
            "observer": observer,
        }
        with self._lock:
            self._watchers[watcher_id] = state
        try:
            observer.start()
        except Exception:
            with self._lock:
                self._watchers.pop(watcher_id, None)
            return _failure("watch_start_failed", "Directory watcher could not start")
        return self.status(watcher_id)

    def status(self, watcher_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._watchers.get(watcher_id)
            if state is None:
                return _failure("watcher_not_found", "Watcher ID was not found")
            return {
                "success": True,
                "data": {
                    "watcher_id": watcher_id,
                    "directory": str(state["directory"]),
                    "auto_ingest": state["auto_ingest"],
                    "state": state["state"],
                    "started_at": state["started_at"],
                    "stopped_at": state["stopped_at"],
                    "counts": dict(state["counts"]),
                    "events": [dict(event) for event in state["events"][-100:]],
                },
                "error": None,
            }

    def stop(self, watcher_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._watchers.get(watcher_id)
            if state is None:
                return _failure("watcher_not_found", "Watcher ID was not found")
            observer = state["observer"]
            if state["state"] == "stopped":
                return self.status(watcher_id)
            state["state"] = "stopped"
            state["stopped_at"] = time.time()

        observer.stop()
        observer.join(timeout=2.0)
        return self.status(watcher_id)

    def record_event(
        self,
        watcher_id: str,
        filepath: str | Path,
        event_type: str,
    ) -> bool:
        path = Path(filepath).expanduser().resolve(strict=False)
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return False

        now = self.clock()
        with self._lock:
            state = self._watchers.get(watcher_id)
            if state is None or state["state"] != "running":
                return False
            directory = state["directory"]
            if path != directory and directory not in path.parents:
                return False
            previous = state["last_seen"].get(path)
            if previous is not None and now - previous < self.debounce_seconds:
                return False
            state["last_seen"][path] = now
            event = {
                "path": str(path),
                "event_type": event_type,
                "detected_at": time.time(),
                "status": "detected",
                "result": None,
            }
            state["events"].append(event)
            state["counts"]["detected"] += 1
            if not state["auto_ingest"]:
                return True
            event["status"] = "pending"
            state["counts"]["pending"] += 1

        future = self.executor.submit(self.ingestor, path)
        future.add_done_callback(
            lambda completed: self._complete_ingestion(watcher_id, event, completed)
        )
        return True

    def _complete_ingestion(
        self,
        watcher_id: str,
        event: dict[str, Any],
        future: Future,
    ) -> None:
        try:
            result = future.result()
        except Exception:
            result = _failure("ingest_failed", "Resume ingestion failed")

        with self._lock:
            state = self._watchers.get(watcher_id)
            if state is None:
                return
            state["counts"]["pending"] = max(0, state["counts"]["pending"] - 1)
            event["result"] = result
            if result.get("success"):
                event["status"] = "processed"
                state["counts"]["processed"] += 1
            else:
                event["status"] = "failed"
                state["counts"]["failed"] += 1
