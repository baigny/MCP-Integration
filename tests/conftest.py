from pathlib import Path

import pytest


@pytest.fixture
def workspace(tmp_path: Path) -> dict[str, Path]:
    """Isolated roots used by filesystem and MCP contract tests."""
    resumes = tmp_path / "resumes"
    output = tmp_path / "output"
    resumes.mkdir()
    output.mkdir()
    return {"root": tmp_path, "resumes": resumes, "output": output}

