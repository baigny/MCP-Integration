from pathlib import Path

import pytest

from backend.batch_processor import BatchProcessor
from backend.filesystem_service import FileSystemService


@pytest.fixture
def processor(workspace: dict[str, Path]) -> BatchProcessor:
    service = FileSystemService(
        allowed_roots=[workspace["resumes"], workspace["output"]],
        writable_roots=[workspace["output"]],
    )
    return BatchProcessor(service)


@pytest.mark.asyncio
async def test_batch_read_preserves_input_order_and_summarizes_results(
    processor: BatchProcessor, workspace: dict[str, Path]
) -> None:
    first = workspace["resumes"] / "first.txt"
    missing = workspace["resumes"] / "missing.txt"
    second = workspace["resumes"] / "second.txt"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    result = await processor.process([first, missing, second], operation="read")

    assert result["success"] is False
    assert [item["path"] for item in result["data"]["results"]] == [
        str(first),
        str(missing),
        str(second),
    ]
    assert result["data"]["summary"] == {
        "total": 3,
        "succeeded": 2,
        "failed": 1,
    }


@pytest.mark.asyncio
async def test_batch_search_requires_keyword(
    processor: BatchProcessor, workspace: dict[str, Path]
) -> None:
    result = await processor.process(
        [workspace["resumes"] / "candidate.txt"], operation="search"
    )

    assert result["success"] is False
    assert result["error"]["code"] == "invalid_keyword"


@pytest.mark.asyncio
async def test_batch_searches_multiple_files(
    processor: BatchProcessor, workspace: dict[str, Path]
) -> None:
    first = workspace["resumes"] / "first.txt"
    second = workspace["resumes"] / "second.txt"
    first.write_text("Python", encoding="utf-8")
    second.write_text("Java", encoding="utf-8")

    result = await processor.process(
        [first, second], operation="search", keyword="python"
    )

    assert result["success"] is True
    assert len(result["data"]["results"][0]["result"]["data"]["matches"]) == 1
    assert result["data"]["results"][1]["result"]["data"]["matches"] == []


@pytest.mark.asyncio
async def test_batch_ingest_uses_injected_ingestor(
    workspace: dict[str, Path],
) -> None:
    resume = workspace["resumes"] / "candidate.txt"
    resume.write_text("Python", encoding="utf-8")
    calls = []

    def ingest(path: str | Path) -> dict:
        calls.append(str(path))
        return {"success": True, "data": {"chunks": 3}, "error": None}

    service = FileSystemService([workspace["resumes"]])
    processor = BatchProcessor(service, ingestor=ingest)

    result = await processor.process([resume], operation="ingest")

    assert result["success"] is True
    assert calls == [str(resume)]
    assert result["data"]["results"][0]["result"]["data"]["chunks"] == 3


@pytest.mark.asyncio
async def test_batch_rejects_unknown_operation(
    processor: BatchProcessor, workspace: dict[str, Path]
) -> None:
    result = await processor.process(
        [workspace["resumes"] / "candidate.txt"], operation="delete"
    )

    assert result["success"] is False
    assert result["error"]["code"] == "invalid_operation"


@pytest.mark.asyncio
async def test_batch_rejects_invalid_concurrency(
    processor: BatchProcessor, workspace: dict[str, Path]
) -> None:
    result = await processor.process(
        [workspace["resumes"] / "candidate.txt"],
        operation="read",
        max_concurrency=0,
    )

    assert result["success"] is False
    assert result["error"]["code"] == "invalid_concurrency"

