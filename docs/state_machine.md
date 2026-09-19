# Agent and MCP Architecture

## LangGraph state machine

~~~mermaid
stateDiagram-v2
    [*] --> parse_jd
    parse_jd --> extract_requirements
    extract_requirements --> search_resumes
    search_resumes --> rank_candidates
    rank_candidates --> generate_report
    generate_report --> human_feedback
    human_feedback --> extract_requirements: refine criteria
    human_feedback --> generate_report: next screening round
    human_feedback --> human_feedback: compare / explain / interview
    human_feedback --> [*]: done
~~~

The graph is checkpointed by thread ID. The human feedback node uses a LangGraph
interrupt, and the CLI resumes it with the reviewer's feedback.

## Agent-to-MCP sequence

~~~mermaid
sequenceDiagram
    actor Recruiter
    participant CLI as Rich CLI
    participant Graph as LangGraph Agent
    participant Client as FilesystemMCPClient
    participant Server as Filesystem MCP Server
    participant FS as Allowed Filesystem
    participant Chroma as ChromaDB
    Recruiter->>CLI: Submit job description
    CLI->>Graph: Start graph
    Graph->>Chroma: Semantic + keyword candidate search
    Chroma-->>Graph: Ranked candidate records
    Graph-->>CLI: Round 1 report + interrupt
    Recruiter->>CLI: Next round / refine / compare
    CLI->>Graph: Resume with feedback
    Graph->>Client: read_file
    Client->>Server: tools/call over stdio or HTTP
    Server->>FS: Validate root and extract content
    FS-->>Server: Resume text and metadata
    Server-->>Client: Structured MCP result
    Client-->>Graph: Normalized result
    Graph-->>CLI: Report / questions / recommendation
~~~

## Watch and ingestion flow

~~~mermaid
flowchart LR
    A[New or modified resume] --> B[Watchdog event]
    B --> C{Supported extension?}
    C -- No --> D[Ignore]
    C -- Yes --> E{Duplicate inside debounce window?}
    E -- Yes --> D
    E -- No --> F[Background ingestion executor]
    F --> G[Extract and chunk]
    G --> H[Local sentence-transformer embeddings]
    H --> I[ChromaDB upsert]
    I --> J[Watcher status: processed]
    F -->|failure| K[Watcher status: failed]
~~~
