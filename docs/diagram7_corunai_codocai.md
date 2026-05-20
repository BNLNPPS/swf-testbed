# diagram7_corunai_codocai

corun-ai + codoc-ai: the research orchestrator and its immediate
application, spanning frontier, commercial, and open-source models. The
open-source tier requires local hardware, which is why the team has
implemented a remote-inference bridge — open-source models run on the
user's desktop (Mac Studio / ollama) and plug into corun-ai as a
first-class dispatch target.

```mermaid
flowchart TB
    classDef user fill:#fff3e0,stroke:#e65100,color:#000
    classDef codoc fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#000
    classDef orch fill:#e8eaf6,stroke:#3949ab,stroke-width:2px,color:#000
    classDef frontier fill:#fff8e1,stroke:#f57f17,color:#000
    classDef oss fill:#f1f8e9,stroke:#33691e,stroke-width:2px,color:#000
    classDef remote fill:#fce4ec,stroke:#ad1457,stroke-width:2px,stroke-dasharray:6 3,color:#000
    classDef tool fill:#f1f8e9,stroke:#33691e,color:#000
    classDef out fill:#ffffff,stroke:#555,color:#000

    U["Expert evaluator<br/>documentation questions · production examination"]:::user

    CODOC["<b>codoc-ai</b> — immediate application<br/>documentation drafting · production analysis"]:::codoc

    CORUN["<b>corun-ai</b> scheduler<br/>config = model × sysprompt × MCP set<br/>configure · dispatch · compare"]:::orch

    subgraph MODELS["Model ensemble — three providers, common scheduler"]
        direction LR
        M1["<b>Anthropic</b><br/>Claude Opus · Sonnet · Haiku<br/><i>Anthropic API · claude -p CLI</i>"]:::frontier
        M2["<b>Google</b><br/>Gemini 2.5 Pro · Flash<br/><i>Google API</i>"]:::frontier
        M3["<b>Open source</b><br/>Gemma 4 via ollama<br/><i>needs local GPU hardware</i>"]:::oss
    end

    REMOTE["<b>Remote inference worker</b><br/>open-source models hosted on<br/>user desktop (Mac Studio · ollama)<br/>bridged to corun-ai as a scheduler target<br/><i>enables commercial vs. open-source comparison</i>"]:::remote

    MCP["<b>MCP tool ecosystem</b><br/>in-house: AskPanDA · PanDA Monitor · Streaming Workflow · VectorDB RAG<br/>3rd-party (6+): Rucio · XRootD · LXR · GitHub · Zenodo · …"]:::tool

    OUT["<b>codoc-ai outputs</b><br/>documentation drafts · production-examination reports ·<br/>cross-model comparison threads (user annotations)"]:::out

    U --> CODOC
    CODOC --> CORUN
    CORUN --> M1
    CORUN --> M2
    CORUN --> M3
    M3 -. hosted by .-> REMOTE
    M1 --> MCP
    M2 --> MCP
    M3 --> MCP
    MCP --> OUT
```
