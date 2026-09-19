# MCP Integration

An MCP-based evolution of the earlier filesystem assistant, RAG profile matcher,
and LangGraph profile-matching agent.

## Current status

Project initialization is complete. Reusable ingestion, embedding, vector-store,
matching, and sample-data components have been copied from the prior milestones.
The filesystem MCP server and refactored LangGraph client will be developed with
the red-green-refactor TDD workflow documented in [PLAN.md](PLAN.md).

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
pytest
```

Copy `.env.example` to `.env` for local overrides. Do not commit `.env`.

