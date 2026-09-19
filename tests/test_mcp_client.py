import json
from types import SimpleNamespace

import pytest

from ai.mcp_client import FilesystemMCPClient, MCPClientConfig, MCPClientError


REQUIRED_TOOLS = {
    "read_file",
    "list_files",
    "write_file",
    "search_in_file",
    "batch_process",
    "watch_directory",
}


class FakeSession:
    def __init__(self, tools=None) -> None:
        self.tools = tools or REQUIRED_TOOLS
        self.calls = []
        self.tool_result = SimpleNamespace(
            is_error=False,
            structured_content={"success": True, "data": {"value": "ok"}, "error": None},
            content=[],
        )
        self.resource_text = json.dumps({"success": True, "data": {"files": []}})

    async def initialize(self):
        return SimpleNamespace(server_info=SimpleNamespace(name="filesystem-mcp-server"))

    async def list_tools(self):
        return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in self.tools])

    async def call_tool(self, name, arguments, read_timeout_seconds=None):
        self.calls.append((name, arguments, read_timeout_seconds))
        return self.tool_result

    async def read_resource(self, uri):
        return SimpleNamespace(contents=[SimpleNamespace(text=self.resource_text)])


@pytest.mark.asyncio
async def test_connect_discovers_required_tools() -> None:
    client = FilesystemMCPClient(MCPClientConfig(), session=FakeSession())

    initialized = await client.connect()

    assert initialized["server_name"] == "filesystem-mcp-server"
    assert set(initialized["tools"]) == REQUIRED_TOOLS
    assert client.connected is True


@pytest.mark.asyncio
async def test_connect_rejects_missing_required_tool() -> None:
    client = FilesystemMCPClient(
        MCPClientConfig(), session=FakeSession(tools={"read_file"})
    )

    with pytest.raises(MCPClientError, match="missing required tools"):
        await client.connect()


@pytest.mark.asyncio
async def test_read_file_wrapper_calls_mcp_tool() -> None:
    session = FakeSession()
    client = FilesystemMCPClient(MCPClientConfig(timeout_seconds=7), session=session)
    await client.connect()

    result = await client.read_file("data/resumes/candidate.txt")

    assert result["success"] is True
    assert session.calls == [
        ("read_file", {"filepath": "data/resumes/candidate.txt"}, 7)
    ]


@pytest.mark.asyncio
async def test_batch_and_watch_wrappers_build_expected_arguments() -> None:
    session = FakeSession()
    client = FilesystemMCPClient(MCPClientConfig(), session=session)
    await client.connect()

    await client.batch_process(
        ["one.txt", "two.txt"],
        operation="search",
        keyword="python",
        max_concurrency=2,
    )
    await client.watch_directory(
        "start", directory="data/resumes", auto_ingest=False
    )

    assert session.calls[0][0:2] == (
        "batch_process",
        {
            "paths": ["one.txt", "two.txt"],
            "operation": "search",
            "keyword": "python",
            "max_concurrency": 2,
        },
    )
    assert session.calls[1][0:2] == (
        "watch_directory",
        {
            "action": "start",
            "directory": "data/resumes",
            "auto_ingest": False,
        },
    )


@pytest.mark.asyncio
async def test_normalizes_mcp_tool_error() -> None:
    session = FakeSession()
    session.tool_result = SimpleNamespace(
        is_error=True,
        structured_content=None,
        content=[SimpleNamespace(text="Unknown tool")],
    )
    client = FilesystemMCPClient(MCPClientConfig(), session=session)
    await client.connect()

    result = await client.read_file("candidate.txt")

    assert result["success"] is False
    assert result["error"]["code"] == "mcp_tool_error"
    assert result["error"]["message"] == "Unknown tool"


@pytest.mark.asyncio
async def test_normalizes_transport_exception() -> None:
    session = FakeSession()

    async def fail(*args, **kwargs):
        raise ConnectionError("connection lost")

    session.call_tool = fail
    client = FilesystemMCPClient(MCPClientConfig(), session=session)
    await client.connect()

    result = await client.read_file("candidate.txt")

    assert result["success"] is False
    assert result["error"]["code"] == "mcp_connection_error"


@pytest.mark.asyncio
async def test_reads_and_decodes_resource() -> None:
    client = FilesystemMCPClient(MCPClientConfig(), session=FakeSession())
    await client.connect()

    result = await client.read_resource("resumes://catalog")

    assert result["success"] is True
    assert result["data"]["files"] == []


def test_config_requires_http_url() -> None:
    with pytest.raises(ValueError, match="server_url"):
        MCPClientConfig(transport="http")

