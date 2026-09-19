import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from ai.mcp_client import FilesystemMCPClient, MCPClientConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_SCRIPT = PROJECT_ROOT / "filesystem_mcp_server.py"


def _server_env(workspace: dict[str, Path]) -> dict[str, str]:
    return {
        **os.environ,
        "MCP_ALLOWED_ROOTS": ",".join(
            (str(workspace["resumes"]), str(workspace["output"]))
        ),
        "MCP_RESUME_ROOT": str(workspace["resumes"]),
        "MCP_OUTPUT_ROOT": str(workspace["output"]),
        "PYTHONUNBUFFERED": "1",
    }


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_port(process: subprocess.Popen, port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read() if process.stderr else ""
            raise RuntimeError(f"HTTP MCP server exited early: {stderr}")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.1)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.05)
    raise TimeoutError("HTTP MCP server did not become ready")


@pytest.fixture
def http_server(workspace: dict[str, Path]):
    port = _free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            str(SERVER_SCRIPT),
            "--transport",
            "http",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=PROJECT_ROOT,
        env=_server_env(workspace),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_for_port(process, port)
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stdio_transport_initializes_discovers_and_calls(
    workspace: dict[str, Path],
) -> None:
    resume = workspace["resumes"] / "candidate.txt"
    resume.write_text("Python engineer", encoding="utf-8")
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_SCRIPT), "--transport", "stdio"],
        cwd=PROJECT_ROOT,
        env=_server_env(workspace),
    )

    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            resources = await session.list_resources()
            result = await session.call_tool("read_file", {"filepath": str(resume)})
            catalog = await session.read_resource("resumes://catalog")

    assert initialized.server_info.name == "filesystem-mcp-server"
    assert "batch_process" in {tool.name for tool in tools.tools}
    assert "watch_directory" in {tool.name for tool in tools.tools}
    assert "resumes://catalog" in {str(resource.uri) for resource in resources.resources}
    assert result.is_error is False
    assert result.structured_content["data"]["content"] == "Python engineer"
    payload = json.loads(catalog.contents[0].text)
    assert payload["data"]["files"][0]["name"] == "candidate.txt"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_streamable_http_transport_initializes_and_calls(
    http_server: str, workspace: dict[str, Path]
) -> None:
    resume = workspace["resumes"] / "candidate.txt"
    resume.write_text("Platform engineer", encoding="utf-8")

    async with streamable_http_client(http_server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("read_file", {"filepath": str(resume)})

    assert initialized.server_info.name == "filesystem-mcp-server"
    assert "read_file" in {tool.name for tool in tools.tools}
    assert result.is_error is False
    assert result.structured_content["data"]["content"] == "Platform engineer"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_transport_returns_protocol_error_for_unknown_tool(
    http_server: str,
) -> None:
    async with streamable_http_client(http_server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool("tool_that_does_not_exist", {})

    assert result.is_error is True
    assert "unknown tool" in result.content[0].text.lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_transport_returns_error_for_invalid_tool_arguments(
    http_server: str,
) -> None:
    async with streamable_http_client(http_server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool("read_file", {})

    assert result.is_error is True
    assert "filepath" in result.content[0].text.lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_adapter_connects_over_streamable_http(
    http_server: str, workspace: dict[str, Path]
) -> None:
    resume = workspace["resumes"] / "candidate.txt"
    resume.write_text("MCP engineer", encoding="utf-8")
    config = MCPClientConfig(transport="http", server_url=http_server)

    async with FilesystemMCPClient(config) as client:
        result = await client.read_file(str(resume))

    assert result["success"] is True
    assert result["data"]["content"] == "MCP engineer"
