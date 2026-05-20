# diagram4_delta_before_after

The 6-month delta visualized. Same boxes, one arrow moves, one audit
loop added. Makes the project feel like a bounded increment on an
operational system, not a research leap.

```mermaid
flowchart LR
    classDef llm fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#000
    classDef human fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#000
    classDef wfms fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px,color:#000
    classDef audit fill:#fffde7,stroke:#f9a825,stroke-dasharray:4 3,color:#000
    classDef delta fill:#fce4ec,stroke:#ad1457,color:#000

    subgraph TODAY["<b>Today</b> — LLM informs, human decides"]
        direction TB
        T_LLM["LLM"]:::llm
        T_MCP["MCP tools<br/><i>reads · analyzes</i>"]:::llm
        T_HUM["<b>Human decides</b>"]:::human
        T_WFMS["WFMS acts"]:::wfms
        T_LLM --> T_MCP --> T_HUM --> T_WFMS
    end

    subgraph NEXT["<b>Proposed (6 months)</b> — LLM decides on pre-defined classes"]
        direction TB
        N_LLM["LLM"]:::llm
        N_MCP["MCP tools<br/><i>reads · analyzes · <b>decides</b></i>"]:::llm
        N_WFMS["WFMS acts"]:::wfms
        N_AUD["HITL audit trail<br/><i>async human review</i>"]:::audit
        N_LLM --> N_MCP --> N_WFMS
        N_WFMS -.-> N_AUD
        N_AUD -.-> N_LLM
    end

    DELTA["<b>Delta:</b><br/>• 'human decides' → 'LLM decides'<br/>• HITL audit loop added<br/>• Scope gated by decision-class allowlist"]:::delta

    TODAY -.-> DELTA -.-> NEXT
```
