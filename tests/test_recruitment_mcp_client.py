from types import SimpleNamespace

import pytest

from ai.recruitment_mcp_client import RecruitmentMCPClient


class FakeSession:
    def __init__(self):
        self.calls = []

    async def initialize(self):
        return SimpleNamespace(server_info=SimpleNamespace(name="recruitment-mcp-server"))

    async def list_tools(self):
        return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in
                                     ("record_round", "list_rounds")])

    async def call_tool(self, name, arguments, read_timeout_seconds=None):
        self.calls.append((name, arguments))
        return SimpleNamespace(is_error=False, structured_content={
            "success": True, "data": {}, "error": None}, content=[])


@pytest.mark.asyncio
async def test_records_round_through_second_mcp_server() -> None:
    session = FakeSession()
    client = RecruitmentMCPClient(session=session)
    await client.connect()
    await client.record_round("thread-1", 2, "Asha", 94)
    assert session.calls == [("record_round", {
        "thread_id": "thread-1", "round_number": 2,
        "candidate_name": "Asha", "score": 94,
    })]
