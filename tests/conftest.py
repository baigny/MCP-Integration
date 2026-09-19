from pathlib import Path
import shutil
from collections.abc import Iterator
from uuid import uuid4

import pytest


@pytest.fixture
def workspace() -> Iterator[dict[str, Path]]:
    """Isolated roots used by filesystem and MCP contract tests."""
    workspace_root = Path("output/test-workspaces")
    root = workspace_root / uuid4().hex
    resumes = root / "resumes"
    output = root / "output"
    resumes.mkdir(parents=True)
    output.mkdir(parents=True)
    try:
        yield {
            "root": root.resolve(),
            "resumes": resumes.resolve(),
            "output": output.resolve(),
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)
        try:
            workspace_root.rmdir()
        except OSError:
            pass
