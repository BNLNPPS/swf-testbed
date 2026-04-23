# AI-enabled WFMS proposal — draft diagrams

Mermaid prototypes to support the "Why us?" section. Finished versions will
graduate to hand-authored SVG in `swf-testbed/docs/images/` style.

Open this file's preview (`Ctrl+Shift+V`) to render.

---

## Diagram 1 — Three Contexts

The thesis picture: three LLM-integrated systems running today, ordered
left-to-right by increasing LLM autonomy. Shared MCP ecosystem feeds all
three. Top banner carries the 6-month claim.

```mermaid
flowchart TB
    classDef llm fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#000
    classDef human fill:#fff3e0,stroke:#e65100,color:#000
    classDef tool fill:#f1f8e9,stroke:#33691e,color:#000
    classDef delta fill:#fce4ec,stroke:#ad1457,stroke-dasharray:4 3,color:#000

    Thesis["<b>Today</b>: LLMs inform humans &nbsp;&nbsp;━━ 6-month step ━━▶&nbsp;&nbsp; <b>Tomorrow</b>: LLMs act within workflows"]:::delta

    subgraph P1["① Real-time bot — Mattermost"]
        direction TB
        U1["ePIC users"]:::human
        B1["AI bot<br/>Haiku · cross-session memory<br/>context harness"]:::llm
        O1["Q&A, diagnostics, on-the-fly analysis"]
        U1 --> B1 --> O1 --> U1
    end

    subgraph P2["② Research orchestrator — corun-ai"]
        direction TB
        U2["Expert evaluators<br/>(production, user learning)"]:::human
        S2["Scheduler<br/>model × sysprompt × MCP set<br/>config compare & annotate"]
        B2["Long-latency worker<br/>Opus / Sonnet / Gemini / Gemma<br/>minutes–tens of minutes"]:::llm
        O2["Deep research entry<br/>(e.g. Perlmutter performance)"]
        U2 --> S2 --> B2 --> O2 --> U2
    end

    subgraph P3["③ Active workflow orchestrator — swf-testbed"]
        direction TB
        U3["Testbed users"]:::human
        B3["LLM orchestrator<br/>launch · run · monitor<br/>assess · summarize"]:::llm
        W3["Hybrid workflow<br/>LLM steps ⇄ deterministic agents<br/>DAQ sim → PanDA workers"]
        O3["Completed run + summary"]
        U3 --> B3 --> W3 --> B3
        W3 --> O3 --> U3
    end

    subgraph MCP["Shared MCP tool ecosystem"]
        direction LR
        IH["<b>In-house</b><br/>AskPanDA · PanDA Monitor · Streaming Workflow"]:::tool
        AD["<b>Adopted</b><br/>Rucio · XRootD · uproot · LXR · GitHub · Zenodo"]:::tool
    end

    Thesis -.-> P1
    Thesis -.-> P2
    Thesis -.-> P3
    P1 --> MCP
    P2 --> MCP
    P3 --> MCP
```

Legend: blue = LLM, orange = human, green = MCP/tool surface, pink-dashed = thesis / 6-month delta.

---

## Diagram 3 — Hybrid Workflow Anatomy

One real swf-testbed streaming run as a pipeline of alternating LLM and
deterministic steps, with the MCP tools each LLM step actually calls.
Human-in-loop gate between ⑨ and ⑩ is where the 6-month scope lands.

```mermaid
flowchart TB
    classDef llm fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#000
    classDef det fill:#eeeeee,stroke:#555,color:#000
    classDef hitl fill:#fff3e0,stroke:#e65100,stroke-dasharray:5 3,color:#000
    classDef mcp fill:#f1f8e9,stroke:#33691e,font-size:11px,color:#000

    U["User prompt<br/>'run a fast-processing test<br/>and summarize results'"]:::hitl

    L1["① Prepare<br/>select config, check prior runs"]:::llm
    L1t["swf_list_workflow_executions<br/>pcs_list_tags · swf_get_system_state"]:::mcp

    L2["② Start testbed"]:::llm
    L2t["swf_start_user_testbed"]:::mcp

    L3["③ Start workflow"]:::llm
    L3t["swf_start_workflow<br/>(stf_count, config, …)"]:::mcp

    D1["④ DAQ simulator<br/>emits STF files"]:::det
    D2["⑤ Data agent<br/>STF registration"]:::det
    D3["⑥ FastMon agent<br/>samples Time Frames"]:::det
    D4["⑦ Fast processing agent<br/>TF slices → PanDA"]:::det
    D5["⑧ PanDA workers<br/>EICrecon reconstruction"]:::det

    L4["⑨ Monitor in-flight<br/>errors, throughput, stragglers"]:::llm
    L4t["swf_list_logs(level='ERROR')<br/>swf_list_workflow_executions<br/>panda_get_activity"]:::mcp

    G1{"human-in-loop<br/>gate<br/>(scope of 6-mo work)"}:::hitl

    L5["⑩ Assess & summarize<br/>narrative run report,<br/>anomaly notes,<br/>comparison to prior runs"]:::llm
    L5t["swf_get_workflow_execution<br/>panda_study_job · lxr_ident"]:::mcp

    O["Run entry + summary<br/>annotated, searchable"]:::hitl

    U --> L1 --> L2 --> L3 --> D1 --> D2 --> D3 --> D4 --> D5 --> L4
    L4 --> G1 --> L5 --> O

    L1 -.- L1t
    L2 -.- L2t
    L3 -.- L3t
    L4 -.- L4t
    L5 -.- L5t
```

Legend: blue = LLM step, grey = deterministic agent, dashed orange = human-in-loop / user edge, green captions = MCP tool calls.

---

## Diagram 2 — MCP Tool Ecosystem

One LLM reaches into the experiment's operational stack through a two-tier
tool set. Counters "everyone has MCP now" by showing depth into production
systems.

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

---

## Diagram 4 — 6-month Delta (before / after)

Same boxes, one arrow moves, one audit loop added. Makes the project
feel like a bounded increment on an operational system, not a research
leap.

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

---

## Diagram 5 — PanDA Scale Provenance

The "why 6 months is plausible" anchor: we're layering on a production
WFMS with a decade of operational history, not starting from zero.

```mermaid
flowchart BT
    classDef app fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#000
    classDef ai fill:#f1f8e9,stroke:#33691e,stroke-width:2px,color:#000
    classDef panda fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#000

    subgraph L1["<b>Foundation</b> — PanDA production WFMS (operational since 2005)"]
        direction LR
        P1["ATLAS @ LHC<br/>O(million) jobs/day<br/>200+ institutions"]:::panda
        P2["PanDA monitor<br/>deep drill-down<br/>refined 15+ years"]:::panda
        P3["ePIC production<br/>(monthly campaigns, OSG, HPC)"]:::panda
        P4["ePIC streaming<br/>workflow testbed<br/>(this team, 2025+)"]:::panda
    end

    subgraph L2["AI instrumentation today — this team (2024–)"]
        direction LR
        I1["AskPanDA MCP"]:::ai
        I2["PanDA Monitor MCP"]:::ai
        I3["VectorDB RAG"]:::ai
        I4["Streaming Workflow MCP"]:::ai
        I5["3rd-party MCP (6+)"]:::ai
    end

    subgraph L3["<b>New application layer</b> — LLM-driven orchestration (proposed, 6 months)"]
        direction LR
        A1["LLM workflow<br/>orchestrator"]:::app
        A2["Hybrid workflows<br/>LLM + deterministic"]:::app
        A3["Harnessed autonomous<br/>LLM action"]:::app
        A4["LLM research assistant<br/><i>evolution of Mattermost<br/>bot + codoc-ai</i>"]:::app
    end

    L1 --> L2
    L2 --> L3
```

---

## Diagram 6 — corun-ai Research Loop

Shows corun-ai as an orchestrated research system, not a chatbot.
Config-compare in annotation threads is the R&D-testbed feature.

```mermaid
sequenceDiagram
    autonumber
    participant U as Expert evaluator
    participant S as Scheduler
    participant W as Worker LLM
    participant M as MCP tools
    participant E as Research entry

    U->>S: submit research prompt<br/>+ config (model · sysprompt · MCP set)
    S->>W: spawn worker with config
    loop deep analysis — minutes to tens of minutes
        W->>M: tool call (PanDA / LXR / Rucio / ...)
        M-->>W: results
        W->>W: reason · refine · iterate
    end
    W-->>S: completed analysis
    S->>E: write research entry
    E-->>U: notify + surface result
    U->>E: annotate · thread comments
    Note over U,E: config variants compared<br/>side-by-side in threads —<br/>an R&D testbed, not a product
```

---

Fill in concrete numbers (PanDA jobs/day, testbed run count, corun-ai prompt count, etc.) before these go into proposal figures.
