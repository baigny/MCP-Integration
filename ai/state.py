"""LangGraph agent state shared across all nodes."""
from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class Candidate(TypedDict, total=False):
    candidate_name: str
    resume_path: str
    match_score: float
    years_experience: int
    education: str
    semantic_similarity: float
    keyword_match: float
    matched_skills: list
    relevant_excerpts: list
    reasoning: str
    deep_analysis: str
    recommendation: str


class Requirements(TypedDict, total=False):
    must_have: list
    nice_to_have: list


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    jd_text: str
    requirements: Requirements
    candidate_pool: list[Candidate]
    shortlist: list[Candidate]
    round: int
    last_action: str
    min_years: int
    prior_shortlist: list[Candidate]
    thread_id: str
