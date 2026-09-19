import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama
from langgraph.types import Command

from ai import job_matcher
from ai.matching_graph import AgentDependencies, MatchingAgent
from ai.mcp_client import FilesystemMCPClient, MCPClientConfig
from backend import vector_store


class ScriptedLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)

    async def ainvoke(self, prompt: str):
        return SimpleNamespace(content=self.responses.pop(0))


def _stdio_config(workspace: dict[str, Path]) -> MCPClientConfig:
    environment = {
        **os.environ,
        "MCP_ALLOWED_ROOTS": ",".join(
            (str(workspace["resumes"]), str(workspace["output"]))
        ),
        "MCP_RESUME_ROOT": str(workspace["resumes"]),
        "MCP_OUTPUT_ROOT": str(workspace["output"]),
    }
    return MCPClientConfig(env=environment)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_three_round_agent_workflow_over_real_mcp(
    workspace: dict[str, Path],
) -> None:
    resume = workspace["resumes"] / "asha.txt"
    resume.write_text(
        "Asha Rao\nSenior Python engineer with AWS and six years of experience.",
        encoding="utf-8",
    )
    candidate = {
        "candidate_name": "Asha Rao",
        "resume_path": str(resume),
        "match_score": 94.0,
        "years_experience": 6,
        "matched_skills": ["Python", "AWS"],
        "reasoning": "Matches Python and AWS.",
    }

    async def search(jd_text: str, top_n: int, min_years=None):
        return [candidate]

    llm = ScriptedLLM(
        [
            '{"must_have": ["Python"], "nice_to_have": ["AWS"]}',
            "Asha is the strongest candidate because her experience matches the role.",
            "1. Describe an AWS system you designed.\n2. How do you test Python services?",
        ]
    )

    async with FilesystemMCPClient(_stdio_config(workspace)) as mcp_client:
        agent = MatchingAgent(
            AgentDependencies(
                mcp_client=mcp_client,
                llm=llm,
                search_candidates=search,
            )
        )
        graph = agent.build_graph()
        config = agent.thread_config("e2e-three-rounds")

        round_one = await graph.ainvoke(
            {"messages": [HumanMessage(content="Need a Python engineer")]},
            config=config,
        )
        round_two = await graph.ainvoke(Command(resume="next round"), config=config)
        round_three = await graph.ainvoke(Command(resume="next round"), config=config)
        completed = await graph.ainvoke(Command(resume="done"), config=config)

    assert "Round 1" in round_one["messages"][-1].content
    assert "deep comparison" in round_two["messages"][-1].content
    assert "Recommend: Asha Rao" in round_three["messages"][-1].content
    assert "Describe an AWS system" in round_three["messages"][-1].content
    assert completed["last_action"] == "end"
    assert "__interrupt__" not in completed


@pytest.mark.integration
def test_real_chroma_hybrid_match_with_deterministic_embedding(
    workspace: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    chroma_path = workspace["root"] / "chroma"
    resume = workspace["resumes"] / "candidate.txt"
    resume.write_text(
        "Asha Rao\nSKILLS\nPython, AWS\nEXPERIENCE\n6 years",
        encoding="utf-8",
    )
    monkeypatch.setattr(vector_store, "PERSIST_DIR", str(chroma_path))
    monkeypatch.setattr(vector_store, "_client", None)
    monkeypatch.setattr(job_matcher, "RESUME_DIR", str(workspace["resumes"]))
    monkeypatch.setattr(job_matcher.embeddings, "embed_text", lambda text: [1.0, 0.0])

    vector_store.upsert_chunks(
        [
            {
                "id": "candidate.txt::0::skills",
                "text": "Python AWS",
                "embedding": [1.0, 0.0],
                "metadata": {
                    "source_file": "candidate.txt",
                    "section": "skills",
                    "name": "Asha Rao",
                    "skills": "Python, AWS",
                    "years_experience": 6,
                    "education": "BS Computer Science",
                },
            }
        ]
    )

    results = job_matcher.match("Need Python and AWS", top_n=1, min_years=5)

    assert len(results) == 1
    assert results[0]["candidate_name"] == "Asha Rao"
    assert results[0]["matched_skills"] == ["AWS", "Python"]
    assert results[0]["match_score"] == 100.0
    vector_store._client = None


@pytest.mark.live_ollama
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_OLLAMA") != "1",
    reason="Set RUN_LIVE_OLLAMA=1 to run the live model smoke test",
)
async def test_live_ollama_smoke() -> None:
    model = ChatOllama(
        model=os.getenv("MCP_OLLAMA_MODEL", "llama3.2:3b"),
        base_url=os.getenv("MCP_OLLAMA_BASE_URL", "http://localhost:11434"),
        temperature=0,
    )

    response = await model.ainvoke("Reply with exactly: MCP READY")

    assert "MCP READY" in response.content.upper()
