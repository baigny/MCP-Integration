"""Six-node LangGraph workflow backed by an MCP filesystem client."""

from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from ai.state import AgentState


SearchCandidates = Callable[..., list[dict[str, Any]] | Awaitable[list[dict[str, Any]]]]
INTENT_LABELS = {
    "END",
    "NEXT_ROUND",
    "REFINE",
    "COMPARE",
    "EXPLAIN",
    "INTERVIEW_QUESTIONS",
}


@dataclass
class AgentDependencies:
    """External capabilities injected into graph nodes."""

    mcp_client: Any
    llm: Any
    search_candidates: SearchCandidates
    round_client: Any | None = None


def _candidate_lines(candidates: list[dict[str, Any]]) -> str:
    return "\n".join(
        (
            f"{index}. {candidate['candidate_name']} - "
            f"{candidate.get('match_score', 0)}/100 "
            f"({candidate.get('years_experience', 0)} yrs, "
            f"skills: {candidate.get('matched_skills', [])})\n"
            f"   {candidate.get('reasoning', '')}"
        )
        for index, candidate in enumerate(candidates, start=1)
    )


def _extract_min_years(text: str) -> int | None:
    match = re.search(r"(\d+)\s*\+?\s*years?", text.lower())
    return int(match.group(1)) if match else None


def _resolve_candidates(text: str, pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lowered = text.lower()
    named = [
        candidate
        for candidate in pool
        if candidate["candidate_name"].lower() in lowered
        or candidate["candidate_name"].split()[0].lower() in lowered
    ]
    if named:
        return named
    match = re.search(r"top\s+(\d+)", lowered)
    if match:
        return pool[: int(match.group(1))]
    return []


def route_after_feedback(state: AgentState) -> str:
    action = state.get("last_action")
    if action == "refine":
        return "extract_requirements"
    if action == "next_round":
        return "generate_report"
    if action == "answered":
        return "human_feedback"
    return "END"


class MatchingAgent:
    """Profile-matching graph with MCP-backed resume access."""

    def __init__(self, dependencies: AgentDependencies) -> None:
        self.dependencies = dependencies

    async def _ask(self, prompt: str) -> str:
        response = await self.dependencies.llm.ainvoke(prompt)
        return response.content.strip()

    async def parse_jd(self, state: AgentState) -> dict[str, Any]:
        for message in state.get("messages", []):
            if isinstance(message, HumanMessage):
                return {"jd_text": message.content, "round": 1}
        return {"jd_text": state.get("jd_text", ""), "round": 1}

    async def extract_requirements_node(self, state: AgentState) -> dict[str, Any]:
        prompt = (
            "Extract job requirements. Reply with only JSON using this shape: "
            '{"must_have": ["..."], "nice_to_have": ["..."]}.\n\n'
            f"Job description:\n{state.get('jd_text', '')}"
        )
        try:
            content = await self._ask(prompt)
            content = re.sub(r"^\x60\x60\x60(?:json)?\s*|\s*\x60\x60\x60$", "", content, flags=re.IGNORECASE)
            parsed = json.loads(content)
            requirements = {
                "must_have": list(parsed.get("must_have", [])),
                "nice_to_have": list(parsed.get("nice_to_have", [])),
            }
        except (json.JSONDecodeError, TypeError, ValueError):
            requirements = {"must_have": [], "nice_to_have": []}
        return {"requirements": requirements}

    async def search_resumes_node(self, state: AgentState) -> dict[str, Any]:
        top_n = 10 if state.get("round", 1) == 1 else max(
            1, len(state.get("candidate_pool", []))
        )
        result = self.dependencies.search_candidates(
            state.get("jd_text", ""),
            top_n=top_n,
            min_years=state.get("min_years"),
        )
        candidates = await result if inspect.isawaitable(result) else result
        return {"candidate_pool": candidates}

    def rank_candidates(self, state: AgentState) -> dict[str, Any]:
        ranked = sorted(
            state.get("candidate_pool", []),
            key=lambda candidate: candidate.get("match_score", 0),
            reverse=True,
        )
        return {"shortlist": ranked}

    async def generate_report(self, state: AgentState) -> dict[str, Any]:
        shortlist = state.get("shortlist", [])
        round_number = state.get("round", 1)
        if not shortlist:
            report = f"Round {round_number} - no matching candidates were found."
        elif round_number == 1:
            report = f"Round 1 - top {len(shortlist)} candidates:\n\n{_candidate_lines(shortlist)}"
        elif round_number == 2:
            comparison = await self._ask(
                "Compare these candidates for the same role. Give strengths, gaps, "
                "and finish with one clear verdict.\n\n"
                f"Job description:\n{state.get('jd_text', '')}\n\n"
                f"Candidates:\n{_candidate_lines(shortlist)}"
            )
            report = f"Round 2 - deep comparison:\n\n{comparison}"
        else:
            top = shortlist[0]
            read_result = await self.dependencies.mcp_client.read_file(top["resume_path"])
            if not read_result.get("success"):
                report = (
                    f"Round 3 - hire recommendation:\n\nRecommend: {top['candidate_name']} "
                    f"(score {top.get('match_score', 0)}/100)\n"
                    "Interview questions could not be generated because the resume "
                    "could not be read through MCP."
                )
            else:
                questions = await self._ask(
                    "Write exactly five concise screening questions grounded in the "
                    "candidate resume and job requirements.\n\n"
                    f"Resume:\n{read_result['data']['content']}\n\n"
                    f"Job description:\n{state.get('jd_text', '')}"
                )
                report = (
                    f"Round 3 - hire recommendation:\n\nRecommend: {top['candidate_name']} "
                    f"(score {top.get('match_score', 0)}/100)\n"
                    f"{top.get('reasoning', '')}\n\nSuggested screening questions:\n{questions}"
                )
        if self.dependencies.round_client is not None:
            top = shortlist[0] if shortlist else {}
            await self.dependencies.round_client.record_round(
                state.get("thread_id", "agent-session"), round_number,
                top.get("candidate_name"), top.get("match_score"),
            )
        return {
            "messages": [AIMessage(content=report)],
            "last_action": f"report_round_{round_number}",
            "prior_shortlist": [],
        }

    async def _classify_intent(self, user_text: str) -> str:
        lowered = user_text.lower()
        if any(word in lowered for word in ("done", "stop", "thanks", "exit")):
            return "END"
        if "next round" in lowered or "hire recommendation" in lowered:
            return "NEXT_ROUND"
        if "interview" in lowered or "screening question" in lowered:
            return "INTERVIEW_QUESTIONS"
        if "compare" in lowered:
            return "COMPARE"
        if "why" in lowered or "explain" in lowered:
            return "EXPLAIN"
        if any(word in lowered for word in ("only", "require", "years", "refine")):
            return "REFINE"
        label = (
            await self._ask(
                "Classify the request into exactly one label: END, NEXT_ROUND, REFINE, "
                "COMPARE, EXPLAIN, INTERVIEW_QUESTIONS.\n"
                f"Request: {user_text}"
            )
        ).upper()
        return next((known for known in INTENT_LABELS if known in label), "END")

    async def human_feedback(self, state: AgentState) -> dict[str, Any]:
        user_text = interrupt({"question": "What would you like to do next?"})
        intent = await self._classify_intent(user_text)
        messages: list[Any] = [HumanMessage(content=user_text)]
        if intent == "REFINE":
            years = _extract_min_years(user_text)
            return {
                "messages": messages,
                "jd_text": f"{state.get('jd_text', '')}\n\nAdditional requirement: {user_text}",
                "round": 1,
                "last_action": "refine",
                "min_years": max(state.get("min_years") or 0, years or 0) or None,
                "prior_shortlist": state.get("shortlist", []),
            }
        if intent == "NEXT_ROUND":
            return {
                "messages": messages,
                "round": min(state.get("round", 1) + 1, 3),
                "last_action": "next_round",
            }
        if intent in {"COMPARE", "EXPLAIN"}:
            selected = _resolve_candidates(user_text, state.get("shortlist", []))
            answer = (
                await self._ask("Compare and explain the ranking:\n\n" + _candidate_lines(selected))
                if len(selected) >= 2
                else "Name at least two candidates or request the top N candidates."
            )
            return {"messages": messages + [AIMessage(content=answer)], "last_action": "answered"}
        if intent == "INTERVIEW_QUESTIONS":
            selected = _resolve_candidates(user_text, state.get("shortlist", []))
            candidate = selected[0] if selected else (
                state.get("shortlist", [None])[0] if state.get("shortlist") else None
            )
            if candidate is None:
                answer = "No shortlisted candidate is available."
            else:
                read_result = await self.dependencies.mcp_client.read_file(candidate["resume_path"])
                answer = (
                    await self._ask(
                        "Write five screening questions for this resume:\n\n"
                        + read_result["data"]["content"]
                    )
                    if read_result.get("success")
                    else "The candidate resume could not be read through MCP."
                )
            return {"messages": messages + [AIMessage(content=answer)], "last_action": "answered"}
        return {"messages": messages, "last_action": "end"}

    def build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("parse_jd", self.parse_jd)
        graph.add_node("extract_requirements", self.extract_requirements_node)
        graph.add_node("search_resumes", self.search_resumes_node)
        graph.add_node("rank_candidates", self.rank_candidates)
        graph.add_node("generate_report", self.generate_report)
        graph.add_node("human_feedback", self.human_feedback)
        graph.add_edge(START, "parse_jd")
        graph.add_edge("parse_jd", "extract_requirements")
        graph.add_edge("extract_requirements", "search_resumes")
        graph.add_edge("search_resumes", "rank_candidates")
        graph.add_edge("rank_candidates", "generate_report")
        graph.add_edge("generate_report", "human_feedback")
        graph.add_conditional_edges(
            "human_feedback",
            route_after_feedback,
            {
                "extract_requirements": "extract_requirements",
                "generate_report": "generate_report",
                "human_feedback": "human_feedback",
                "END": END,
            },
        )
        return graph.compile(checkpointer=MemorySaver())

    @staticmethod
    def thread_config(thread_id: str = "session-1") -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}
