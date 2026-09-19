import json
from pathlib import Path

import pytest

from backend.filesystem_service import FileSystemService
from filesystem_mcp_server import create_server


@pytest.fixture
def mcp_server(workspace: dict[str, Path]):
    service = FileSystemService(
        allowed_roots=[workspace["resumes"], workspace["output"]],
        writable_roots=[workspace["output"]],
    )
    return create_server(service, resume_root=workspace["resumes"])


@pytest.mark.asyncio
async def test_discovers_milestone_one_tools(mcp_server) -> None:
    tools = await mcp_server.list_tools()

    assert {tool.name for tool in tools} == {
        "list_files",
        "read_file",
        "search_in_file",
        "write_file",
    }


@pytest.mark.asyncio
async def test_calls_read_file_tool(
    mcp_server, workspace: dict[str, Path]
) -> None:
    resume = workspace["resumes"] / "candidate.txt"
    resume.write_text("Python engineer", encoding="utf-8")

    result = await mcp_server.call_tool("read_file", {"filepath": str(resume)})

    assert result.is_error is False
    assert result.structured_content["success"] is True
    assert result.structured_content["data"]["content"] == "Python engineer"


@pytest.mark.asyncio
async def test_tool_returns_domain_error_as_structured_result(
    mcp_server, workspace: dict[str, Path]
) -> None:
    result = await mcp_server.call_tool(
        "read_file", {"filepath": str(workspace["root"] / "outside.txt")}
    )

    assert result.is_error is False
    assert result.structured_content["success"] is False
    assert result.structured_content["error"]["code"] == "forbidden_path"


@pytest.mark.asyncio
async def test_discovers_static_resources(mcp_server) -> None:
    resources = await mcp_server.list_resources()

    assert {str(resource.uri) for resource in resources} == {
        "config://server",
        "resumes://catalog",
    }


@pytest.mark.asyncio
async def test_discovers_resume_resource_template(mcp_server) -> None:
    templates = await mcp_server.list_resource_templates()

    assert {template.uri_template for template in templates} == {
        "resume://{relative_path}"
    }


@pytest.mark.asyncio
async def test_reads_resume_catalog_resource(
    mcp_server, workspace: dict[str, Path]
) -> None:
    (workspace["resumes"] / "candidate.txt").write_text("Python", encoding="utf-8")

    contents = await mcp_server.read_resource("resumes://catalog")
    payload = json.loads(list(contents)[0].content)

    assert payload["success"] is True
    assert payload["data"]["files"][0]["name"] == "candidate.txt"


@pytest.mark.asyncio
async def test_reads_resume_template_resource(
    mcp_server, workspace: dict[str, Path]
) -> None:
    (workspace["resumes"] / "candidate.txt").write_text("Python", encoding="utf-8")

    contents = await mcp_server.read_resource("resume://candidate.txt")
    payload = json.loads(list(contents)[0].content)

    assert payload["success"] is True
    assert payload["data"]["content"] == "Python"


@pytest.mark.asyncio
async def test_config_resource_does_not_expose_secrets(mcp_server) -> None:
    contents = await mcp_server.read_resource("config://server")
    payload = json.loads(list(contents)[0].content)

    assert payload["name"] == "filesystem-mcp-server"
    assert "token" not in json.dumps(payload).lower()
    assert "password" not in json.dumps(payload).lower()
