# Test Scenarios

## Automated coverage

| Scenario | Expected result |
|---|---|
| Read/list/write/search supported files | Structured success response |
| Access outside allowed roots | Forbidden-path domain error |
| Unsupported file extension | Unsupported-extension domain error |
| Unsafe overwrite | Already-exists error unless overwrite is enabled |
| Mixed batch | Ordered per-file results and independent failure counts |
| Watch start/status/stop | Stable watcher ID and lifecycle state |
| Duplicate watch event | Second event inside the debounce window is ignored |
| Automatic ingestion | Event moves from pending to processed or failed |
| stdio transport | Initialize, discover, call a tool, and read a resource |
| Streamable HTTP transport | Initialize and call tools at the MCP endpoint |
| Unknown tool | MCP result is marked as an error |
| Invalid arguments | MCP validation identifies the invalid field |
| Client capability check | Connection fails when required tools are absent |
| LangGraph initial flow | Ranking and report complete before interrupt |
| Three screening rounds | Ranking, comparison, then recommendation |
| MCP resume-read failure | Agent returns a safe failure message |
| Real Chroma match | Correct hybrid-scored candidate is returned |

## Commands

~~~powershell
.\.venv\Scripts\python.exe -m pytest -m "not integration and not live_ollama"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest --cov=ai --cov=backend --cov=filesystem_mcp_server

$env:RUN_LIVE_OLLAMA="1"
.\.venv\Scripts\python.exe -m pytest -m live_ollama
~~~

The live test is skipped by default so CI and reviewers do not need a running model.
