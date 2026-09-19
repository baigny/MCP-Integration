from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def workspace() -> dict[str, Path]:
    """Isolated roots used by filesystem and MCP contract tests."""
    root = Path("output/test-workspaces") / uuid4().hex
    resumes = root / "resumes"
    output = root / "output"
    resumes.mkdir(parents=True)
    output.mkdir(parents=True)
    return {
        "root": root.resolve(),
        "resumes": resumes.resolve(),
        "output": output.resolve(),
    }
