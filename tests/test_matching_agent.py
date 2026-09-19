import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage

from ai.matching_graph import AgentDependencies, MatchingAgent, route_after_feedback


class FakeMCPClient:
    def __init__(self) -> None:
        self.read_paths = []
        self.read_result = {
            "success": True,
            "data": {"content": "Senior Python engineer with AWS experience."},
            "error": None,
        }

    async def read_file(self, filepath: str):
        self.read_paths.append(filepath)
        return self.read_result


class FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.prompts = []

    async def ainvoke(self, prompt: str):
        self.prompts.append(prompt)
        return SimpleNamespace(content=self.responses.pop(0))


class FakeRoundClient:
    def __init__(self) -> None:
        self.calls = []

    async def record_round(self, *args) -> None:
        self.calls.append(args)


def candidate(name: str, score: float, path: str) -> dict:
    return {
        "candidate_name": name,
        "resume_path": path,
        "match_score": score,
        "years_experience": 5,
        "matched_skills": ["Python"],
        "reasoning": "Matches Python",
    }


@pytest.mark.asyncio
async def test_extract_search_and_rank_nodes() -> None:
    searched = []

    async def search(jd_text: str, top_n: int, min_years=None):
        searched.append((jd_text, top_n, min_years))
        return [
            candidate("Lower", 70, "data/resumes/lower.txt"),
            candidate("Higher", 92, "data/resumes/higher.txt"),
        ]

    dependencies = AgentDependencies(
        mcp_client=FakeMCPClient(),
        llm=FakeLLM(
            ['{"must_have": ["Python"], "nice_to_have": ["AWS"]}']
        ),
        search_candidates=search,
    )
    agent = MatchingAgent(dependencies)
    state = {"jd_text": "Need a Python engineer", "round": 1}

    requirements = await agent.extract_requirements_node(state)
    searched_state = await agent.search_resumes_node({**state, **requirements})
    ranked = agent.rank_candidates(searched_state)

    assert requirements["requirements"]["must_have"] == ["Python"]
    assert searched == [("Need a Python engineer", 10, None)]
    assert [item["candidate_name"] for item in ranked["shortlist"]] == [
        "Higher",
        "Lower",
    ]


@pytest.mark.asyncio
async def test_round_three_reads_resume_through_mcp() -> None:
    mcp = FakeMCPClient()
    llm = FakeLLM(["1. Explain your Python architecture experience."])
    agent = MatchingAgent(
        AgentDependencies(mcp_client=mcp, llm=llm, search_candidates=lambda **_: [])
    )
    top = candidate("Asha", 95, "data/resumes/asha.txt")

    result = await agent.generate_report(
        {"round": 3, "shortlist": [top], "jd_text": "Need Python"}
    )

    assert mcp.read_paths == ["data/resumes/asha.txt"]
    assert "Recommend: Asha" in result["messages"][0].content
    assert "Explain your Python architecture" in result["messages"][0].content


@pytest.mark.asyncio
async def test_round_three_handles_mcp_read_failure() -> None:
    mcp = FakeMCPClient()
    mcp.read_result = {
        "success": False,
        "data": None,
        "error": {"code": "not_found", "message": "File does not exist"},
    }
    agent = MatchingAgent(
        AgentDependencies(
            mcp_client=mcp,
            llm=FakeLLM([]),
            search_candidates=lambda **_: [],
        )
    )
    top = candidate("Asha", 95, "data/resumes/missing.txt")

    result = await agent.generate_report(
        {"round": 3, "shortlist": [top], "jd_text": "Need Python"}
    )

    assert "could not be read through MCP" in result["messages"][0].content


@pytest.mark.asyncio
async def test_report_is_recorded_through_second_mcp_server() -> None:
    rounds = FakeRoundClient()
    agent = MatchingAgent(AgentDependencies(
        mcp_client=FakeMCPClient(), llm=FakeLLM([]),
        search_candidates=lambda **_: [], round_client=rounds,
    ))
    top = candidate("Asha", 95, "data/resumes/asha.txt")
    await agent.generate_report({"thread_id": "demo", "round": 1,
                                 "shortlist": [top], "jd_text": "Python"})
    assert rounds.calls == [("demo", 1, "Asha", 95)]


def test_builds_six_node_langgraph() -> None:
    dependencies = AgentDependencies(
        mcp_client=FakeMCPClient(),
        llm=FakeLLM([]),
        search_candidates=lambda **_: [],
    )

    compiled = MatchingAgent(dependencies).build_graph()

    assert set(compiled.get_graph().nodes) >= {
        "parse_jd",
        "extract_requirements",
        "search_resumes",
        "rank_candidates",
        "generate_report",
        "human_feedback",
    }


@pytest.mark.asyncio
async def test_compiled_graph_runs_to_human_feedback_interrupt() -> None:
    async def search(jd_text: str, top_n: int, min_years=None):
        return [candidate("Asha", 91, "data/resumes/asha.txt")]

    agent = MatchingAgent(
        AgentDependencies(
            mcp_client=FakeMCPClient(),
            llm=FakeLLM(
                ['{"must_have": ["Python"], "nice_to_have": ["AWS"]}']
            ),
            search_candidates=search,
        )
    )
    graph = agent.build_graph()

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Need a Python engineer")]},
        config=agent.thread_config("test-initial-flow"),
    )

    assert result["shortlist"][0]["candidate_name"] == "Asha"
    assert "Round 1" in result["messages"][-1].content
    assert result["__interrupt__"]


def test_feedback_routes_preserve_existing_workflow() -> None:
    assert route_after_feedback({"last_action": "refine"}) == "extract_requirements"
    assert route_after_feedback({"last_action": "next_round"}) == "generate_report"
    assert route_after_feedback({"last_action": "answered"}) == "human_feedback"
    assert route_after_feedback({"last_action": "end"}) == "END"


def test_agent_layer_has_no_direct_filesystem_tool_imports() -> None:
    import ai.matching_graph as matching_graph

    source = inspect.getsource(matching_graph)

    assert "backend.fs_tools" not in source
    assert "from backend import fs_tools" not in source


def test_root_matching_agent_deliverable_exists() -> None:
    assert Path("matching_agent.py").is_file()
