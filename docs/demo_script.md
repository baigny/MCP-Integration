# Demo Video Script (5-6 minutes)

## 0:00-0:40 - Problem and architecture

- Explain that the previous agent called local filesystem functions directly.
- Show the state and sequence diagrams.
- Explain that MCP tools perform actions and resources expose readable data.

## 0:40-1:30 - Start and discover the MCP server

~~~powershell
.\.venv\Scripts\Activate.ps1
python filesystem_mcp_server.py --transport http --host 127.0.0.1 --port 8000
~~~

- Show the HTTP MCP endpoint.
- Run the transport tests or use an MCP inspector.
- Show six tools, two static resources, and the resume resource template.

## 1:30-2:20 - Filesystem and batch operations

- List the resume directory.
- Read one TXT, PDF, DOCX, or PPTX resume.
- Search for `Python`.
- Batch two valid files and one missing file.
- Highlight ordered results and partial-failure counts.

## 2:20-3:00 - Directory watching

- Start a watcher on the resume directory.
- Copy a supported resume into it.
- Show detected, pending, and processed status.
- Show debouncing and stop the watcher.

## 3:00-4:35 - End-to-end agent

~~~powershell
python matching_agent.py --jd "Need a senior Python engineer with AWS experience"
~~~

- Show the MCP connection panel and discovered tools.
- Show the Round 1 ranking.
- Compare the top two candidates.
- Advance through Rounds 2 and 3.
- Show that Round 3 reads the selected resume through MCP.

## 4:35-5:10 - Error handling and tests

- Attempt to read outside the allowed roots.
- Show the structured `forbidden_path` response.
- Run the complete test suite.

## 5:10-5:40 - Production notes

- Configuration comes from environment variables and local secrets are excluded.
- Writes are restricted and overwrite-protected.
- Embeddings load lazily and generated data is not committed.
- State that a second MCP server is optional bonus work, not part of this implementation.
