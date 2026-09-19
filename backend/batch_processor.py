"""Bounded concurrent processing for filesystem and ingestion operations."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Iterable

from backend.filesystem_service import FileSystemService


Ingestor = Callable[[str | Path], dict[str, Any]]
VALID_OPERATIONS = frozenset({"read", "search", "ingest"})


def _failure(code: str, message: str) -> dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message},
    }


class BatchProcessor:
    """Run independent file operations concurrently with deterministic output order."""

    def __init__(
        self,
        service: FileSystemService,
        *,
        ingestor: Ingestor | None = None,
        default_concurrency: int = 4,
    ) -> None:
        self.service = service
        self.ingestor = ingestor
        self.default_concurrency = default_concurrency

    async def process(
        self,
        paths: Iterable[str | Path],
        *,
        operation: str,
        keyword: str | None = None,
        max_concurrency: int | None = None,
    ) -> dict[str, Any]:
        normalized_operation = operation.strip().lower()
        if normalized_operation not in VALID_OPERATIONS:
            return _failure(
                "invalid_operation",
                f"Operation must be one of: {', '.join(sorted(VALID_OPERATIONS))}",
            )
        if normalized_operation == "search" and not (keyword or "").strip():
            return _failure("invalid_keyword", "Search operation requires a keyword")
        if normalized_operation == "ingest" and self.ingestor is None:
            return _failure("operation_unavailable", "No resume ingestor is configured")

        concurrency = self.default_concurrency if max_concurrency is None else max_concurrency
        if not 1 <= concurrency <= 32:
            return _failure("invalid_concurrency", "Concurrency must be between 1 and 32")

        path_list = list(paths)
        semaphore = asyncio.Semaphore(concurrency)

        async def run_one(path: str | Path) -> dict[str, Any]:
            async with semaphore:
                try:
                    result = await asyncio.to_thread(
                        self._execute,
                        path,
                        normalized_operation,
                        keyword,
                    )
                except Exception:
                    result = _failure("internal_error", "Batch item processing failed")
                return {"path": str(path), "result": result}

        results = await asyncio.gather(*(run_one(path) for path in path_list))
        succeeded = sum(1 for item in results if item["result"].get("success"))
        failed = len(results) - succeeded
        return {
            "success": failed == 0,
            "data": {
                "operation": normalized_operation,
                "results": results,
                "summary": {
                    "total": len(results),
                    "succeeded": succeeded,
                    "failed": failed,
                },
            },
            "error": (
                None
                if failed == 0
                else {
                    "code": "batch_partial_failure",
                    "message": f"{failed} batch item(s) failed",
                }
            ),
        }

    def _execute(
        self,
        path: str | Path,
        operation: str,
        keyword: str | None,
    ) -> dict[str, Any]:
        if operation == "read":
            return self.service.read_file(path)
        if operation == "search":
            return self.service.search_in_file(path, keyword or "")

        authorized = self.service.read_file(path)
        if not authorized["success"]:
            return authorized
        assert self.ingestor is not None
        return self.ingestor(path)
