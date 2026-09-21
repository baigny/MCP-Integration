# MCP Integration

Fourth project in a series: `LLM-Powered-File-System-Assistant` (Milestone 1, direct
file tools) -> `RAG-Based-Profile-Matching` (Milestone 2, hybrid retrieval) ->
`Agentic-Profile-Matching` (Milestone 3, LangGraph workflow) -> this project
(Milestone 4, standardized MCP servers and clients).

## What's different from Milestones 1-3

- Milestone 1: an Ollama agent calls four Python filesystem functions directly.
- Milestone 2: resumes are embedded in ChromaDB and matched through a fixed hybrid pipeline.
- Milestone 3: LangGraph adds state, human feedback, intent routing, and three screening rounds.
- Milestone 4 (here): filesystem access is moved behind a JSON-RPC 2.0 MCP server. The
  LangGraph agent uses MCP clients instead of direct file tools, supports stdio and
  Streamable HTTP, processes batches, watches for new resumes, and records screening
  rounds through a second SQLite-backed MCP server.

## Stack

- **MCP Python SDK** — standardized tools, resources, discovery, stdio, and Streamable HTTP.
- **LangGraph** — six-node, checkpointed, human-in-the-loop matching workflow.
- **Ollama `llama3.2:3b`** — local requirement extraction, comparisons, questions, and routing.
- **ChromaDB** — persistent resume vector store.
- **sentence-transformers `all-MiniLM-L6-v2`** — local embeddings without an API key.
- **SQLite** — recruitment-round audit history exposed through the second MCP server.
- **Rich** — interactive terminal tables, panels, progress, and feedback prompts.

## Project structure

~~~text
MCP Integration/
├── filesystem_mcp_server.py    # safe file tools, resources, and transports
├── recruitment_mcp_server.py   # SQLite round-history MCP server
├── matching_agent.py           # multi-MCP LangGraph CLI
├── ai/                         # MCP clients, graph, matcher, and Rich UI
├── backend/                    # filesystem safety, RAG, batching, and watching
├── data/                       # 32 resumes and 6 job descriptions
├── docs/                       # workflow diagrams and test scenarios
├── scripts/ingest_resumes.py   # ChromaDB ingestion command
├── tests/                      # unit, transport, and end-to-end tests
├── requirements.txt            # runtime dependencies
└── requirements-dev.txt        # runtime plus test dependencies
~~~

## Setup

### 1. Install Ollama and pull the model

~~~cmd
ollama pull llama3.2:3b
ollama list
~~~

### 2. Create and activate a virtual environment

~~~cmd
python -m venv .venv
call .venv\Scripts\activate.bat
~~~

### 3. Install dependencies and configuration

~~~cmd
python -m pip install -r requirements-dev.txt
if not exist .env copy .env.example .env
~~~

`requirements.txt` contains application packages. `requirements-dev.txt` includes it and
adds pytest and coverage tools.

### 4. Ingest the resume collection

~~~cmd
python scripts\ingest_resumes.py
~~~

This step extracts, chunks, embeds, and stores the included resumes in `chroma_db/`.
It can be skipped when that database is already populated. Job descriptions are passed
directly to the agent and do not need ingestion.

## Run

The normal stdio mode starts both MCP server subprocesses automatically:

~~~cmd
python matching_agent.py --thread-id demo-001 --jd "Need a senior Python engineer with AWS and at least five years of experience"
~~~

At the feedback prompt, try:

- `compare the top 2 candidates`
- `generate interview questions for the top candidate`
- `only show candidates with at least 7 years of experience`
- `next round` — advances to Round 2, then Round 3.
- `done` — ends the checkpointed session.

To deploy the filesystem server separately over Streamable HTTP:

~~~cmd
python filesystem_mcp_server.py --transport http --host 127.0.0.1 --port 8000
python matching_agent.py --transport http --server-url http://127.0.0.1:8000/mcp --jd "Need a senior Python engineer"
~~~

## MCP capabilities

### Filesystem server — 6 tools

| Tool | Description |
|---|---|
| `read_file` | Safely extracts TXT, PDF, DOCX, or PPTX content. |
| `list_files` | Lists supported files and metadata inside an allowed root. |
| `write_file` | Writes inside configured output roots with overwrite protection. |
| `search_in_file` | Performs case-insensitive search in a file or directory. |
| `batch_process` | Reads, searches, or ingests files with bounded concurrency. |
| `watch_directory` | Starts, inspects, or stops debounced resume monitoring. |

Resources include `resumes://catalog`, `config://server`, and the
`resume://{relative_path}` template.

### Recruitment server — 2 tools

| Tool | Description |
|---|---|
| `record_round` | Persists a screening-round result in SQLite. |
| `list_rounds` | Reads round history, optionally filtered by workflow thread. |

The server also exposes `recruitment://rounds` as a discoverable MCP resource.

## Architecture

The agent never reads resume files directly. ChromaDB supplies ranked candidate records;
detailed resume access passes through `FilesystemMCPClient`, and each generated report is
recorded through `RecruitmentMCPClient`.

See [docs/state_machine.md](docs/state_machine.md) for the state graph, round progression,
MCP sequence, batch-processing flow, and directory-watching flow.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `MCP_ALLOWED_ROOTS` | `data/resumes,output` | Filesystem security boundary |
| `MCP_RESUME_ROOT` | `data/resumes` | Resume resource and watcher root |
| `MCP_OUTPUT_ROOT` | `output` | Writable report directory |
| `MCP_CHROMA_DIR` | `chroma_db` | Persistent vector database |
| `MCP_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `MCP_OLLAMA_MODEL` | `llama3.2:3b` | Local chat model |
| `MCP_BATCH_CONCURRENCY` | `4` | Concurrent batch limit |
| `MCP_RECRUITMENT_DB` | `runtime/recruitment.db` | SQLite audit database |

Local configuration, vector databases, runtime databases, caches, output, and `.venv`
are excluded from Git.

## Reused from prior milestones

- Resume parsing, chunking, embeddings, vector-store, ingestion, and hybrid matching come
  from `RAG-Based-Profile-Matching`.
- The six-node state model, intent routing, three screening rounds, and human interrupt
  workflow come from `Agentic-Profile-Matching`.
- Direct filesystem calls were replaced by MCP tools and client adapters in this milestone.

## Test scenarios

Run the complete suite:

~~~cmd
python -m pytest
~~~

Run the focused transport and multi-MCP checks:

~~~cmd
python -m pytest tests\test_transport_integration.py tests\test_recruitment_mcp_server.py tests\test_recruitment_mcp_client.py -v
~~~

The suite covers filesystem boundaries, structured errors, discovery, resources, batching,
watching, stdio, Streamable HTTP, both MCP clients, LangGraph routing, Rich CLI behavior,
real Chroma matching, and the end-to-end workflow. See
[docs/test_scenarios.md](docs/test_scenarios.md) for the coverage matrix.

The live Ollama smoke test is opt-in:

~~~cmd
set RUN_LIVE_OLLAMA=1
python -m pytest -m live_ollama -v
set RUN_LIVE_OLLAMA=
~~~

## Performance note

The system runs locally without a paid API. Initial ingestion can take longer while the
embedding model is downloaded and loaded. Ollama response time depends on local CPU/GPU
capacity; this is expected local-inference latency rather than an MCP transport delay.

## Demo video

[Watch the demo](https://drive.google.com/file/d/1yanPze3pjYcZuATNS4I4rwfibtl8qiBO/view?usp=drive_link)
