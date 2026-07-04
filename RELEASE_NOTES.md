# Release Notes

## v36 (2026-06-21)

### EpicProd Production Workflow Shell (swf-monitor)

The production landing page and header navigation were rebuilt around the actual EpicProd workflow boundaries:

- **Production Requests** — questionnaire/request intake, explicitly separated from PCS.
- **Physics Configuration System** — physics tags, physics category numbering, generator configurations, simulation/reconstruction/background tags, datasets, submission templates, and submit-ready tasks.
- **Production Campaigns** — campaign catalogs spanning current, past, and future campaigns.
- **PanDA Execution** — live task/job browsing, diagnostics, queues, error summaries, and Alarms.
- **Validation** — placeholder workflow column reserved for the next integration.

The header now keeps active items as normal links while using intensity to show the current section, avoiding layout shifts from bold text. PCS highlighting is constrained to real PCS pages, requests no longer light up PCS, and the System menu consolidates System Status, Admin where appropriate, and About while preserving status color both in the top bar and dropdown.

Page chrome was tightened across the production UI: compact title spacing, consistent title font sizes, standard Eastern build-time display, cleaned queue formatting, and clearer filled action buttons for PanDA activity error/diagnostic actions.

### Production Request Questionnaire Intake (swf-monitor)

Production request questionnaire import became first-class request intake, not part of PCS:

- Questionnaire list/detail pages with request-id links, contact metadata, generator/event filters, raw metadata inspection, and support for long event requests.
- Import script and REST API for loading questionnaire responses.
- Match-management support so questionnaire requests can be connected to downstream production planning.
- Devcloud import controls are hidden on the external face where they are not operationally valid.

### PCS Identity, Tags, and Compose Workflow (swf-monitor)

PCS advanced from tag/catalog browsing toward a coherent configuration system with stable composed identities:

- Dataset and task identity now uses composed names rather than transient internal IDs; MCP wrappers, URLs, detail links, and task action buttons were aligned around that identity.
- Background tags were added as a real tag axis, with import/backfill support and compose UI integration.
- Physics schema coverage was expanded so imported catalog rows can map cleanly onto physics tags, including background, detector/version, beam, species, Q2, and related axes.
- Imported catalog rows are adopted into the editable draft lifecycle instead of remaining as legacy import records.
- Draft-by-default tag/task lifecycle: objects can be composed and iterated in draft form, then locked at submission.
- The compose views were renamed and polished, with two-panel lists, sort toggles, identity-keyed navigation, used-by lists, and consistent action visibility.
- PCS catalogs now classify future/current/past releases correctly, display tags more consistently, and surface EVGEN input matched/unmatched populations.

### Production Operations Agent and Automated Submission (swf-monitor)

The production operations agent is now the execution boundary for EpicProd write actions on the BNL side. Browser-facing pages request work through external-safe API triggers; the agent performs the privileged or long-running operation in the production environment and reports completion back to the UI.

- EVGEN submission is routed through the agent rather than fragile page POSTs.
- Submit buttons in PCS produce the production task envelope, call an external-safe API trigger, and report outcomes through SSE completion events.
- Task submission metadata is carried through task JSON so submitted tasks can show actions and submission state.
- Submission artifacts now use the true Rucio DID for `outDS` and `taskName`, with tag-based LFN templates carrying `$PANDAID` for per-file uniqueness.
- Command previews and task submission specs are server-authoritative, regenerated from current PCS state rather than hand-maintained client text.
- `record-submission` is idempotent and the submit-readiness gate is visible before lock/submission.
- Payload-log retrieval and caching were hardened, with live page updates via SSE instead of reload loops.
- Cleaner-killer cron runs standalone with explicit prod environment parsing and a bounded restart policy.

### Rucio, Catalog, and Data-Lineage Integration (swf-monitor)

The production catalog can now assimilate and reconcile external EVGEN inputs and produced outputs:

- JLab Rucio EVGEN input snapshots are imported into the PCS catalog and matched against requested datasets.
- A self-hosted Rucio DID detail page links catalog output DIDs to local inspection.
- Rucio snapshot writes use the configured temporary path, preserving the agent write-path boundary.
- Documentation now records the data-lineage model and the external-face write-action contract.

### PanDA Monitoring and System Status (swf-monitor)

PanDA monitoring pages received focused operational upgrades:

- Task and job detail pages now prioritize payload logs, owner information, monitor links, composed task names, and expanded context.
- PanDA activity grouping, filter behavior, query counts, time windows, and transformation-viewer rendering were refined.
- Error, diagnostic, queue, job, and task pages were brought into the streamlined production page layout.
- System Status was added as a first-class monitor page and production nav item, with stale-threshold documentation and refresh tooling.
- ePIC production job-file inventory was added, including model, sync command, and supporting docs.

### Production Alarms Moved to swf-monitor

The production alarm system moved from `swf-remote` to `swf-monitor`:

- Alarm dashboard, editor, event detail, run reports, team editor, and standalone runner now live in `swf-monitor`.
- Alarm configuration, events, engine runs, teams, and history now use monitor-side state rather than the remote instance.
- Existing alarm state was imported from the remote instance: 2 contexts, 17,554 entries, and 38 versions.
- The runner installs as a standalone venv under the monitor deployment, writes state to monitor Postgres, and sends email through AWS SES using `boto3` until BNL mail delivery replaces it.
- Alarm helper packaging was cleaned up and install permissions were hardened.
- `swf-remote` now proxies `/prod/alarms/...` from monitor; its old alarm code is retained only for rollback/reference, with old cron disabled.

### Access, Deployment, and Documentation (swf-monitor)

- Read-only production pages are open by default; writes and sensitive actions remain gated.
- Login preserves `?next=` so users land on the requested page after authentication.
- Apache config and deployment docs were updated for the current production shape.
- New and revised docs cover EpicProd operations, the ops agent, SSE push, validation planning, questionnaire ingest, background tags, external access, Postgres MCP, system status, and alarms.

### MCP Runtime Stability (swf-monitor)

The monitor completed the move away from `django-mcp-server` for the streaming MCP runtime. The FastMCP/Starlette path replaces the freeze-prone Django integration that had been causing monitor stalls under MCP client load; the v36 branch also pins the relevant Starlette dependency and removes the old migration-smoke cruft.

The practical result is operational: MCP remains available without tying up the main Django request path, and the freezes seen before the migration have not recurred in production use.

### Agent Background Execution (swf-common-lib, swf-testbed)

`BaseAgent` now has opt-in background execution for long-running handlers. Agents that block on subprocesses or slow REST / Rucio / xrootd calls can offload that work to a bounded thread pool with `run_in_background(...)`, keeping the STOMP receiver thread responsive for later messages and liveness traffic.

The behavior is deliberately opt-in: existing agents that do not call it behave as before. For consumers that do opt in, the wrapper keeps PROCESSING/READY state correct while background work is in flight, logs worker exceptions, supports deduplication by work key, serializes bus sends from worker threads, and drains workers during shutdown. The first production consumer is the EpicProd operations agent; the design rationale is documented in `swf-testbed`.

### swf-testbed Notes

- MCP local configuration now carries bearer-auth configuration for the shared token path.
- Installation docs record the requirements-to-dev-update-to-production dependency chain.
- Release-note terminology was cleaned up to use Compose rather than the retired Workbench name.

## v35 (2026-05-20)

### ePIC Production Task Catalog (swf-monitor)

A new dynamic catalog of ePIC production tasks under PCS. The catalog imports the canonical `epic-prod/datasets.csv` request manifest, joins it against live Rucio output, and presents the campaigns through three lifecycle tabs:

- **Past** — completed campaigns, year-grouped Release navigation with All 2026 at the front, Stage column and Stage filter, faceted filters derived from the DID path (Geometry / Beam / Physics / Q² / Species / Energy), unit-aware Energy sort, NC/CC folded into the Physics facet.
- **Current** — the active 26.x release. Faceted filters on Geometry / Beam / Physics / Q² / Species / Energy / Priority / Nevents / Generator, with a Rucio arrivals timeline at the top of the page in two stacked panes (datasets and output TB) on 12 h bins. A one-click **Make current** button promotes the requested release. **Update from Rucio** refreshes the live JLab snapshot of current-campaign output in ~12 s (parallelized down from ~80 s).
- **Last** — a clean, frozen Past variant that pairs a release selector with the matching Rucio timeline. Suitable for quick "what landed in the last cycle" inspection without filter state.

Each catalog row carries the full request line in the Dataset cell: Campaign, Input dataset path, Sample (Generator / version), Description with the issue link, an Output rollup that summarises Simu / Reco file counts and bytes by RSE with an **Incomplete file counts** indicator, plus Nev (M), Backgd / New / pTDR / early flags and Priority. Filters are live (no Apply button). The "Past output mode" surfaces subsequent request↔Rucio matching with a disclosure pane for unmatched requests so it is obvious which requested datasets have not yet been produced.

`https://epic-devcloud.org/prod/pcs/tasks/catalog/`

### Two-Panel Compose View (swf-monitor)

`/swf-monitor/pcs/tasks/compose/?tab=tasks` opens a two-panel sibling of the catalog: a concise left list of the current campaign's tasks, and a right pane with full detail and (for owners) Edit / Copy / Delete actions. The two views are interchangeable siblings — the catalog is for bulk inspection, compose for detail and editing — and a task can be opened in either from anywhere it appears.

- **Left rows.** PWG chip, dataset path with the standard `/volatile/eic/EPIC/` prefix elided (full path on hover), status, priority, sample, Nev, and Bg / New / pTDR / ES / Other flag pills. The title row never wraps, so row height is predictable as the list is scrolled.
- **Collapsed filter bar.** Fourteen facet titles — Status, Requestor, Sample, Submission, Priority, Nev, Geom, Beam, Physics, Q², Species, Energy, Output, Flags — wrap into one row at the top; clicking a title expands only that facet's values. Filter state is mirrored in the URL so a filtered view is bookmarkable.
- **Right pane.** For CSV-imported tasks the dataset's auto-generated Physics / EvGen / Simu / Reco tags are placeholders and are no longer rendered — the panel instead lists the real physics characterization carried in `overrides.csv_import` (Sample, Geom, Beam, Physics, Q², Species, Energy, Nev, Background, Detector). Non-CSV tasks retain the original tag table. The panel title is the dataset path (matching the compose-list row), never the internal `csv_import.<slug>` key.
- **Cross-linking.** Catalog Input links and the dataset-detail "Used by Production Tasks" lists now land in compose with the row preselected, so navigation between bulk and detail views is one click in either direction.

### PCS — Submission Path, Intake, MCP Wrappers (swf-monitor)

PCS now owns the full path from a CSV request to a submitted PanDA task.

- **Submission artifact endpoint.** `GET /swf-monitor/pcs/api/prod-tasks/command/?name=<task>&fmt=<format>` regenerates the submission artifact from current PCS state on every call (no DB writes), with `fmt` in `condor | panda | jedi | dump`. The companion `pcs-task-cmd` CLI (introduced in v34) drives JEDI submission with no Django imports or DB credentials.
- **External EVGEN dataset support.** Register an external generator-level dataset and link it to a task as an input; `ProdConfig.workflow_mode` distinguishes `external_evgen` and `internal_evgen` flows.
- **Task-dataset relations** (input / output / intermediate) are schema-free lists on the task, with a one-shot backfill script linking legacy `csv_file` records to their input Dataset rows.
- **REST intake endpoints** (`datasets/intake/`, `prod-tasks/intake/`, `link-input/`, `set-status/`, `record-submission/`) carry lifecycle gates and double-submit guards; each is exposed as a peer MCP tool so PanDAbot and other clients can drive intake without constructing REST queries.
- **Catalog backend** acquires `Campaign` and `ProdRequest` models, a `services` layer, an admin surface, and doc cross-refs.

### Catalog Documentation and Roles

Two design documents under `swf-monitor/docs/`:

- **`EPICPROD_TASK_CATALOG.md`** — data model and view conventions for the catalog.
- **`PCS_DATASET_REQUEST_WORKFLOW.md`** — planning workflow from a PWG/DSC physics request through Compose to running tasks, including the dynamic public catalog direction.

A new short section, **Roles and Approval**, captures the design intent that once PCS is integrated with the ePIC phonebook and COmanage, role assertions will gate authoring vs publication: PWG members author Physics Configs within PCS-enforced templates, and production managers approve before propagation to automated production.

### MCP Server Migrated to FastMCP (swf-monitor)

The streaming `/swf-monitor/mcp/` endpoint (isolated on its own ASGI worker in v34) is migrated from `django-mcp-server` to a standalone FastMCP ASGI entrypoint. The cutover was staged behind parity smoke probes against the live django-mcp service so tool semantics did not change. Worker count is raised from 2 to 20 so dozens of concurrent MCP clients fit cleanly on a single host. POST-only enforcement and Bearer-token authentication are in place; the pandabot and testbed-bot now thread `MCP_BEARER_TOKEN` through to the new mount.

### PanDA / BigMon Polish (swf-monitor)

- **Task aggregates.** `nrunning`, `nretries`, `nfinalfailed`, and a derived `computed_finalfailurerate` are joined in by every PanDA task query and surfaced on the task list and detail views. `panda_list_tasks` default limit raised from 25 to 500.
- **Cell-fill state colors** applied consistently across BigMon-equivalent pages. Copy-ID buttons on identifier cells. Near-zero-latency Bootstrap tooltips. Uniform Eastern-time clock across all timestamp columns.
- **Read-only REST API for tasks / activity** with per-task job counts — drives the UI and is also available to external scripts.

### PanDAbot (swf-monitor)

- **corun-ai completion notifications** integrated; bot commentary on a job routes to the originating Mattermost thread rather than the channel.
- **DID-specific Rucio rule lookup** so a question about a specific dataset finds its replication rules without an LLM tool-search round trip.
- **Reply discipline.** Direct `@PanDAbot` mentions now require a substantive reply (silence-only variants are flagged). Plain channel chatter no longer reaches Haiku. ePIC campaign Rucio scope handling fixed.

### Workflow Runner — Script Logs Identified Correctly (swf-testbed)

Logs emitted from inside workflow scripts (`stf_datataking.py`, `prompt_processing.py`) now record their source under `module=workflow_runner` rather than the Python sentinel `<string>` (which arose because the runner used `exec()` on a code string with no synthetic filename). Filtering and searching workflow logs by module works as expected. *Thanks to Zhaoyu Yang for the diagnosis and fix.*

### Agents and Testbed Infrastructure (swf-testbed)

- **New `fast_processing` agent** with operator-facing documentation (`docs/fast-processing-workflow.md`); a companion `docs/prompt-processing-workflow.md` is also added. *Thanks to Wen Guan.*
- **Configurable STF folder** for the prompt-processing workflow via `prompt_processing.toml`; **run number in the logger** so testbed log lines can be associated with the corresponding PanDA task id. *Thanks to Zhaoyu Yang.*
- **Per-run isolation of supervisord control sockets** — multiple users can now run testbeds concurrently on the same host without `/tmp` collisions. `prompt_processing_agent.py` respects `PANDA_NICKNAME`. The earlier namespace hack is reverted in favour of the proper workflow-namespace fix. *Thanks to Dmitry Kalinkin.*
- Several Wen Guan fixes: TF-slice handling, core count, run-imminent worker deduplication, message-header conventions, fastmon default filesize, workflow-namespace correction, and the supporting `define headers for sending messages` series.

### Containerization and CI

- **Dockerfiles** for both `swf-testbed` and `swf-monitor`, plus a reworked `docker-compose.yml` covering the full local-development stack. *Thanks to Dmitry Kalinkin (`swf-testbed#46`, `swf-monitor#32`).*
- **GitHub Actions integration-test workflow** for `swf-testbed`. *Thanks to Dmitry Kalinkin (`swf-testbed#48`).*
- **swf-monitor connects only to PanDA / iDDS databases when credentials are present** — clean out-of-the-box install for users who don't need the PanDA join. *Thanks to Dmitry Kalinkin.*

### swf-common-lib

- STOMP declared as an explicit dependency in `pyproject.toml`. *Thanks to Dmitry Kalinkin.*

## v34 (2026-04-21)

### Streaming MCP Moved Off mod_wsgi (swf-monitor)

The `/swf-monitor/mcp/` endpoint now runs on a dedicated ASGI worker (uvicorn, `swf-monitor-mcp-asgi.service` on `127.0.0.1:8001`) behind Apache `ProxyPass`. Everything else (`/about/`, `/api/`, `/accounts/login/`, PCS, static files) stays on mod_wsgi.

**Why:** `django-mcp-server` uses Starlette's `StreamableHTTPSessionManager`. Under WSGI, each streaming MCP session holds a thread via `async_to_sync` for the full session lifetime. A handful of concurrent MCP clients (OpenCode, Claude Code CLI, Ollama-backed scripts, python-httpx — any streamable-HTTP MCP client) was enough to saturate the pool and 503 every dynamic URL on the site. Isolating `/mcp/` on an async worker removes that failure mode from the main app.

**What changed operationally:**

- mod_wsgi tuned for burst resilience: `threads=30`, `listen-backlog=500`, `queue-timeout=30`, `inactivity-timeout=300`, `graceful-timeout=15` — no `request-timeout` (would truncate `/api/messages/stream/` SSE long-poll).
- Proxy tuned for streaming: `timeout=3600 keepalive=On disablereuse=On`, `proxy-sendchunked`, `no-gzip`, `CacheDisable` on `/mcp/`.
- `swf-monitor-mcp-asgi.service` systemd unit added (`Restart=always`, 2 uvicorn workers).
- `src/swf_monitor_project/asgi.py` cleaned up — removed dead `mcp_app.routing` import (the module was replaced by the `mcp_server` package long ago; ASGI entrypoint was quietly broken).

### Apache Config Auto-Sync on Deploy (swf-monitor)

`apache-swf-monitor.conf` in the repo is now the source of truth. `deploy-swf-monitor.sh` diffs it against the live `/etc/httpd/conf.d/swf-monitor.conf` on every deploy; if different, it backs up live, installs from the release, validates with `httpd -t`, and rolls back on failure. The Apache reload that happens every deploy (to recycle mod_wsgi for new Python code) picks up any conf change along with it.

**Why it matters:** there was a 6-week drift — the Mar 11 `dce7abf` fix for MCP IP restriction was committed to the repo but never reached live Apache because nothing copied it. `setup-apache-deployment.sh` regenerated the conf from a hardcoded heredoc (that had drifted from the repo canonical), and `deploy-swf-monitor.sh` didn't touch Apache conf at all. Closed: setup script now `cp`s `apache-swf-monitor.conf` and splits the dynamic `LoadModule` line out to `/etc/httpd/conf.modules.d/20-swf-monitor-wsgi.conf`.

**ASGI worker is also recycled on every deploy** — uvicorn loads code once at startup, so fresh Python code requires a restart. Bots already follow the same pattern (conditional on bot-specific code change).

### PanDA Mattermost Bot — Multi-Server MCP with Progressive Tool Loading (swf-monitor)

The PanDA bot now orchestrates across **seven external MCP servers** plus the local swf-monitor MCP, selecting tools based on the user's question. New integrations:

- **LXR MCP server** (`github.com/BNLNPPS/lxr-mcp-server`, new this release) — EIC code browser cross-reference. `lxr_ident` (definitions + references), `lxr_search` (ripgrep across repos), `lxr_source` (read source with line numbers), `lxr_list` (browse directories).
- **uproot MCP server** (`github.com/eic/uproot-mcp-server`) — inspect ROOT files: list branches, read arrays, sample contents.
- **JLab-Rucio and BNL-Rucio MCP servers** — query Rucio for EIC datasets, replicas, and rules.
- **GitHub MCP server** — now uses the `epic-capybara` service account with write access for bot-driven automation on EIC repos.
- **epicdoc** — RAG search over ePIC documentation (`epic_doc_search`, `epic_doc_contents`). Runs in-process inside the bot (not as a separate MCP server, not inside WSGI — initial attempt to host it in WSGI brought the monitor down and was moved; see the debugging notes in the 2026-03-31 assessment).

With that many tools, "send the whole catalog to the LLM every turn" stops working. Two new techniques address that:

- **Progressive tool loading via semantic similarity.** For each user question the bot embeds the question and ranks tools by server-prefixed cosine similarity, auto-truncating at a score cliff. The LLM sees a small, relevant slice rather than all hundreds of tools — and the rank is preserved through the display so the LLM can judge relevance.
- **3-tier tool awareness.** Every tool is visible by name + one-line catalog entry in the system prompt, so the LLM knows the full surface area exists at minimal token cost. Detailed schemas are fetched only for tools the LLM explicitly selects via `select_tools`. Server and suggestion context carries forward across thread turns, so follow-ups don't re-select from scratch.

**Other bot improvements:**

- **System prompt externalized** to `monitor_app/panda/system_prompt.txt` and re-read on every message — prompt iteration no longer requires a bot restart.
- **DPID detection hardened.** For job/task questions the bot verifies that any Data Provenance ID in the reply came from actual tool output before letting it through. Detection is now line-based and format-agnostic; trigger word **AND** a matching ID must both be present.
- **Bamboo log analysis** integrated into `panda_study_job` for failed jobs — surfaces Harvester pilot-log analysis automatically when filebrowser lookup fails. Exposed to the LLM via an explicit `log_analysis` field the bot is instructed to surface.
- **Response style rules** in the system prompt curb overenthusiastic replies (e.g., verbose explanations when a one-line answer suffices).
- Server-side matplotlib plot rendering, nightly cron scripts to auto-update each MCP server repo.

### New swf-monitor MCP Tool: `panda_harvester_workers`

Live Harvester pilot/worker counts via bamboo's `askpanda_atlas`. Useful for "what pilots are running right now?" without needing to grep through Harvester logs.

```python
panda_harvester_workers(status='running', site='NERSC', resourcetype='SCORE', days=1)
```

Returns totals plus breakdown by status, site, and resourcetype. Clean, LLM-friendly response format.

### PCS — Compose UX Polish + Programmatic Submission Path (swf-monitor)

**Compose pages (Physics/EvGen/Simu/Reco tags, Datasets, Prod Configs, Prod Tasks):**

- Uniform button styling — all filled (solid) variants, dark-green accent on live edited values, consistent New-button placement in the left panel across all compose views.
- Breadcrumbs and Cancel buttons point to compose views instead of the legacy list views.
- Name-based URL params so compose views are bookmarkable and deep-linkable.
- Owner-only edit enforcement on production configs (same discipline as tag edits).
- Edit / Copy / New buttons no longer silently fail on prod config compose (previous type-argument mismatch fixed).
- Compose panels for `command` and `taskParamMap` grow to fit content instead of forcing horizontal scroll.
- Fixed type-argument mismatch in compose URL sync.

**Production Tasks — submission artifacts:**

A single read-only endpoint regenerates a task's submission artifact from current PCS state on every call (no DB writes):

```
GET /swf-monitor/pcs/api/prod-tasks/command/?name=<task_name>&fmt=<format>
```

| `fmt` | Contents |
|-------|----------|
| `condor` | env-prefixed `submit_csv.sh` command |
| `panda` | `prun` command |
| `jedi` | `taskParamMap` for `Client.insertTaskParams()` |
| `dump` | Full view: task + dataset + all four tags + prod config + effective config |

The parameter is `fmt` because DRF reserves `format` for its own content-negotiation.

**New CLI `pcs-task-cmd`** — stdlib-only Python client over that endpoint. The recommended way for production operators and automation to fetch submission artifacts (no Django import, no DB credentials):

```bash
# Inspect a task
pcs-task-cmd <task_name> --format dump

# Submit to JEDI (requires valid PanDA auth)
pcs-task-cmd <name> --format jedi | python -c '
import json, sys
from pandaclient import Client
print(Client.insertTaskParams(json.load(sys.stdin)))
'

# Pipe Condor command into bash
eval "$(pcs-task-cmd <name> --format condor)"
```

Environment: `SWFMON_URL` (default `https://epic-devcloud.org/prod`), optional `SWFMON_TOKEN` for non-public deployments.

**JEDI taskParamMap now surfaced on task detail** — `build_task_params()` renders the full param map users will submit, viewable and copyable directly from the compose page.

### Deploy-Script Improvements (swf-monitor)

- **`swf-monitor-mcp-asgi.service` restart step** — always restarts on deploy (uvicorn needs it).
- **Apache conf sync** — described above.
- **Shared HuggingFace cache** — `deploy-swf-monitor.sh` ensures `/opt/swf-monitor/shared/hf_cache` exists with open perms and appends `HF_HOME=` to `production.env` if missing. Bamboo and epicdoc reuse the cache across processes.
- **Bot restarts after health check, not before** — avoids killing bots mid-request if Apache comes up broken.
- **Nightly cron** (`nightly-update-mcp-servers.sh`, `nightly-update-epicdoc.sh`) — auto-updates sibling MCP-server repos and re-ingests ePIC documentation into epicdoc's ChromaDB store.

### PanDA Production Monitoring — Job Deep-Dive Enhancements (swf-monitor)

- **NERSC portal log URLs** surfaced for Perlmutter jobs in `panda_study_job` — clickable links to the NERSC job portal alongside existing Harvester log URLs.
- **Bamboo log analysis** runs on failed jobs automatically; LLM-friendly `log_analysis` field with fallback to Harvester URL when filebrowser fails.
- **Error field rename** in `/panda job` output (source → component) — fixes a KeyError that surfaced on some job records.

### Auth & API Changes (swf-monitor)

- **`TunnelAuthMiddleware`** now requires an `X-Remote-User` header before auto-authenticating — anonymous proxy requests no longer get a free pass. Matches the threat model of the TunnelAuthentication DRF backend (also checks the header before acting).
- **`/api/users/`** response now includes `email`, `first_name`, `last_name` — enables richer devcloud account sync.

### Documentation

- **`PRODUCTION_DEPLOYMENT.md`** refreshed for the two-backend layout, new setup-apache-deployment.sh behavior, and the full deploy step list (conf sync, ASGI worker restart).
- **`MCP.md`** — ASGI/WSGI split documented, transport description corrected (it IS streamable HTTP), tool summary count corrected to 44, all tool categories added.
- **`PCS.md`** — MCP Tools table corrected to the tools that actually exist.
- **JEDI design docs** added: `JEDI_INTEGRATION.md` (architecture, field mapping, implementation plan) and `JEDI_EPIC_PROPOSAL.md` (technical proposal for PanDA team review) — roadmap for direct task submission to JEDI replacing the current `prun` CLI text generation.

### Agent Resilience (swf-common-lib)

Further hardening of the BaseAgent lifecycle under unreliable infrastructure:

- **Agent-ID registration retries indefinitely** on API failure (previously gave up after a bounded number of attempts). Agents starting into a partially-up monitor no longer silently fail to register.
- **Improved resilience to server restarts** — agents survive transient monitor outages and resume their heartbeat loop cleanly on reconnection.

### swf-testbed — Upstream Contributions Integrated

Several contributions landed direct-to-main during and just before the v34 cycle that were not acknowledged in earlier release notes. They are part of main as of this release. With thanks:

**Agent code consolidation — Dmitry Kalinkin (PR #35, #36)**

Unified agent code into the `swf-testbed` repository:

- **PR #35 "Import SOTA agents"** — imports `agents/data_agent.py` and `agents/processing_agent.py` with full git history from the sibling repositories `BNLNPPS/swf-data-agent` and `BNLNPPS/swf-processing-agent`. Supersedes the shell of earlier example agents with BaseAgent-derived implementations (Rucio / XRootD integration, MQ handlers, dataset lifecycle).
- **PR #36 "Delete superseded agents"** — final cleanup once the unified `agents/` package stabilized: removes `example_agents/daq_simulator_superseded.py`, `example_agents/example_daqsim_agent_superseded.py`, and `example_agents/processing_agent.py`.

**Prompt-processing workflow — Zhaoyu Yang (PR #37, #38)**

A new streaming workflow for prompt processing of time-frame slices, built on top of Dmitry's imported agents package:

- `agents/prompt_processing_agent.py` — new agent for the prompt-processing pipeline
- `workflows/prompt_processing.py`, `workflows/prompt_processing.toml`, `workflows/prompt_processing_default.toml` — workflow definition and default config
- Orchestrator wiring in `workflows/orchestrator.py`; supervisord entry in `agents.supervisord.conf`
- `scripts/dummy_stf_processing.sh` — placeholder payload for development
- Refactor updates to `agents/data_agent.py` supporting the new flow
- Documentation: `docs/prompt-processing-workflow.md`, architecture image `docs/images/prompt-processing-workflow.png`, `docs/skills-for-testbed.md`

**CRIC endpoint / queue-config expansions — Xin Zhao (PR #34)**

- `config/ddm_endpoints.json` — substantial DDM endpoint additions (+465 lines)
- `config/panda_queues.json` — PanDA queue config additions (+1030 lines)
- Reflects updated CRIC-sourced site/endpoint data for ePIC production

### swf-testbed — Baseline Branch Work

No user-facing changes on the `infra/baseline-v34` branch itself — administrative commits only (CLAUDE.md branch-reference updates, v33 release notes catch-up, v34 release notes including this acknowledgments section).

---

## v33 (2026-03-29)

### Dual-Mode UI: ePIC Production / ePIC Testbed (swf-monitor)

The monitor now operates in two modes, selectable via a nav bar toggle (localStorage-persisted):

- **ePIC Production** (`/prod/`) — PanDA production monitoring (activity, jobs, tasks, errors, diagnostics, queues) + PCS (tags, datasets, prod configs, prod tasks). Shared PCS sections template keeps PCS hub and production hub in sync.
- **ePIC Testbed** (`/testbed/`) — Streaming workflow testbed: workflows, time frame data, agents, messaging, system state, PanDA/Rucio.

Root URL redirects based on mode. About page updated for dual-mode, all access methods, tech stack.

### PanDA Production Pages (swf-monitor)

Full DataTables views for **Activity, Jobs, Tasks, Errors, Diagnostics**. **EIC PanDA Queues** from live schedconfig with MCP tools (`panda_list_queues`, `panda_get_queue`). **`panda_resource_usage`** for allocated vs used core-hours. **`panda_study_job`** for deep single-job analysis. **`destinationse`** (destination storage element) from filestable4 added to job listings and error summary. PanDA query modules refactored into `constants.py`, `sql.py`, `queries.py`. Monitor links point to epic-devcloud.org.

### PCS Auth & Proxy Support (swf-monitor)

Full PCS functionality through the swf-remote (epic-devcloud.org) proxy:

- **`TunnelAuthentication`** DRF backend — authenticates localhost/tunnel requests via `X-Remote-User` header without CSRF enforcement
- **`IsAuthenticatedOrReadOnly`** on all PCS API viewsets — anonymous GET, auth required for writes
- **`created_by` from `request.user`** — read-only in serializers, set server-side
- **Tag delete API** — `POST /delete/` with creator-only, draft-only enforcement
- **All PCS templates** converted from form POST to JS fetch → REST API
- **`/api/users/`** endpoint with password hash for devcloud account sync

### Mattermost PanDA Bot (swf-monitor)

- **4 MCP server types**: HTTP (PanDA, PCS), stdio (XRootD, GitHub, Zenodo)
- **DPID (Data Provenance ID)** anti-fabrication: bot verifies LLM cited a real DPID, strips from user reply, warns if verification fails
- **`/panda` slash commands** — status, errors, jobs/tasks with status filter and pagination, job/task detail, sites, site detail, help
- **`bot_manage_servers`** virtual tool — list with versions, update/rebuild/restart
- **Server-side matplotlib plots** in Mattermost
- System prompt: data integrity rules, security rules, "never ask user to look something up"

### MCP Servers

- **Zenodo** (`eic/zenodo-mcp-server`) — search, inspect, download from zenodo.org
- **XRootD** (`eic/xrootd-mcp-server`) — file browsing and reading on JLab XRootD
- **GitHub** (`github/github-mcp-server`) — read-only repo, issue, PR, actions access
- **StdioMCPClient** transport for managing external MCP server subprocesses

### Agent Resilience (swf-common-lib, swf-testbed)

- API retry with exponential backoff (swf-common-lib)
- Agent manager: supervisord health verification, SIGUSR1 heartbeat, exit heartbeat on shutdown
- check-testbed skill and supervisord health monitoring
- AI memory hooks for cross-session dialogue persistence

### Bug Fixes

- Namespace datatable: `Count('id')` on model without `id` field
- `list_tasks`: stale filter params misaligned with where clauses
- Django 5+ logout requires POST
- Workflow parameter override: auto-discover all config sections

## v32 (2026-03-02)

### PCS (Physics Configuration System) — New Django App (swf-monitor)

A new Django app for configuring production tasks based on physics inputs for ePIC Monte Carlo simulation campaigns. PCS organizes configurations as tags — named parameter sets for each stage of the MC pipeline:

- **Physics tags (p):** process, beam energies, species, Q2 range
- **EvGen tags (e):** event generator and version
- **Simu tags (s):** detector simulation config
- **Reco tags (r):** reconstruction config

Tags have a draft/locked lifecycle. Locked tags are immutable and used in production.

**Tag compose UI:** Split-panel interface for browsing, creating, editing, copying, and locking tags. Arrow key navigation, parameter filter dropdowns, inline editing with suggestion bars, predicted tag numbering, and diff highlighting for edits. Generalized for all four tag types with category-conditional fields.

**Seeded data:** `seed_campaign_tags` management command creates 64 tags from the 26.02.0 campaign (47 physics, 15 evgen, 1 simu, 1 reco).

**MCP tools:** `pcs_list_tags`, `pcs_get_tag`, `pcs_search_tags`.

### PanDA Mattermost Bot (swf-monitor)

Claude-based production monitoring chatbot in Mattermost. Listens in the `#pandabot` channel, answers questions using Claude Haiku with tool use.

- Discovers tools from MCP server automatically
- System prompt built from MCP server instructions, stays in sync with deployed tool documentation
- Supports PanDA and PCS tools
- Thread-aware conversations

### PanDA Web Monitor (swf-monitor)

New web views for ePIC-focused PanDA production monitoring:

- Activity overview, job list, task list, job detail, task detail, error summary, job diagnostics
- Cross-linking, days selector, server-side DataTables, colored status badges
- Shares data layer with MCP tools via factored `panda/` package (`constants.py`, `sql.py`, `queries.py`)

### PanDA MCP Tools — New and Enhanced (swf-monitor)

Six new tools for PanDA production monitoring via MCP:

- `panda_list_jobs` — job overview with summary stats, cursor-based pagination
- `panda_list_tasks` — JEDI task monitoring with workinggroup/processingtype filters
- `panda_get_activity` — pre-digested activity overview (aggregate counts, no individual records)
- `panda_error_summary` — aggregate error ranking across failed jobs
- `panda_diagnose_jobs` — failed job diagnostics with all 7 error component fields
- `panda_study_job` — deep single-job analysis (~40 fields, filestable, condor logs, structured errors)

### MCP Infrastructure (swf-monitor)

- Refactored monolithic `mcp.py` (2,544 lines) into `mcp/` package
- AI memory model and REST API for cross-session dialogue persistence
- Fixed `_get_username()`: use SWF_HOME directory ownership instead of `getpass.getuser()` (returns 'apache' under WSGI)
- Fixed fastmon-files API to accept STF filename string instead of requiring UUID
- Added Bootstrap 5 CSS

### Documentation Cleanup

Deleted 9 stale or superseded files across both repos (1,800+ lines removed): old monolithic README backup, abandoned design docs, failed procedure docs, one-time reports, broken index pages. Fixed hardcoded credentials in installation guide, dead links, malformed markdown, and updated CLAUDE.md branch reference to v32.

### swf-common-lib

No changes in v32.

---

## v31 (2026-02-18)

### Robustness Improvements for LLM-driven Testbed Controls

Hardened the MCP control path so AI agents can reliably start, monitor, and manage testbed workflows without misinterpreting system state.

**Testbed status fixes (swf-monitor):**
- `ready` field now checks running workflow executions, not agent count — was permanently false when agents were idle after a completed workflow
- REST heartbeat no longer overwrites `workflow_enabled` to false on every heartbeat
- `start_workflow` namespace resolution falls back to running agent manager's namespace when env var unavailable in Apache context
- `start_user_testbed` no longer destroys the agent manager on every start
- Surfaced supervisord health and agent manager errors in MCP status tools
- Fixed MCP username resolution: use SWF_HOME directory ownership, require explicit username parameter

**Agent manager hardening (swf-testbed):**
- Verify supervisord health, check agent starts, log errors instead of failing silently
- SIGUSR1 heartbeat refresh after check-testbed fixes
- Exit heartbeat on shutdown so DB immediately reflects agent manager death
- check-testbed skill for bootstrapping infrastructure
- Fixed workflow parameter override to auto-discover all config sections

**Workflow monitoring guidance:**
- MCP docs now instruct AI to actively poll `swf_get_workflow_monitor` during execution rather than sleeping

**Other:**
- AI memory hooks and documentation for cross-session dialogue persistence
- Refactored monolithic mcp.py into package (system, workflows, ai_memory, common)

## v30 (2026-02-03)

### Auth0 OAuth 2.1 Authentication for Claude.ai MCP

Added secure OAuth 2.1 authentication for remote MCP connections from Claude.ai, using [Auth0](https://auth0.com/) as the identity provider.

**How it works:**
1. Claude.ai discovers OAuth metadata via `/.well-known/oauth-protected-resource`
2. User authenticates with Auth0 (redirected to Auth0's login page)
3. Auth0 issues JWT access token to Claude.ai
4. Claude.ai includes Bearer token in MCP requests
5. Django middleware validates JWT against Auth0's JWKS endpoint

**Configuration:**
```bash
AUTH0_DOMAIN=your-tenant.us.auth0.com
AUTH0_CLIENT_ID=your-client-id
AUTH0_CLIENT_SECRET=your-client-secret
AUTH0_API_IDENTIFIER=https://your-server/swf-monitor/mcp
```

**Access modes:**
- **Claude.ai (remote)**: Requires OAuth authentication via Auth0
- **Claude Code (local)**: POST requests pass through without auth for local development

**Network requirement:** Claude.ai connects from Anthropic's servers, so the MCP endpoint must be accessible from the public internet.

### MCP Tool Naming Convention

Renamed all 29 MCP tools with `swf_` service prefix for multi-server discovery:
- `list_agents` → `swf_list_agents`
- `get_system_state` → `swf_get_system_state`
- etc.

This follows MCP best practices for environments where multiple MCP servers are connected. The prefix enables clean tool discovery and avoids naming collisions.

Reference: https://www.philschmid.de/mcp-best-practices

### Pagination Metadata for List Tools

All list tools now return pagination metadata to help LLMs manage context:

```json
{
  "items": [...],
  "total_count": 1523,
  "has_more": true,
  "monitor_urls": [...]
}
```

- `total_count`: Total matching records in database
- `has_more`: Boolean indicating results are truncated

This helps LLMs understand when query results are incomplete and whether to refine filters.

### New MCP Tool: swf_send_message

Send messages to the workflow monitoring stream:

```python
swf_send_message(
    message="Test message",
    message_type="announcement",  # or "test", custom types
    metadata={"key": "value"}     # optional
)
```

Use cases:
- Testing the message pipeline end-to-end
- Sending announcements to colleagues monitoring the stream
- Debugging SSE relay functionality

### Message Type Standardization

Standardized on `stf_ready` message type across all agents. Previously some agents used `data_ready` inconsistently. Updated `WORKFLOW_MESSAGE_TYPES` in swf-common-lib and all example agents. Also added `tf_file_registered` to the canonical message types.

### Bug Fixes

- **Fixed monitor URLs in MCP responses**: Tool responses were returning localhost URLs instead of production URLs. Now correctly returns URLs based on deployment configuration.

### Documentation

- Updated `docs/MCP.md` with all swf_ prefixed tool names
- Documented Auth0 OAuth 2.1 configuration and flow
- Added pagination metadata documentation
- Documented ActiveMQ connection patterns and messaging semantics
- Noted that `.env` files are not deployed from git (must be configured on server)
- **CLAUDE.md overhaul**: Streamlined per Anthropic best practices, added operational guidelines
- **MCP tool change guidance**: When adding/modifying MCP tools, must update `swf_list_available_tools()` hardcoded list in mcp.py

---

## v29 (2026-01-25)

### Per-User Configuration Override (SWF_TESTBED_CONFIG)

A new environment variable `SWF_TESTBED_CONFIG` enables per-user configuration overrides across all core repositories. This allows multiple users to run their own testbed instances with different configurations on the same system.

**Usage:**
```bash
export SWF_TESTBED_CONFIG=/path/to/my-testbed.toml
testbed run  # Uses your custom config instead of workflows/testbed.toml
```

This is supported in swf-testbed, swf-monitor (MCP tools), and swf-common-lib (BaseAgent).

### Agent Manager Enhancements

The user agent manager daemon introduced in v28 has been significantly improved:

- **Config-driven namespace and agent selection**: The agent manager now reads namespace and agent configuration from testbed.toml, enabling different users to run different agent sets
- **REST logging**: Agent manager logs are now sent to swf-monitor for centralized viewing via `list_logs()`
- **Restart command**: New `restart` command for reloading configuration without full stop/start cycle
- **Immediate heartbeat**: Agent manager sends heartbeat immediately on startup, not after the first interval
- **Clean disconnect**: Proper cleanup on restart prevents stale connection state
- **Venv path handling**: Improved virtual environment path resolution

### New MCP Tool: get_testbed_status

A comprehensive status tool that combines agent manager, namespace, and workflow agent information in a single call.

```python
get_testbed_status(username='wenauseic')
```

Returns:
- Agent manager status (alive, namespace, control queue)
- Summary of running/stopped agents
- List of all workflow agents with current state

This replaces the need to call multiple tools to understand testbed readiness.

### MCP Improvements

- **SWF_TESTBED_CONFIG support**: MCP tools respect the per-user config override
- **start_user_testbed safety check**: Refuses to start if workflow agents are already running - user must call stop_user_testbed first to ensure clean state
- **Log filtering fixes**: Multiple fixes to username extraction in log list views - now correctly filters by the username segment in agent instance names
- **Heartbeat API fix**: The heartbeat endpoint now properly updates operational_state, pid, and hostname fields
- **monitor_urls in responses**: MCP tool responses include links to relevant monitor UI pages

### Documentation

New architectural documentation with SVG diagrams:
- **docs/agent-management.md**: Agent lifecycle, supervisord integration, agent manager architecture
- **docs/fast-processing-workflow.md**: Fast processing pipeline, TF slice workflow, worker coordination
- **5 SVG diagrams**: Visual architecture diagrams for agent management and fast processing

Updated MCP documentation with Claude Code settings examples and query best practices.

### Signal Handlers (swf-common-lib)

BaseAgent now includes signal handlers for SIGTERM and SIGINT, enabling cleaner shutdown behavior when agents are terminated by supervisord or manually.

---

## v28 (2026-01-13)

### ActiveMQ Destination Prefix Requirement (Breaking Change)

**All ActiveMQ destinations now require explicit `/queue/` or `/topic/` prefix.** This is a breaking change that affects all agent code sending messages.

**Before (incorrect):**
```python
self.send_message('epictopic', message)  # WRONG - bare name
```

**After (correct):**
```python
self.send_message('/topic/epictopic', message)  # Correct - explicit prefix
```

**Why this matters:**
- Bare destination names were ambiguous - ActiveMQ behavior depends on broker configuration
- Explicit prefixes make the routing intention clear: `/queue/` for anycast (one consumer) vs `/topic/` for multicast (all consumers)
- BaseAgent now validates destination format and raises `ValueError` for bare names

Existing code using bare names will fail immediately with a clear error message explaining the required format. All example agents and workflow code have been updated.

### MCP Workflow Control - AI-Driven Operations

The MCP service now provides **full workflow control**, enabling AI assistants to start, stop, and monitor workflows without requiring CLI access. This is the key enabler for AI-driven testbed operations.

**New workflow control tools:**
- `start_workflow` - Start a workflow by sending a command to the DAQ Simulator agent. All parameters are optional; defaults are read from the user's `testbed.toml`. Override specific parameters (e.g., `stf_count=5`) while inheriting others from config.
- `stop_workflow` - Stop a running workflow gracefully by execution_id. The workflow stops at the next checkpoint.
- `end_execution` - Mark a stuck execution as terminated in the database. Use this to clean up stale executions that the agent can no longer reach.

**New agent management tools:**
- `kill_agent` - Send SIGKILL to an agent process by instance name. Looks up the agent's PID and hostname, kills if on the same host, and always marks the agent as EXITED in the database.

**New monitoring tools:**
- `get_workflow_monitor` - Aggregated view of workflow execution: status, phase, STF count, key events, and errors (from both messages and logs). Single-call alternative to polling multiple tools.
- `list_workflow_monitors` - List recent executions (last 24h) that can be monitored.

The MCP tool count has grown from 20 to **27 tools**. Documentation in `swf-monitor/docs/MCP.md` has been updated to reflect all tools.

### User Agent Manager - Per-User Testbed Control via MCP

A new **agent manager daemon** enables MCP-driven control of per-user testbed agents. This allows AI assistants to start and stop a user's testbed without requiring SSH or terminal access.

**Architecture:**
- Each user runs a lightweight `testbed agent-manager` daemon in their swf-testbed directory
- The daemon listens on a user-specific queue (`/queue/agent_control.<username>`) for commands
- It manages supervisord-controlled agents and reports status via heartbeats

**New MCP tools:**
- `check_agent_manager(username)` - Check if a user's agent manager is alive. Returns heartbeat status, control queue name, and whether agents are running.
- `start_user_testbed(username, config_name)` - Send start command to agent manager. Agents start asynchronously.
- `stop_user_testbed(username)` - Send stop command to agent manager.

**Usage:**
```bash
# Start the agent manager daemon (run once, keeps running)
cd /data/<username>/github/swf-testbed
source .venv/bin/activate && source ~/.env
testbed agent-manager
```

Then an AI assistant can:
1. Check readiness: `check_agent_manager(username='wenauseic')`
2. Start testbed: `start_user_testbed(username='wenauseic')`
3. Run workflows: `start_workflow()`
4. Stop when done: `stop_user_testbed(username='wenauseic')`

### Persistent WorkflowRunner with Message-Driven Execution

The WorkflowRunner agent has been redesigned as a **persistent, message-driven service** rather than a one-shot script.

**Key changes:**
- WorkflowRunner now starts with supervisord and listens on `/queue/workflow_control` for commands
- Commands include `run_workflow` (from MCP `start_workflow`) and `stop_workflow`
- Each execution gets a unique `execution_id` (e.g., `stf_datataking-wenauseic-0044`)
- The `stop_workflow` command targets a specific execution by ID, enabling graceful termination

**Why this matters:**
- The WorkflowRunner is always ready to receive workflow commands - it doesn't need to be started for each run
- This models the actual ePIC system more realistically, where the DAQ system is a persistent service
- Workflows can be started and stopped via MCP without CLI access
- Multiple workflows can be managed by execution_id

### Enhanced get_system_state - User Context and Readiness

The `get_system_state` MCP tool now accepts a `username` parameter and provides user-specific context.

**New fields returned:**
- `user_context` - Namespace and workflow defaults from user's `testbed.toml`
- `agent_manager` - Status of user's agent manager daemon (healthy/unhealthy/missing/exited)
- `workflow_runner` - Status of DAQ Simulator in user's namespace
- `ready_to_run` - Boolean indicating if the user can start a workflow
- `last_execution` - Most recent workflow execution in user's namespace
- `errors_last_hour` - Count of ERROR logs in user's namespace

This enables AI assistants to answer questions like "Am I ready to run a workflow?" with a single call.

### EXITED Status and Agent Lifecycle

Improved agent lifecycle management with explicit EXITED status handling.

**Changes:**
- Agents now set `status='EXITED'` and `operational_state='EXITED'` on clean shutdown
- `list_agents` **excludes EXITED agents by default** - use `status='EXITED'` to see only exited, or `status='all'` to see all
- `kill_agent` always marks agents as EXITED, even if the kill fails
- EXITED agents don't clutter the active agent list but remain queryable for debugging

**Migration:** A database migration (`0014_systemagent_exited_status.py`) adds the EXITED choice to the status field.

### Logging Context with execution_id

Improved log traceability with execution context in log records.

**Changes:**
- New `_log_extra()` helper in BaseAgent returns consistent extra fields: `username`, `execution_id`, `run_id`
- All agent log calls should use: `logger.info("message", extra=self._log_extra())`
- `list_logs` MCP tool now supports `execution_id` parameter to filter logs by workflow execution

**Usage:**
```python
# In agent code
self.logger.info("Processing STF", extra=self._log_extra())

# Via MCP
list_logs(execution_id='stf_datataking-wenauseic-0044')
```

This enables tracing all log messages for a specific workflow execution, essential for debugging workflow failures.

### Monitor UI Improvements

**Log detail page:** The log detail view (`/logs/<id>/`) now displays the `extra_data` JSON field when present. This shows execution context (execution_id, run_id, namespace, username) that agents include via `_log_extra()`. Previously this context was captured but not visible in the UI.

**Log list filtering:** The log list now supports filtering by execution_id, complementing the existing app_name, instance_name, and level filters.

### Documentation Updates

- **MCP.md** completely rewritten to document all 27 tools with accurate parameters and return values
- Removed "Not Yet Implemented" section - all documented tools are now functional
- Added sections for Workflow Control, Agent Management, User Agent Manager, and Workflow Monitoring
- Updated tool count from 20 to 27

---

## v27 (2026-01-08)

### MCP Integration

The swf-monitor now exposes a **Model Context Protocol (MCP)** API, enabling AI assistants like Claude to query and interact with the testbed system.

**20+ MCP tools** for:
- **System state**: `get_system_state`, `list_agents`, `get_agent`, `list_namespaces`
- **Workflows**: `list_workflow_definitions`, `list_workflow_executions`, `get_workflow_execution`
- **Data**: `list_runs`, `get_run`, `list_stf_files`, `get_stf_file`, `list_tf_slices`
- **Messages & Logs**: `list_messages`, `list_logs`, `get_log_entry`

**Auto-discovery**: Add `.mcp.json` to your project root for Claude Code to automatically connect:
```json
{
  "mcpServers": {
    "swf-testbed": {
      "type": "sse",
      "url": "https://pandaserver02.sdcc.bnl.gov/swf-monitor/mcp/"
    }
  }
}
```

**Endpoint**: `https://pandaserver02.sdcc.bnl.gov/swf-monitor/mcp/`

### Agent Lifecycle Management

Agents now report process information for lifecycle management:
- **pid**: Process ID for kill operations
- **hostname**: Host where agent is running
- **operational_state**: STARTING → READY → PROCESSING → EXITED

These fields enable future orchestration features like agent health monitoring and remote termination.

### Database Logging

New `DbLogHandler` sends Python log records to the monitor database, enabling centralized log viewing:
- View logs via monitor UI at `/logs/`
- Filter by app, instance, level, time range
- Query via MCP: `list_logs(level='ERROR')`, `get_log_entry(log_id)`

### BaseAgent Improvements

- Agents report EXITED status on shutdown
- Warning logged when sending messages without namespace set
- Heartbeats include pid, hostname, operational_state

---

## v26 (2025-12-31)

### Namespaces

Workflows now operate within **namespaces**, allowing users to isolate their work from others sharing the same infrastructure.

On shared systems like pandaserver02, multiple users can run workflows simultaneously. Namespaces let you filter the monitor UI to see only your workflows, agents, and messages, and avoid conflicts with other users.

Configure your namespace in `workflows/testbed.toml` before running any workflows:

```toml
[testbed]
namespace = "your-namespace"  # e.g., "alice-dev", "team-fastmon"
```

All workflow messages now include the namespace, and the monitor UI provides namespace filtering on agents, executions, and messages.

### Monitor UI

- **Namespace pages**: List and detail views; namespace column and filter on agents, executions, messages
- **Agent list**: Type and status filters; click agent to see detail
- **Agent detail**: Streamlined view linking to filtered workflow messages
- **Workflow messages**: execution_id and run_id filters; STF count column; click for message detail
- **Message detail**: Full message content view
- **Drill-down links**: Click execution_id, run_id, namespace, or agent anywhere to navigate to details
- **Source links**: GitHub links on workflow definition (branch) and execution (commit) pages

### Workflow Refinements

**Count-based workflow completion:** Workflows can now run until a specific number of STF files are generated, rather than requiring a duration limit:

```bash
python workflows/workflow_simulator.py stf_datataking \
    --workflow-config fast_processing_default \
    --stf-count 10
```

**Immutable definitions:** Workflow definitions are now immutable once created. The definition captures the source code and configuration at creation time. Each execution records its specific git version for reproducibility.

**Source traceability:** Workflow definitions now link to their source script on GitHub. Executions record the exact git commit, so you can always trace back to the code that ran.

### Fast Processing Support

New infrastructure for fast processing workflows that sample STF data for near real-time monitoring:

- **Fast processing agent** (`example_agents/fast_processing_agent.py`) creates TF slices from STF samples
- Configurable sampling rate, slices per sample, and processing time
- Agents can start mid-run and extract context from messages
- New monitor views: TF Slices (`/tf-slices/`) and Run States (`/run-states/`)

### Agent Improvements

- Agents now register using the workflow name as their type (e.g., `STF_Datataking` instead of generic `workflow_runner`)
- Retry logic for initial ActiveMQ connection improves reliability on startup
- Agent list in monitor now supports type and status filters

### Infrastructure

- Docker-compose updated with Redis and health checks
- Artemis queue configuration guide added (`docs/artemis-queue-configuration.md`)
- Fixed environment loading that was breaking git commands when `~/.env` contained PATH references

---

*For detailed technical changes, see the pull requests for [swf-testbed](https://github.com/BNLNPPS/swf-testbed/pulls), [swf-common-lib](https://github.com/BNLNPPS/swf-common-lib/pulls), and [swf-monitor](https://github.com/BNLNPPS/swf-monitor/pulls).*
