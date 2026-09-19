# MCP Integration Project Plan

## Summary

Build a standalone `MCP-Integration/` project using the relevant components from the three existing repositories. Preserve the free local stack—Ollama, sentence-transformers, ChromaDB, and LangGraph—while replacing direct filesystem access in the agent with standardized MCP client calls.

Implement the project using test-driven development (TDD): write a failing test, implement the minimum behavior required to pass it, then refactor while keeping the suite green. Complete all required deliverables before starting the optional multi-MCP bonus.

## 1. Project Foundation

- Create the new project as `MCP-Integration/` beside the three cloned repositories.
- Target the locally available Python 3.12 runtime and use a virtual environment.
- Copy only reusable source code and representative resume/job-description data.
- Do not copy virtual environments, secrets, output files, caches, or generated Chroma databases.
- Add dependency and development tooling for MCP, LangGraph, Ollama, ChromaDB, document parsing, Rich, pytest, pytest-asyncio, and coverage.
- Add `.env.example`, `.gitignore`, configuration loading, and structured logging.
- Configure repository-local Git identity before committing:

  ```powershell
  git config user.name "baigny"
  git config user.email "baigny@gmail.com"
  ```

- Use the authenticated Git remote belonging to `baigny` when pushing. Do not store GitHub credentials or tokens in the repository.

## 2. TDD Workflow

For every behavior:

1. **Red:** Add a focused test that describes the expected public behavior and confirm it fails for the intended reason.
2. **Green:** Implement the smallest production change that makes the test pass.
3. **Refactor:** Improve structure, naming, and duplication without changing behavior.
4. Run the focused tests after each change and the complete suite before every commit and push.

Testing order:

1. Filesystem service and path-safety tests.
2. MCP tool and resource contract tests.
3. Batch-processing tests.
4. Directory-watcher and automatic-ingestion tests.
5. MCP client-adapter tests.
6. LangGraph node and routing tests.
7. stdio and Streamable HTTP integration tests.
8. End-to-end CLI workflow tests.

Use temporary directories and temporary Chroma collections in tests. Mock Ollama for the default automated suite and keep the real-model smoke test optional.

## 3. Filesystem MCP Server

Create `filesystem_mcp_server.py` with the official Python MCP SDK/FastMCP.

### Transports

- `stdio` for the default local LangGraph integration.
- Streamable HTTP for independent deployment and JSON-RPC demonstration.
- Let the MCP SDK manage initialization, capability negotiation, request IDs, discovery, and JSON-RPC 2.0 protocol responses.

### MCP tools

Expose the original Milestone 1 operations:

- `read_file(filepath)`
- `list_files(directory, extension=None)`
- `write_file(filepath, content, overwrite=False)`
- `search_in_file(filepath, keyword)`

Preserve supported TXT, PDF, DOCX, and PPTX behavior from the latest filesystem implementation.

Add:

- `watch_directory(directory, action, auto_ingest=True)`
  - `start` creates a background watcher and returns a watcher ID.
  - `status` returns pending, processed, failed, and detected-file information.
  - `stop` shuts the watcher down cleanly.
  - Supported new or modified resumes are debounced and automatically queued for Chroma ingestion.
- `batch_process(paths, operation, keyword=None, max_concurrency=None)`
  - Operations: `read`, `search`, and `ingest`.
  - Preserve input order in results.
  - Report success or failure for each file and aggregate totals.
  - Continue processing after individual file failures.

### MCP resources

- `resumes://catalog` — discover available resume files and metadata.
- `resume://{relative_path}` — read one resume through a resource template.
- `config://server` — expose safe, non-secret server configuration.
- Support standard tool, resource, and resource-template discovery.

### Safety and configuration

- Restrict operations to configured resume and output roots.
- Resolve paths before use and reject traversal, absolute paths outside allowed roots, and symlink escapes.
- Reject unsupported extensions and protect existing files unless `overwrite=True`.
- Configure allowed roots, Chroma path, Ollama URL/model, embedding model, HTTP host/port, log level, watch debounce, and concurrency through environment variables.
- Use stable responses containing `success`, `data`, `error`, and operation metadata.
- Return appropriate MCP errors for invalid arguments, missing files, forbidden paths, unsupported formats, and internal failures.
- Do not log resume contents, API tokens, or credentials.

## 4. LangGraph Agent Refactor

Create `matching_agent.py` from the current six-node workflow:

```text
START
  -> parse_jd
  -> extract_requirements
  -> search_resumes
  -> rank_candidates
  -> generate_report
  -> human_feedback
       -> extract_requirements (refinement)
       -> generate_report (next round)
       -> human_feedback (inline answer)
       -> END
```

- Remove direct filesystem imports and calls from the agent layer.
- Add an async MCP client adapter that:
  - Uses stdio by default and supports Streamable HTTP through configuration.
  - Discovers required tools and resources during startup.
  - Provides typed wrappers for MCP calls.
  - Applies timeouts and converts MCP failures into safe agent results.
  - Cleans up sessions and child processes reliably.
- Route resume discovery and reading through MCP.
- Preserve ChromaDB retrieval, 60/40 semantic-keyword scoring, requirement extraction, ranking, comparison, interview questions, refinement, and three screening rounds.
- Use Ollama `llama3.2:3b` and `all-MiniLM-L6-v2` embeddings by default.
- Provide a Rich CLI displaying connection state, discovered capabilities, graph nodes, summarized MCP calls, rankings, reports, and feedback prompts.

## 5. Public Commands and Interfaces

```powershell
python filesystem_mcp_server.py --transport stdio
python filesystem_mcp_server.py --transport http --host 127.0.0.1 --port 8000
python matching_agent.py
pytest
pytest --cov
```

Public MCP tools:

- `read_file`
- `list_files`
- `write_file`
- `search_in_file`
- `watch_directory`
- `batch_process`

Public MCP resources:

- `resumes://catalog`
- `resume://{relative_path}`
- `config://server`

## 6. Test and Acceptance Scenarios

- Read, write, list, and search TXT, PDF, DOCX, and PPTX files.
- Discover MCP tools, resources, and resource templates over stdio and HTTP.
- Validate raw JSON-RPC request IDs, successful results, unknown methods, invalid arguments, and internal errors.
- Reject traversal, forbidden absolute paths, symlink escapes, unsupported files, and unsafe overwrites.
- Batch mixed valid, invalid, duplicate, and unreadable files without aborting the batch.
- Start, inspect, and stop a watcher; debounce duplicate events; ignore unsupported files; automatically ingest supported resumes.
- Run LangGraph tests with mocked MCP responses and mocked Ollama output.
- Run a real MCP subprocess against temporary filesystem and Chroma directories.
- Exercise initial matching, refinement, comparison, explanation, interview questions, three-round screening, ambiguous JDs, empty results, and MCP disconnection.
- Run the full automated suite successfully before committing or pushing.

## 7. Documentation and Demo

- Document installation, configuration, ingestion, stdio, HTTP, CLI, testing, and troubleshooting in `README.md`.
- Add a Mermaid state-machine and sequence diagram covering user, LangGraph, MCP client, filesystem server, watcher, ingestion pipeline, and ChromaDB.
- Include `.env.example` without secrets.
- Prepare a 5–6 minute demo script showing:
  1. Architecture and MCP discovery.
  2. HTTP server startup.
  3. Tool/resource discovery and JSON-RPC compliance.
  4. File operations and batch processing.
  5. Directory watching with automatic ingestion.
  6. End-to-end LangGraph matching and refinement.
  7. A handled error case.
- The submitter records the final video using the supplied script and commands.

## 8. Optional Bonus Phase

Only begin after all required acceptance tests pass:

- Create `resume_search_mcp_server.py` as a second MCP server.
- Move Chroma ingestion, collection status, and semantic search behind it.
- Connect the agent to both filesystem and search MCP sessions.
- Demonstrate filesystem discovery/reading followed by vector retrieval through the second server.
- Keep the bonus isolated so it cannot destabilize the required deliverables.

## 9. Commit and Push Rules

- Commit only after the relevant focused tests and the complete test suite pass.
- Keep each commit limited to one coherent TDD increment.
- Use a concise imperative subject and, only when useful, a concise body.
- Do not add author, co-author, generated-by, or attribution trailers.
- Do not mention AI assistance in commit messages.
- Example:

  ```text
  Add safe MCP file reading

  Validate allowed roots and return structured read errors.
  ```

- Before pushing, verify:
  - `git config user.name` returns `baigny`.
  - `git config user.email` returns `baigny@gmail.com`.
  - Tests pass.
  - No `.env`, credentials, tokens, local databases, caches, or generated outputs are staged.
  - The destination remote is the intended `baigny` repository.

## Assumptions

- The required project is a new sibling folder named `MCP-Integration`.
- Rich CLI is the required interface; no paid hosting or UI framework is needed.
- Ollama and local embeddings keep the normal workflow free.
- Callable behavior is exposed as MCP tools; discoverable read-only data is exposed as MCP resources.
- Required functionality has priority over the optional multi-MCP bonus.
