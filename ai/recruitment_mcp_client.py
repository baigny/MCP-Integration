"""Client adapter for the optional recruitment history MCP server."""

from __future__ import annotations

import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ai.mcp_client import MCPClientError, _failure


class RecruitmentMCPClient:
    REQUIRED_TOOLS = {"record_round", "list_rounds"}

    def __init__(self, *, session: Any | None = None) -> None:
        self._session = session
        self._external_session = session is not None
        self._stack: AsyncExitStack | None = None
        self.connected = False
        self.tools: tuple[str, ...] = ()
        self.server_name: str | None = None

    async def __aenter__(self) -> "RecruitmentMCPClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.close()

    async def connect(self) -> dict[str, Any]:
        if self._session is None:
            self._stack = AsyncExitStack()
            root = Path(__file__).resolve().parents[1]
            parameters = StdioServerParameters(
                command=sys.executable,
                args=[str(root / "recruitment_mcp_server.py"), "--transport", "stdio"],
                cwd=root,
                env=dict(os.environ),
            )
            try:
                streams = await self._stack.enter_async_context(stdio_client(parameters))
                self._session = await self._stack.enter_async_context(
                    ClientSession(streams[0], streams[1]))
            except Exception as exc:
                await self.close()
                raise MCPClientError("Unable to connect to recruitment MCP server") from exc
        initialized = await self._session.initialize()
        discovered = await self._session.list_tools()
        names = {tool.name for tool in discovered.tools}
        missing = self.REQUIRED_TOOLS - names
        if missing:
            await self.close()
            raise MCPClientError("Recruitment MCP server is missing required tools")
        self.server_name = initialized.server_info.name
        self.tools = tuple(sorted(names))
        self.connected = True
        return {"server_name": self.server_name, "tools": list(self.tools)}

    async def close(self) -> None:
        self.connected = False
        if self._stack is not None:
            stack, self._stack = self._stack, None
            await stack.aclose()
        if not self._external_session:
            self._session = None

    async def record_round(self, thread_id: str, round_number: int,
                           candidate_name: str | None, score: float | None) -> dict[str, Any]:
        if not self.connected or self._session is None:
            return _failure("mcp_connection_error", "Recruitment MCP client is not connected")
        try:
            result = await self._session.call_tool("record_round", {
                "thread_id": thread_id, "round_number": round_number,
                "candidate_name": candidate_name, "score": score,
            }, read_timeout_seconds=30)
        except Exception:
            return _failure("mcp_connection_error", "Recruitment MCP tool call failed")
        return result.structured_content if not result.is_error else _failure(
            "mcp_tool_error", "Recruitment MCP tool failed")
