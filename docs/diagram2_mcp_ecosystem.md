# diagram2_mcp_ecosystem

MCP ecosystem: one LLM reaches into the experiment's operational stack
through a two-tier tool set. Answers the reviewer who thinks "everyone
has MCP tools now" by showing depth into production systems.

```mermaid
flowchart TB
    classDef llm fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#000
    classDef ih fill:#f1f8e9,stroke:#33691e,color:#000
    classDef ad fill:#fff8e1,stroke:#f57f17,color:#000
    classDef sys fill:#fafafa,stroke:#888,color:#444

    LLM["<b>LLM</b><br/>Opus · Sonnet · Haiku · Gemini · Gemma<br/>sysprompt · effort level · context harness"]:::llm

    subgraph IH["In-house — purpose-built on our production WFMS"]
        direction LR
        T1["AskPanDA<br/><i>job diagnostics</i>"]:::ih
        T2["PanDA Monitor MCP<br/><i>operational state</i>"]:::ih
        T3["Streaming Workflow MCP<br/><i>active testbed control</i>"]:::ih
    end

    subgraph AD["3rd-party MCP — 6+ community/standard tools"]
        direction LR
        T4["Rucio MCP"]:::ad
        T5["XRootD MCP"]:::ad
        T6["uproot MCP"]:::ad
        T7["LXR XREF MCP"]:::ad
        T8["GitHub MCP"]:::ad
        T9["Zenodo MCP"]:::ad
    end

    subgraph SYS["Reaches into"]
        direction LR
        S1["PanDA DB<br/>monitor · testbed"]:::sys
        S2["Rucio<br/>data catalogs"]:::sys
        S3["XRootD<br/>remote I/O"]:::sys
        S4["ePIC codebase<br/>(55+ repos)"]:::sys
        S5["Zenodo<br/>official repo"]:::sys
    end

    LLM --> IH
    LLM --> AD
    IH --> SYS
    AD --> SYS
```
