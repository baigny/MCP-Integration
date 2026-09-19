import json
from pathlib import Path

import pytest

from recruitment_mcp_server import create_server


@pytest.fixture
def server(workspace: dict[str, Path]):
    return create_server(workspace["output"] / "recruitment.db")


@pytest.mark.asyncio
async def test_discovers_recruitment_tools(server) -> None:
    tools = await server.list_tools()
    assert {tool.name for tool in tools} == {"record_round", "list_rounds"}


@pytest.mark.asyncio
async def test_records_and_lists_rounds(server) -> None:
    recorded = await server.call_tool("record_round", {
        "thread_id": "demo-1", "round_number": 1,
        "candidate_name": "Asha", "score": 94.0,
    })
    listed = await server.call_tool("list_rounds", {"thread_id": "demo-1"})

    assert recorded.structured_content["success"] is True
    assert listed.structured_content["data"]["rounds"][0]["candidate_name"] == "Asha"


@pytest.mark.asyncio
async def test_exposes_round_history_resource(server) -> None:
    resources = await server.list_resources()
    assert {str(resource.uri) for resource in resources} == {"recruitment://rounds"}
    result = await server.read_resource("recruitment://rounds")
    payload = json.loads(list(result)[0].content)
    assert payload["success"] is True
