# Agent and MCP Interaction Flow

## End-to-end architecture

This diagram makes the protocol boundary explicit. The LangGraph agent can query the vector index directly for ranking, but all resume-file access passes through the MCP client and server.

~~~mermaid
flowchart LR
    User([Recruiter]) --> CLI[Rich CLI]

    subgraph Agent[LangGraph application]
        CLI --> Graph[Matching state graph]
        Graph --> LLM[Ollama chat model]
        Graph --> Search[Hybrid candidate search]
        Graph --> Client[FilesystemMCPClient]
        Graph --> AuditClient[RecruitmentMCPClient]
    end

    Search --> Chroma[(ChromaDB)]

    subgraph Protocol[MCP protocol boundary]
        Client <-->|JSON-RPC 2.0<br/>stdio or Streamable HTTP| Server[Filesystem MCP server]
    end

    Server --> Guard{Path and extension valid?}
    Guard -->|Yes| Files[(Allowed resume and output roots)]
    Guard -->|No| Error[Structured MCP error]
    Files --> Extract[TXT / PDF / DOCX / PPTX extraction]
    Extract --> Server
    Error --> Server
    AuditClient <-->|MCP stdio| AuditServer[Recruitment MCP server]
    AuditServer --> SQLite[(SQLite round history)]
~~~

## LangGraph state machine

The graph pauses at `human_feedback` through a LangGraph interrupt. Its checkpoint is keyed by thread ID, so the CLI can resume the same state with a `Command` containing the recruiter's response.

~~~mermaid
stateDiagram-v2
    direction LR
    [*] --> ParseJD
    ParseJD --> ExtractRequirements
    ExtractRequirements --> SearchResumes
    SearchResumes --> RankCandidates
    RankCandidates --> GenerateReport
    GenerateReport --> HumanFeedback

    state GenerateReport {
        [*] --> SelectRound
        SelectRound --> RankingReport: Round 1
        SelectRound --> DeepComparison: Round 2
        SelectRound --> MCPResumeRead: Round 3
        MCPResumeRead --> Recommendation: read succeeds
        MCPResumeRead --> SafeFallback: read fails
        RankingReport --> [*]
        DeepComparison --> [*]
        Recommendation --> [*]
        SafeFallback --> [*]
    }

    HumanFeedback --> ExtractRequirements: refine criteria
    HumanFeedback --> GenerateReport: next round
    HumanFeedback --> HumanFeedback: compare / explain / questions
    HumanFeedback --> [*]: done / stop / exit
~~~

### Round progression

~~~mermaid
flowchart TD
    R1[Round 1<br/>rank candidate pool] --> I1{{Human interrupt}}
    I1 -->|next round| R2[Round 2<br/>LLM deep comparison]
    R2 --> I2{{Human interrupt}}
    I2 -->|next round| R3[Round 3<br/>MCP resume read]
    R3 --> Result[Recommendation and<br/>five screening questions]

    I1 -->|refine requirements| Filter[Extract constraints<br/>such as minimum years]
    I2 -->|refine requirements| Filter
    Filter --> R1

    I1 -->|compare / explain / questions| Answer[Answer against current shortlist]
    I2 -->|compare / explain / questions| Answer
    Answer --> I1

    I1 -->|done| End([End])
    I2 -->|done| End
~~~

## Agent-to-MCP request sequence

~~~mermaid
sequenceDiagram
    autonumber
    actor Recruiter
    participant CLI as Rich CLI
    participant Graph as LangGraph
    participant Search as Candidate search
    participant Client as MCP client
    participant Server as MCP server
    participant FS as Allowed filesystem

    CLI->>Client: Open configured transport
    Client->>Server: initialize
    Server-->>Client: capabilities and server info
    Client->>Server: tools/list
    Server-->>Client: six tool definitions
    Client->>Client: verify required capabilities

    Recruiter->>CLI: Submit job description
    CLI->>Graph: ainvoke initial state
    Graph->>Search: semantic + keyword search
    Search-->>Graph: ranked candidate records
    Graph-->>CLI: Round 1 report + interrupt

    loop Recruiter review
        Recruiter->>CLI: refine / compare / next round
        CLI->>Graph: Command(resume=feedback)
        Graph-->>CLI: updated report + interrupt
    end

    Recruiter->>CLI: next round to Round 3
    CLI->>Graph: resume checkpoint
    Graph->>Client: read_file(resume_path)
    Client->>Server: tools/call
    Server->>FS: validate and extract
    alt Read succeeds
        FS-->>Server: content and metadata
        Server-->>Client: structured success result
        Client-->>Graph: normalized content
        Graph-->>CLI: recommendation + questions
    else Read fails
        FS-->>Server: domain failure
        Server-->>Client: structured error result
        Client-->>Graph: normalized failure
        Graph-->>CLI: safe fallback report
    end
~~~

## Batch-processing flow

~~~mermaid
flowchart TD
    Call[batch_process request] --> Validate{Operation valid?}
    Validate -->|No| Invalid[Return invalid-operation error]
    Validate -->|Yes| Limit[Apply bounded concurrency]
    Limit --> FanOut{Process each path}
    FanOut --> Read[Read]
    FanOut --> Search[Search]
    FanOut --> Ingest[Ingest]
    Read --> Collect[Preserve input order]
    Search --> Collect
    Ingest --> Collect
    Collect --> Summary[Return per-file results<br/>succeeded and failed counts]
~~~

One file failure does not cancel the remaining batch. Each item retains its own structured success or error result.

## Directory-watching and ingestion flow

~~~mermaid
flowchart TD
    Start[watch_directory: start] --> ValidateRoot{Allowed directory?}
    ValidateRoot -->|No| Reject[Structured error]
    ValidateRoot -->|Yes| Watcher[Start watchdog observer]
    Watcher --> Event[Created or modified event]
    Event --> Supported{Supported extension?}
    Supported -->|No| Ignore[Ignore event]
    Supported -->|Yes| Duplicate{Inside debounce window?}
    Duplicate -->|Yes| Ignore
    Duplicate -->|No| Pending[Record pending event]
    Pending --> Auto{Auto-ingest enabled?}
    Auto -->|No| Detected[Record detected status]
    Auto -->|Yes| Worker[Background ingestion executor]
    Worker --> Extract[Extract metadata and text]
    Extract --> Chunk[Chunk content]
    Chunk --> Embed[Generate local embeddings]
    Embed --> Upsert[(ChromaDB upsert)]
    Upsert --> Processed[Record processed status]
    Worker -->|exception| Failed[Record failed status]
    Processed --> Status[watch_directory: status]
    Failed --> Status
    Detected --> Status
    Status --> Stop[watch_directory: stop]
~~~
