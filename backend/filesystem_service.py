"""Safe filesystem operations used by the MCP server.

The service owns path authorization and stable response envelopes. Format-specific
document parsing/writing remains in the proven Milestone 1 implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from backend import fs_tools


SUPPORTED_EXTENSIONS = frozenset({".txt", ".pdf", ".docx", ".pptx"})


def _success(data: dict[str, Any]) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}


def _failure(code: str, message: str) -> dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message},
    }


class FileSystemService:
    """Perform file operations within explicit read and write boundaries."""

    def __init__(
        self,
        allowed_roots: Iterable[str | Path],
        writable_roots: Iterable[str | Path] = (),
    ) -> None:
        self.allowed_roots = self._normalize_roots(allowed_roots)
        self.writable_roots = self._normalize_roots(writable_roots)
        if not self.allowed_roots:
            raise ValueError("At least one allowed root is required")
        if any(not self._is_within(root, self.allowed_roots) for root in self.writable_roots):
            raise ValueError("Every writable root must be within an allowed root")

    @staticmethod
    def _normalize_roots(roots: Iterable[str | Path]) -> tuple[Path, ...]:
        return tuple(Path(root).expanduser().resolve() for root in roots)

    @staticmethod
    def _is_within(path: Path, roots: tuple[Path, ...]) -> bool:
        return any(path == root or root in path.parents for root in roots)

    def _authorize(self, path: str | Path, *, write: bool = False) -> Path | None:
        resolved = Path(path).expanduser().resolve(strict=False)
        roots = self.writable_roots if write else self.allowed_roots
        return resolved if self._is_within(resolved, roots) else None

    @staticmethod
    def _validate_extension(path: Path) -> dict[str, Any] | None:
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return _failure(
                "unsupported_extension",
                f"Unsupported extension: {path.suffix.lower() or '<none>'}",
            )
        return None

    def list_files(
        self, directory: str | Path, extension: str | None = None
    ) -> dict[str, Any]:
        resolved = self._authorize(directory)
        if resolved is None:
            return _failure("forbidden_path", "Directory is outside the allowed roots")
        if not resolved.exists():
            return _failure("not_found", "Directory does not exist")
        if not resolved.is_dir():
            return _failure("not_directory", "Path is not a directory")

        normalized_extension = extension.lower() if extension else None
        if normalized_extension and not normalized_extension.startswith("."):
            normalized_extension = f".{normalized_extension}"

        files = []
        for path in sorted(resolved.iterdir(), key=lambda item: item.name.lower()):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if normalized_extension and path.suffix.lower() != normalized_extension:
                continue
            stat = path.stat()
            files.append(
                {
                    "name": path.name,
                    "relative_path": path.relative_to(resolved).as_posix(),
                    "extension": path.suffix.lower(),
                    "size_bytes": stat.st_size,
                    "modified": stat.st_mtime,
                }
            )
        return _success({"directory": str(resolved), "files": files})

    def read_file(self, filepath: str | Path) -> dict[str, Any]:
        resolved = self._authorize(filepath)
        if resolved is None:
            return _failure("forbidden_path", "File is outside the allowed roots")
        if not resolved.exists():
            return _failure("not_found", "File does not exist")
        if not resolved.is_file():
            return _failure("not_file", "Path is not a file")
        if extension_error := self._validate_extension(resolved):
            return extension_error

        result = fs_tools.read_file(str(resolved))
        if not result.get("success"):
            return _failure("read_failed", result.get("error", "Unable to read file"))
        return _success(
            {
                "path": str(resolved),
                "content": result["content"],
                "metadata": result["metadata"],
            }
        )

    def write_file(
        self,
        filepath: str | Path,
        content: str,
        *,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        resolved = self._authorize(filepath, write=True)
        if resolved is None:
            return _failure("forbidden_path", "File is outside the writable roots")
        if extension_error := self._validate_extension(resolved):
            return extension_error
        if resolved.exists() and not overwrite:
            return _failure("already_exists", "File already exists")

        result = fs_tools.write_file(str(resolved), content)
        if not result.get("success"):
            return _failure("write_failed", result.get("error", "Unable to write file"))
        return _success({"path": str(resolved), "overwritten": overwrite})

    def search_in_file(self, filepath: str | Path, keyword: str) -> dict[str, Any]:
        if not keyword.strip():
            return _failure("invalid_keyword", "Keyword must not be empty")

        resolved = self._authorize(filepath)
        if resolved is None:
            return _failure("forbidden_path", "Path is outside the allowed roots")
        if not resolved.exists():
            return _failure("not_found", "Path does not exist")

        if resolved.is_dir():
            listed = self.list_files(resolved)
            if not listed["success"]:
                return listed
            grouped_matches = []
            for entry in listed["data"]["files"]:
                child_result = self.search_in_file(resolved / entry["name"], keyword)
                if child_result["success"] and child_result["data"]["matches"]:
                    grouped_matches.append(
                        {"file": entry["name"], "matches": child_result["data"]["matches"]}
                    )
            return _success({"path": str(resolved), "matches": grouped_matches})

        read_result = self.read_file(resolved)
        if not read_result["success"]:
            return read_result

        needle = keyword.casefold()
        matches = [
            {"line_number": number, "context": line.strip()}
            for number, line in enumerate(
                read_result["data"]["content"].splitlines(), start=1
            )
            if needle in line.casefold()
        ]
        return _success({"path": str(resolved), "matches": matches})
