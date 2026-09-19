"""Typed MCP client adapter used by the LangGraph matching agent."""

from __future__ import annotations

import json
import os
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client


REQUIRED_TOOLS = frozenset(
    {
        "read_file",
        "list_files",
        "write_file",
        "search_in_file",
        "batch_process",
        "watch_directory",
    }
)


class MCPClientError(RuntimeError):
    """Raised when an MCP connection cannot satisfy the agent contract."""


@dataclass(frozen=True)
class MCPClientConfig:
    transport: Literal["stdio", "http"] = "stdio"
    server_url: str | None = None
    command: str = sys.executable
    args: tuple[str, ...] = field(
        default_factory=lambda: (
            str(Path(__file__).resolve().parents[1] / "filesystem_mcp_server.py"),
            "--transport",
            "stdio",
        )
    )
    cwd: str | Path = field(default_factory=lambda: Path(__file__).resolve().parents[1])
    env: dict[str, str] | None = None
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.transport not in {"stdio", "http"}:
            raise ValueError("transport must be 'stdio' or 'http'")
        if self.transport == "http" and not self.server_url:
            raise ValueError("server_url is required for HTTP transport")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


def _failure(code: str, message: str) -> dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message},
    }


class FilesystemMCPClient:
    """Manage one MCP session and expose filesystem-specific async wrappers."""

    def __init__(
        self,
        config: MCPClientConfig,
        *,
        session: Any | None = None,
    ) -> None:
        self.config = config
        self._session = session
        self._external_session = session is not None
        self._stack: AsyncExitStack | None = None
        self.connected = False
        self.server_name: str | None = None
        self.tools: tuple[str, ...] = ()

    async def __aenter__(self) -> "FilesystemMCPClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.close()

    async def connect(self) -> dict[str, Any]:
        if self.connected:
            return {"server_name": self.server_name, "tools": list(self.tools)}

        if self._session is None:
            self._stack = AsyncExitStack()
            try:
                if self.config.transport == "stdio":
                    parameters = StdioServerParameters(
                        command=self.config.command,
                        args=list(self.config.args),
                        cwd=self.config.cwd,
                        env=self.config.env or dict(os.environ),
                    )
                    streams = await self._stack.enter_async_context(stdio_client(parameters))
                else:
                    assert self.config.server_url is not None
                    streams = await self._stack.enter_async_context(
                        streamable_http_client(self.config.server_url)
                    )
                self._session = await self._stack.enter_async_context(
                    ClientSession(streams[0], streams[1])
                )
            except Exception as exc:
                await self.close()
                raise MCPClientError("Unable to connect to filesystem MCP server") from exc

        try:
            initialized = await self._session.initialize()
            discovered = await self._session.list_tools()
        except Exception as exc:
            await self.close()
            raise MCPClientError("MCP initialization failed") from exc

        tool_names = {tool.name for tool in discovered.tools}
        missing = REQUIRED_TOOLS - tool_names
        if missing:
            await self.close()
            raise MCPClientError(
                f"MCP server is missing required tools: {', '.join(sorted(missing))}"
            )

        self.server_name = initialized.server_info.name
        self.tools = tuple(sorted(tool_names))
        self.connected = True
        return {"server_name": self.server_name, "tools": list(self.tools)}

    async def close(self) -> None:
        self.connected = False
        if self._stack is not None:
            stack, self._stack = self._stack, None
            await stack.aclose()
        if not self._external_session:
            self._session = None

    def _require_connection(self) -> Any:
        if not self.connected or self._session is None:
            raise MCPClientError("MCP client is not connected")
        return self._session

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        session = self._require_connection()
        try:
            result = await session.call_tool(
                name,
                arguments,
                read_timeout_seconds=self.config.timeout_seconds,
            )
        except Exception:
            return _failure("mcp_connection_error", "MCP tool call failed")

        if result.is_error:
            message = "\n".join(
                block.text for block in result.content if hasattr(block, "text")
            ) or f"MCP tool failed: {name}"
            return _failure("mcp_tool_error", message)
        if not isinstance(result.structured_content, dict):
            return _failure("mcp_response_error", "MCP tool returned no structured content")
        return result.structured_content

    async def read_file(self, filepath: str) -> dict[str, Any]:
        return await self._call_tool("read_file", {"filepath": filepath})

    async def list_files(
        self, directory: str, extension: str | None = None
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {"directory": directory}
        if extension is not None:
            arguments["extension"] = extension
        return await self._call_tool("list_files", arguments)

    async def write_file(
        self,
        filepath: str,
        content: str,
        *,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        return await self._call_tool(
            "write_file",
            {"filepath": filepath, "content": content, "overwrite": overwrite},
        )

    async def search_in_file(self, filepath: str, keyword: str) -> dict[str, Any]:
        return await self._call_tool(
            "search_in_file", {"filepath": filepath, "keyword": keyword}
        )

    async def batch_process(
        self,
        paths: list[str],
        *,
        operation: str,
        keyword: str | None = None,
        max_concurrency: int | None = None,
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {"paths": paths, "operation": operation}
        if keyword is not None:
            arguments["keyword"] = keyword
        if max_concurrency is not None:
            arguments["max_concurrency"] = max_concurrency
        return await self._call_tool("batch_process", arguments)

    async def watch_directory(
        self,
        action: str,
        *,
        directory: str | None = None,
        watcher_id: str | None = None,
        auto_ingest: bool = True,
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {"action": action}
        if directory is not None:
            arguments["directory"] = directory
            arguments["auto_ingest"] = auto_ingest
        if watcher_id is not None:
            arguments["watcher_id"] = watcher_id
        return await self._call_tool("watch_directory", arguments)

    async def read_resource(self, uri: str) -> dict[str, Any]:
        session = self._require_connection()
        try:
            result = await session.read_resource(uri)
            text = result.contents[0].text
            payload = json.loads(text)
        except (AttributeError, IndexError, TypeError, json.JSONDecodeError):
            return _failure("mcp_response_error", "MCP resource returned invalid JSON")
        except Exception:
            return _failure("mcp_connection_error", "MCP resource read failed")
        return payload
