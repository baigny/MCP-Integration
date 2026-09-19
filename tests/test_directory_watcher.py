from concurrent.futures import Future
from pathlib import Path

import pytest

from backend.directory_watcher import DirectoryWatchManager
from backend.filesystem_service import FileSystemService


class FakeObserver:
    def __init__(self) -> None:
        self.handler = None
        self.directory = None
        self.started = False
        self.stopped = False

    def schedule(self, handler, directory: str, recursive: bool = False) -> None:
        self.handler = handler
        self.directory = directory

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def join(self, timeout: float | None = None) -> None:
        return None


class InlineExecutor:
    def submit(self, function, *args, **kwargs) -> Future:
        future = Future()
        try:
            future.set_result(function(*args, **kwargs))
        except Exception as exc:  # pragma: no cover - mirrors Executor behavior
            future.set_exception(exc)
        return future


@pytest.fixture
def watch_setup(workspace: dict[str, Path]):
    observers = []
    ingested = []

    def observer_factory():
        observer = FakeObserver()
        observers.append(observer)
        return observer

    def ingestor(path: str | Path) -> dict:
        ingested.append(str(path))
        return {"success": True, "data": {"chunks": 2}, "error": None}

    service = FileSystemService([workspace["resumes"]])
    manager = DirectoryWatchManager(
        service,
        ingestor=ingestor,
        observer_factory=observer_factory,
        executor=InlineExecutor(),
        debounce_seconds=1.0,
        clock=lambda: 100.0,
    )
    return manager, observers, ingested


def test_starts_watcher_for_allowed_directory(watch_setup, workspace) -> None:
    manager, observers, _ = watch_setup

    result = manager.start(workspace["resumes"], auto_ingest=True)

    assert result["success"] is True
    assert result["data"]["state"] == "running"
    assert observers[0].started is True
    assert observers[0].directory == str(workspace["resumes"])


def test_rejects_directory_outside_allowed_roots(watch_setup, workspace) -> None:
    manager, _, _ = watch_setup

    result = manager.start(workspace["root"])

    assert result["success"] is False
    assert result["error"]["code"] == "forbidden_path"


def test_records_supported_event_and_auto_ingests(watch_setup, workspace) -> None:
    manager, _, ingested = watch_setup
    started = manager.start(workspace["resumes"], auto_ingest=True)
    watcher_id = started["data"]["watcher_id"]
    resume = workspace["resumes"] / "candidate.txt"
    resume.write_text("Python", encoding="utf-8")

    accepted = manager.record_event(watcher_id, resume, "created")
    status = manager.status(watcher_id)

    assert accepted is True
    assert ingested == [str(resume)]
    assert status["data"]["counts"] == {
        "detected": 1,
        "pending": 0,
        "processed": 1,
        "failed": 0,
    }


def test_ignores_unsupported_and_debounces_duplicate_events(
    watch_setup, workspace
) -> None:
    manager, _, _ = watch_setup
    watcher_id = manager.start(workspace["resumes"])["data"]["watcher_id"]
    resume = workspace["resumes"] / "candidate.txt"
    resume.write_text("Python", encoding="utf-8")

    unsupported = manager.record_event(
        watcher_id, workspace["resumes"] / "candidate.csv", "created"
    )
    first = manager.record_event(watcher_id, resume, "created")
    duplicate = manager.record_event(watcher_id, resume, "modified")

    assert unsupported is False
    assert first is True
    assert duplicate is False
    assert manager.status(watcher_id)["data"]["counts"]["detected"] == 1


def test_status_rejects_unknown_watcher(watch_setup) -> None:
    manager, _, _ = watch_setup

    result = manager.status("missing")

    assert result["success"] is False
    assert result["error"]["code"] == "watcher_not_found"


def test_stops_running_watcher(watch_setup, workspace) -> None:
    manager, observers, _ = watch_setup
    watcher_id = manager.start(workspace["resumes"])["data"]["watcher_id"]

    result = manager.stop(watcher_id)

    assert result["success"] is True
    assert result["data"]["state"] == "stopped"
    assert observers[0].stopped is True

