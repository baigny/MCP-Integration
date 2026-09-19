"""LangGraph profile-matching agent wired to the filesystem MCP client."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from langchain_ollama import ChatOllama

from ai import job_matcher
from ai.matching_graph import AgentDependencies, MatchingAgent


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


def build_agent(mcp_client: Any) -> MatchingAgent:
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
        )
    )


__all__ = ["AgentDependencies", "MatchingAgent", "build_agent"]
