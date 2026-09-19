"""LangGraph profile-matching agent wired to the filesystem MCP client."""

from __future__ import annotations

import asyncio
import argparse
import os
from typing import Any

from langchain_ollama import ChatOllama

from ai import job_matcher
from ai.mcp_client import FilesystemMCPClient, MCPClientConfig, MCPClientError
from ai.recruitment_mcp_client import RecruitmentMCPClient
from ai.matching_graph import AgentDependencies, MatchingAgent
from ai.rich_cli import MatchingCLI
from rich.console import Console
from rich.panel import Panel


async def _search_candidates(
    jd_text: str,
    *,
    top_n: int = 10,
    min_years: int | None = None,
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(
        job_matcher.match,
        jd_text,
        top_n=top_n,
        min_years=min_years,
    )


def build_agent(mcp_client: Any, round_client: Any | None = None) -> MatchingAgent:
    """Build the production graph around an already-connected MCP client."""
    llm = ChatOllama(
        model=os.getenv("MCP_OLLAMA_MODEL", "llama3.2:3b"),
        base_url=os.getenv("MCP_OLLAMA_BASE_URL", "http://localhost:11434"),
        temperature=0,
    )
    return MatchingAgent(
        AgentDependencies(
            mcp_client=mcp_client,
            llm=llm,
            search_candidates=_search_candidates,
            round_client=round_client,
        )
    )


__all__ = ["AgentDependencies", "MatchingAgent", "build_agent"]


async def run_cli(
    *,
    transport: str = "stdio",
    server_url: str | None = None,
    job_description: str | None = None,
    thread_id: str = "session-1",
) -> int:
    console = Console()
    try:
        config = MCPClientConfig(
            transport=transport,
            server_url=server_url,
        )
        async with FilesystemMCPClient(config) as client:
            async with RecruitmentMCPClient() as round_client:
                console.print(
                    Panel(
                        f"Connected to [bold]{client.server_name}[/bold]\n"
                        f"Connected to [bold]{round_client.server_name}[/bold]\n"
                        f"Discovered {len(client.tools) + len(round_client.tools)} MCP tools",
                        title="MCP connection",
                        border_style="green",
                    )
                )
                completed = await MatchingCLI(
                    build_agent(client, round_client), console=console,
                ).run(job_description, thread_id=thread_id)
                return 0 if completed else 1
    except (MCPClientError, ValueError):
        console.print(
            "[bold red]Could not connect to an MCP server.[/bold red]"
        )
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument(
        "--server-url",
        default=os.getenv("MCP_SERVER_URL"),
        help="Streamable HTTP endpoint, for example http://127.0.0.1:8000/mcp",
    )
    parser.add_argument("--jd", help="Job description text; prompts when omitted")
    parser.add_argument("--thread-id", default="session-1")
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(
            run_cli(
                transport=args.transport,
                server_url=args.server_url,
                job_description=args.jd,
                thread_id=args.thread_id,
            )
        )
    )


if __name__ == "__main__":
    main()
