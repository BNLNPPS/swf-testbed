# Bootstrap Guide for Claude

**Date:** 2026-01-07
**Branch:** infra/baseline-v27 (all 3 repos)

## Project

ePIC Streaming Workflow Testbed. Agent-based system with ActiveMQ messaging.

**Attention AIs:** This is not a chronicle of completed work. This is quick essential background to current status and next steps.
Be concise and to the point. When something is done and isn't essential background for next steps, remove it.

**Repos** (siblings in /data/wenauseic/github/):
- **swf-testbed** - workflows, example agents
- **swf-monitor** - Django web app, REST API
- **swf-common-lib** - BaseAgent class

**Host:** pandaserver02.sdcc.bnl.gov

## Critical Rules

- **COMMIT BEFORE DEPLOY** - Deploy pulls from git repo, not local files. Always commit and push changes before running deploy script.
- Activate venv before any python
- All 3 repos on same branch (currently v27, shorthand for infra/baseline-v27)
- Redeploy swf-monitor after Django changes: `sudo bash /data/wenauseic/github/swf-monitor/deploy-swf-monitor.sh branch infra/baseline-v27`

## Commands

See [docs/quick-start.md](docs/quick-start.md) for run commands.


# SESSION STATUS 2026-01-07

## MCP MODERNIZATION - DONE (Basic Implementation)

MCP integration complete. Old custom `mcp_app/` removed, replaced with proper MCP via django-mcp-server.

**Endpoint:** `/mcp/mcp`
**Documentation:** `swf-monitor/docs/MCP.md`
**Tools defined in:** `swf-monitor/src/monitor_app/mcp.py`

### Current Tools

| Tool | Description |
|------|-------------|
| `get_system_status()` | Overall health: agent counts, executions, messages |
| `list_agents(namespace=None)` | List agents with status and heartbeat |
| `get_agent(name)` | Specific agent details |
| `list_namespaces()` | List isolation namespaces |
| `list_workflow_definitions()` | Available workflow definitions |
| `list_workflow_executions(namespace, status, hours)` | Recent executions with filters |
| `get_workflow_execution(execution_id)` | Specific execution details |
| `list_messages(namespace, sender, message_type, minutes)` | Recent messages with filters |
| `start_workflow`, `stop_workflow` | Stubs - not yet implemented |

### Key Design Points

- **Tools only** - MCP Resources not used (they're for passive context injection, not interactive queries)
- **Tool docstrings are critical** - they're the only documentation the LLM sees for discovery
- **Simple tools with optional filters** - LLM-friendly, not complex query languages

### Pending

- Commit and push changes to swf-monitor
- Redeploy: `sudo bash /data/wenauseic/github/swf-monitor/deploy-swf-monitor.sh branch infra/baseline-v27`
- Test with Claude Desktop or Claude Code

---

## IMMEDIATE NEXT STEP: Expand MCP Tools Based on Monitor UI

The browser-based monitor (swf-monitor Django UI) is the definitive expression of what information users want. The MCP service should provide natural language access to this same information.

**Task:** Study the monitor UI views and templates to understand the full data model and user workflows, then expand MCP tools to cover:

1. **High-level views**
   - Workflow definitions and executions overview
   - System dashboard statistics

2. **Drilling down by namespace/user**
   - Agent ensembles grouped by namespace
   - User ownership (username embedded in agent names)
   - Execution history per namespace

3. **Workflow artifacts**
   - STF files in the workflow
   - TF sample files created from STF files
   - File metadata and relationships

4. **Message details**
   - Messages by agent, by type, by workflow stage
   - Message payloads and timing

**Files to study:**
- `swf-monitor/src/monitor_app/views.py` - what data the UI presents
- `swf-monitor/src/monitor_app/templates/` - how data is structured for users
- `swf-monitor/src/monitor_app/models.py` - StfFile, TFSlice, Run, etc.
- `swf-monitor/src/monitor_app/workflow_models.py` - workflow data model

**Goal:** MCP tools should enable the same queries and drill-downs that users can do in the browser, but via natural language.

---

## NEXT MAJOR TASK: WORKFLOW ORCHESTRATION

### Problem
- Each agent requires its own terminal/process
- No way to define "this workflow needs these agents"
- No single command to start/stop agent group
- Multiple testbed.toml files (workflows/, example_agents/) - should be ONE

### Architecture Decision
Use **supervisord** for agent management (already in project), NOT subprocesses.

**Agent behavior:**
- Agents are **persistent** - they start, wait for work, process it, close out, go back to waiting
- Agents should not exit after processing - they're long-running services
- This is the production architecture we're building toward

### Solution Design

**1. Single testbed.toml in workflows/**

All agents use `workflows/testbed.toml`. Delete `example_agents/testbed.toml`.

```toml
[testbed]
namespace = "torre1"

[workflow]
name = "stf_datataking"
config = "fast_processing_default"
duration = 120
realtime = true

[agents]
# Agents managed by supervisord

[agents.processing]
enabled = true
script = "example_agents/example_processing_agent.py"

[agents.data]
enabled = false
script = "example_agents/example_data_agent.py"

[agents.fastmon]
enabled = false
script = "example_agents/example_fastmon_agent.py"

# Override workflow config values using descriptive section names
[fast_processing]
stf_count = 5

[daq_state_machine]
stf_interval = 1.0
```

**2. Workflow Orchestrator**

New CLI command: `swf-testbed run [testbed.toml]`

Orchestrator behavior:
1. Read testbed.toml
2. For each enabled agent:
   - If not running in supervisord → start it
   - If running → health check (heartbeat recent?)
3. When all agents verified running and healthy → start the workflow run
4. Graceful shutdown on Ctrl+C (stop workflow, optionally stop agents)

**3. supervisord Integration**

- Generate/update supervisord.conf from testbed.toml agent definitions
- Use supervisorctl to start/stop/status agents
- Agents report health via heartbeat to monitor

### Implementation Steps

1. Extend testbed.toml schema with [agents] section
2. Delete example_agents/testbed.toml, update agents to use workflows/testbed.toml
3. Create orchestrator module in swf-testbed
4. Update supervisord.conf generation to include agents from testbed.toml
5. Implement health check via monitor API (check last_heartbeat)
6. Single CLI command to run workflow with agent management

### Files to Modify

- `workflows/testbed.toml` - extend schema
- `example_agents/testbed.toml` - DELETE
- `example_agents/*.py` - update config_path to use workflows/testbed.toml
- `src/swf_testbed_cli/main.py` - add `run` command
- `supervisord.conf` template - agent definitions


## PENDING: STFWorkflow DEPRECATION

STFWorkflow model is unused - WorkflowMessage has all needed fields. UI still references it (dashboard stats, workflow list). Decision: deprecate entirely.
