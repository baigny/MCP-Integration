# MCP Integration

A production-oriented resume matching system that replaces direct filesystem access with a Model Context Protocol (MCP) server. It combines safe file operations, batch processing, directory watching, Chroma-based retrieval, and a three-round LangGraph workflow behind a Rich terminal interface.

## Assignment coverage

- JSON-RPC 2.0 MCP server over stdio or Streamable HTTP
- Six discoverable tools: `read_file`, `list_files`, `write_file`, `search_in_file`, `batch_process`, and `watch_directory`
- MCP resources for the server catalog, runtime configuration, and individual resumes
- Structured domain errors, root-path restrictions, and overwrite protection
- Bounded-concurrency batch processing with independent per-file results
- Debounced directory watching with optional automatic ingestion
- MCP client adapter used by the LangGraph matching agent
- Rich CLI for the complete three-round candidate workflow
- Unit, transport-integration, and end-to-end tests

The optional multi-MCP bonus is not implemented. The core assignment does not require a second server.

## Architecture

The agent never reads resume files directly. It discovers the filesystem server's capabilities through MCP, uses Chroma to rank candidates, and calls the MCP `read_file` tool when detailed resume content is needed.

See the [state machine and interaction diagrams](docs/state_machine.md) and [test scenarios](docs/test_scenarios.md).

## Setup

Requirements:

- Python 3.12 or a compatible Python 3.11+ installation
- Ollama for an interactive agent demo
- The `llama3.2:3b` Ollama model, unless `MCP_OLLAMA_MODEL` is changed

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
ollama pull llama3.2:3b
~~~

`requirements.txt` contains runtime packages. `requirements-dev.txt` includes it and adds test and coverage tools.

## Configuration

Local settings are loaded from `.env`. The main variables are:

| Variable | Default | Purpose |
|---|---|---|
| `MCP_ALLOWED_ROOTS` | `data/resumes,output` | Comma-separated filesystem boundary |
| `MCP_RESUME_ROOT` | `data/resumes` | Resume resource and watcher root |
| `MCP_OUTPUT_ROOT` | `output` | Writable report directory |
| `MCP_CHROMA_DIR` | `chroma_db` | Persistent vector database |
| `MCP_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `MCP_OLLAMA_MODEL` | `llama3.2:3b` | Chat model |
| `MCP_BATCH_CONCURRENCY` | `4` | Maximum concurrent batch items |

Do not commit `.env`, `chroma_db`, or `.venv`.

## Run the application

Build or refresh the local resume collection:

~~~powershell
python scripts/ingest_resumes.py
~~~

The simplest run uses stdio. The client starts and owns the MCP server process:

~~~powershell
python matching_agent.py --jd "Need a senior Python engineer with AWS experience"
~~~

For a separately deployed Streamable HTTP server, use two terminals:

~~~powershell
python filesystem_mcp_server.py --transport http --host 127.0.0.1 --port 8000
~~~

~~~powershell
python matching_agent.py --transport http --server-url http://127.0.0.1:8000/mcp --jd "Need a senior Python engineer"
~~~

The CLI displays the MCP connection, ranked shortlist, generated reports, and prompts for actions such as comparison, interview questions, refinement, or the next screening round.

## Test

~~~powershell
python -m pytest
python -m pytest --cov=ai --cov=backend --cov=filesystem_mcp_server
~~~

The normal suite is deterministic and does not require Ollama. To include the optional live-model scenario:

~~~powershell
$env:RUN_LIVE_OLLAMA="1"
python -m pytest -m live_ollama
~~~

On restricted Windows sandboxes, tests that create MCP subprocess pipes may require a normal local terminal. This is an operating-system permission issue, not an application dependency.

## Project layout

~~~text
filesystem_mcp_server.py   MCP tools, resources, and transports
matching_agent.py          Production CLI entry point
ai/                        MCP client and LangGraph workflow
backend/                   File safety, watching, ingestion, and retrieval
scripts/ingest_resumes.py  Chroma ingestion helper
tests/                     Unit, integration, and E2E coverage
docs/                      Diagrams, scenarios, and demo script
data/                      Sample resumes and job descriptions
~~~

The repository stays lightweight: generated databases, local configuration, caches, and the virtual environment are excluded from Git.
