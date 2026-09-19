from pathlib import Path

import pytest

from backend.filesystem_service import FileSystemService


@pytest.fixture
def service(workspace: dict[str, Path]) -> FileSystemService:
    return FileSystemService(
        allowed_roots=[workspace["resumes"], workspace["output"]],
        writable_roots=[workspace["output"]],
    )


def test_lists_supported_files_with_metadata(
    service: FileSystemService, workspace: dict[str, Path]
) -> None:
    (workspace["resumes"] / "candidate.txt").write_text("Python", encoding="utf-8")
    (workspace["resumes"] / "ignored.csv").write_text("name", encoding="utf-8")

    result = service.list_files(workspace["resumes"])

    assert result["success"] is True
    assert [entry["name"] for entry in result["data"]["files"]] == ["candidate.txt"]
    assert result["data"]["files"][0]["size_bytes"] == 6


def test_reads_supported_text_file(
    service: FileSystemService, workspace: dict[str, Path]
) -> None:
    resume = workspace["resumes"] / "candidate.txt"
    resume.write_text("Python and FastAPI", encoding="utf-8")

    result = service.read_file(resume)

    assert result["success"] is True
    assert result["data"]["content"] == "Python and FastAPI"
    assert result["data"]["metadata"]["extension"] == ".txt"


def test_searches_directory_case_insensitively(
    service: FileSystemService, workspace: dict[str, Path]
) -> None:
    (workspace["resumes"] / "one.txt").write_text("Python developer", encoding="utf-8")
    (workspace["resumes"] / "two.txt").write_text("Java developer", encoding="utf-8")

    result = service.search_in_file(workspace["resumes"], "PYTHON")

    assert result["success"] is True
    assert result["data"]["matches"] == [
        {
            "file": "one.txt",
            "matches": [{"line_number": 1, "context": "Python developer"}],
        }
    ]


def test_writes_only_inside_writable_root_without_overwrite(
    service: FileSystemService, workspace: dict[str, Path]
) -> None:
    target = workspace["output"] / "report.txt"

    created = service.write_file(target, "first")
    blocked = service.write_file(target, "second")
    replaced = service.write_file(target, "second", overwrite=True)

    assert created["success"] is True
    assert blocked["success"] is False
    assert blocked["error"]["code"] == "already_exists"
    assert replaced["success"] is True
    assert target.read_text(encoding="utf-8") == "second"


def test_rejects_paths_outside_allowed_roots(
    service: FileSystemService, workspace: dict[str, Path]
) -> None:
    outside = workspace["root"] / "private.txt"
    outside.write_text("secret", encoding="utf-8")

    result = service.read_file(outside)

    assert result["success"] is False
    assert result["error"]["code"] == "forbidden_path"


def test_rejects_write_to_read_only_root(
    service: FileSystemService, workspace: dict[str, Path]
) -> None:
    result = service.write_file(workspace["resumes"] / "new.txt", "content")

    assert result["success"] is False
    assert result["error"]["code"] == "forbidden_path"


def test_rejects_unsupported_extension(
    service: FileSystemService, workspace: dict[str, Path]
) -> None:
    unsupported = workspace["resumes"] / "candidate.csv"
    unsupported.write_text("name,skill", encoding="utf-8")

    result = service.read_file(unsupported)

    assert result["success"] is False
    assert result["error"]["code"] == "unsupported_extension"


def test_reports_missing_file(service: FileSystemService, workspace: dict[str, Path]) -> None:
    result = service.read_file(workspace["resumes"] / "missing.txt")

    assert result["success"] is False
    assert result["error"]["code"] == "not_found"
