from io import StringIO

import pytest
from langchain_core.messages import AIMessage
from langgraph.types import Command
from rich.console import Console

from ai.rich_cli import MatchingCLI


class FakeGraph:
    def __init__(self) -> None:
        self.calls = []

    async def ainvoke(self, graph_input, config):
        self.calls.append((graph_input, config))
        if len(self.calls) == 1:
            return {
                "shortlist": [
                    {
                        "candidate_name": "Asha Rao",
                        "match_score": 92,
                        "years_experience": 6,
                        "matched_skills": ["Python", "AWS"],
                    }
                ],
                "messages": [AIMessage(content="Round 1 report")],
                "__interrupt__": [object()],
            }
        return {
            "shortlist": [],
            "messages": [AIMessage(content="Session complete")],
        }


class FakeAgent:
    def __init__(self, graph: FakeGraph) -> None:
        self.graph = graph

    def build_graph(self):
        return self.graph

    @staticmethod
    def thread_config(thread_id: str):
        return {"configurable": {"thread_id": thread_id}}


@pytest.mark.asyncio
async def test_cli_displays_shortlist_and_resumes_feedback() -> None:
    stream = StringIO()
    console = Console(file=stream, width=120, color_system=None)
    answers = iter(["done"])
    graph = FakeGraph()
    cli = MatchingCLI(
        FakeAgent(graph),
        console=console,
        input_func=lambda prompt: next(answers),
    )

    await cli.run("Need a Python engineer", thread_id="cli-test")

    output = stream.getvalue()
    assert "Asha Rao" in output
    assert "Round 1 report" in output
    assert "Session complete" in output
    assert isinstance(graph.calls[1][0], Command)
    assert graph.calls[1][0].resume == "done"
    assert graph.calls[0][1]["configurable"]["thread_id"] == "cli-test"


@pytest.mark.asyncio
async def test_cli_prompts_until_job_description_is_not_empty() -> None:
    stream = StringIO()
    answers = iter(["", "Need a backend engineer", "done"])
    graph = FakeGraph()
    cli = MatchingCLI(
        FakeAgent(graph),
        console=Console(file=stream, width=100, color_system=None),
        input_func=lambda prompt: next(answers),
    )

    await cli.run()

    assert graph.calls[0][0]["messages"][0].content == "Need a backend engineer"
    assert "cannot be empty" in stream.getvalue()


@pytest.mark.asyncio
async def test_cli_reports_graph_failure_without_traceback() -> None:
    class FailingGraph:
        async def ainvoke(self, graph_input, config):
            raise RuntimeError("database unavailable")

    stream = StringIO()
    cli = MatchingCLI(
        FakeAgent(FailingGraph()),
        console=Console(file=stream, width=100, color_system=None),
        input_func=lambda prompt: "unused",
    )

    result = await cli.run("Need an engineer")

    assert result is False
    assert "Workflow failed" in stream.getvalue()
    assert "database unavailable" not in stream.getvalue()
