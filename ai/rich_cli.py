"""Rich terminal interface for the MCP-connected LangGraph workflow."""

from __future__ import annotations

from typing import Any, Callable
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


class MatchingCLI:
    """Run a compiled matching graph through an interactive terminal loop."""

    def __init__(
        self,
        agent: Any,
        *,
        console: Console | None = None,
        input_func: Callable[[str], str] = input,
    ) -> None:
        self.agent = agent
        self.console = console or Console()
        self.input_func = input_func

    def _prompt(self, label: str) -> str:
        self.console.print(f"[bold cyan]{label}[/bold cyan]")
        return self.input_func("> ").strip()

    def _show_shortlist(self, shortlist: list[dict[str, Any]]) -> None:
        if not shortlist:
            return
        table = Table(title="Candidate shortlist", show_lines=False)
        table.add_column("Rank", justify="right")
        table.add_column("Candidate")
        table.add_column("Score", justify="right")
        table.add_column("Experience", justify="right")
        table.add_column("Matched skills")
        for rank, candidate in enumerate(shortlist, start=1):
            table.add_row(
                str(rank),
                candidate.get("candidate_name", "Unknown"),
                f"{candidate.get('match_score', 0):.1f}",
                f"{candidate.get('years_experience', 0)} yrs",
                ", ".join(candidate.get("matched_skills", [])) or "—",
            )
        self.console.print(table)

    def _show_latest_report(self, state: dict[str, Any]) -> None:
        messages = state.get("messages", [])
        latest = next(
            (message for message in reversed(messages) if isinstance(message, AIMessage)),
            None,
        )
        if latest is not None:
            self.console.print(
                Panel(latest.content, title="Agent report", border_style="green")
            )

    async def run(
        self,
        job_description: str | None = None,
        *,
        thread_id: str | None = None,
    ) -> bool:
        self.console.print(
            Panel(
                "MCP-connected resume matching with LangGraph",
                title="Profile Matching Agent",
                border_style="cyan",
            )
        )
        while not (job_description or "").strip():
            if job_description is not None:
                self.console.print("[yellow]Job description cannot be empty.[/yellow]")
            try:
                job_description = self._prompt("Paste the job description")
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[yellow]Session cancelled.[/yellow]")
                return False

        graph = self.agent.build_graph()
        config = self.agent.thread_config(thread_id or f"cli-{uuid4().hex[:8]}")
        graph_input: dict[str, Any] | Command = {
            "messages": [HumanMessage(content=job_description.strip())]
        }

        while True:
            try:
                with self.console.status("[cyan]Running agent workflow...[/cyan]"):
                    state = await graph.ainvoke(graph_input, config=config)
            except Exception:
                self.console.print(
                    "[bold red]Workflow failed.[/bold red] Check MCP, Ollama, and Chroma configuration."
                )
                return False

            self._show_shortlist(state.get("shortlist", []))
            self._show_latest_report(state)
            if not state.get("__interrupt__"):
                return True

            try:
                feedback = self._prompt(
                    "Next action (refine, compare, interview questions, next round, or done)"
                )
            except (EOFError, KeyboardInterrupt):
                feedback = "done"
            if not feedback:
                self.console.print("[yellow]Please enter an action.[/yellow]")
                continue
            graph_input = Command(resume=feedback)
