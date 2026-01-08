# Bootstrap Guide for Claude

**Date:** 2026-01-08
**Branch:** infra/baseline-v27 (all 3 repos)

## Project

ePIC Streaming Workflow Testbed. Agent-based system with ActiveMQ messaging.

**Attention AIs:** This is not a chronicle of completed work. This is quick essential background to current status and next steps.
Be concise and to the point. When something is done and isn't essential background for next steps, remove it.

**Repos** (siblings in /data/wenauseic/github/):
- **swf-testbed** - workflows, example agents
- **swf-monitor** - Django web app, REST API, MCP service
- **swf-common-lib** - BaseAgent class

**Host:** pandaserver02.sdcc.bnl.gov

## Critical Rules

- **COMMIT BEFORE DEPLOY** - Deploy pulls from git repo, not local files. Always commit and push changes before running deploy script.
- Activate venv before any python
- All 3 repos on same branch (currently v27, shorthand for infra/baseline-v27)
- Redeploy swf-monitor after Django changes: `sudo bash /data/wenauseic/github/swf-monitor/deploy-swf-monitor.sh branch infra/baseline-v27`

## Commands

See [docs/quick-start.md](docs/quick-start.md) for run commands.


# SESSION STATUS 2026-01-08

## MCP - COMPLETE

MCP integration complete via django-mcp-server. Claude Code auto-connects via `.mcp.json`.

**Endpoint:** `https://pandaserver02.sdcc.bnl.gov/swf-monitor/mcp/`
**Documentation:** `swf-monitor/docs/MCP.md`, `swf-testbed/README.md`
**Tools defined in:** `swf-monitor/src/monitor_app/mcp.py`

### MCP Tools

| Category | Tools |
|----------|-------|
| System | `get_system_state`, `list_agents`, `get_agent`, `list_namespaces`, `get_namespace` |
| Workflows | `list_workflow_definitions`, `list_workflow_executions`, `get_workflow_execution`, `end_execution` |
| Data | `list_runs`, `get_run`, `list_stf_files`, `get_stf_file`, `list_tf_slices`, `get_tf_slice` |
| Messages | `list_messages` |
| Logs | `list_logs`, `get_log_entry` |
| Actions | `start_workflow` (stub), `stop_workflow` (stub) |

### Monitor DB Logging

- `DbLogHandler` class in `monitor_app/db_log_handler.py`
- All `monitor_app.*` loggers write to AppLog DB table
- MCP actions logged via standard Python logging

---

## NEXT MAJOR TASK: WORKFLOW ORCHESTRATION

### Problem
- Each agent requires its own terminal/process
- No way to define "this workflow needs these agents"
- No single command to start/stop agent group
- Multiple testbed.toml files (workflows/, example_agents/) - should be ONE

### Architecture Decisions

**1. Command name:** `testbed` (package remains `swf-testbed`)
- `testbed run`, `testbed status`, etc.

**2. Supervisord separation:** Two config files
- `supervisord.conf` - backend services (postgres, monitor, redis)
- `agents.supervisord.conf` - workflow agents (processing, fastmon, etc.)
- Different lifecycle: backend always running, agents start/stop per workflow

**3. Orchestrator location:** `workflows/orchestrator.py`
- Consistent with workflow_runner.py, workflow_simulator.py
- CLI command imports from there

**4. Agent naming:**
- **Program name** (supervisord): `example-processing-agent` - stable, for management
- **Instance name** (agent): `processing-agent-wenauseic-0042` - unique with sequence ID for logging/tracking

**5. Agent states (operational_state field):**
- STARTING - process coming up
- READY - connected to MQ, waiting for work, sending heartbeats
- PROCESSING - handling workflow messages
- EXITED - process terminated

**6. Agents are persistent:**
- Start, wait for work (READY), process (PROCESSING), return to READY
- Between workflow runs: sit in READY state, maintain heartbeats
- Don't exit after processing - long-running services

### Schema Changes (SystemAgent model)

Add to `swf-monitor/src/monitor_app/models.py`:

```python
# New fields for SystemAgent
pid = models.IntegerField(null=True, blank=True, help_text="Process ID for kill operations")
hostname = models.CharField(max_length=100, null=True, blank=True, help_text="Host where agent runs")
operational_state = models.CharField(
    max_length=20,
    choices=[
        ('STARTING', 'Starting'),
        ('READY', 'Ready'),
        ('PROCESSING', 'Processing'),
        ('EXITED', 'Exited'),
    ],
    default='STARTING',
    help_text="What the agent is doing (vs status which is health)"
)
```

Note: `status` = health (OK/WARNING/ERROR), `operational_state` = activity

### MCP Tools for Agent Management

**Supervisord level:**
- `list_supervised_agents()` - programs under supervisord, process status
- `start_supervised_agent(program_name)`
- `stop_supervised_agent(program_name)`
- `restart_supervised_agent(program_name)`

**Instance level:**
- `get_agent_instance_status(instance_name)` - detailed instance info
- `kill_agent(instance_name)` - kill -9 by PID, with confirmation (for stuck agents)

### testbed.toml Schema

```toml
[testbed]
namespace = "torre1"

[workflow]
name = "stf_datataking"
config = "fast_processing_default"
duration = 0
realtime = true

[agents.processing]
enabled = true
program = "example-processing-agent"

[agents.fast_processing]
enabled = true
program = "example-fast-processing-agent"

# Workflow config overrides
[fast_processing]
stf_count = 5

[daq_state_machine]
stf_interval = 1.0
```

### Orchestrator Behavior (`testbed run`)

1. Read testbed.toml
2. Ensure supervisord running (for agents config)
3. For each enabled agent:
   - Start via `supervisorctl -c agents.supervisord.conf start <program>`
4. Wait for agents healthy (heartbeat + operational_state=READY)
5. Run workflow via WorkflowRunner
6. On completion: agents remain in READY state (default) or stop with `--stop-agents`
7. Ctrl+C: stop workflow gracefully, agents stay running

### Implementation Order

**Phase 1: Schema & Agent Updates**
1. Add pid, hostname, operational_state to SystemAgent model
2. Run migration
3. Update BaseAgent to populate new fields in heartbeat
4. Update agents to track operational_state (READY ↔ PROCESSING)

**Phase 2: Supervisord Separation**
1. Create agents.supervisord.conf with example agent programs
2. Set autostart=false (orchestrator controls startup)
3. Keep existing supervisord.conf for backend services

**Phase 3: Orchestrator & CLI**
1. Create workflows/orchestrator.py
2. Add `testbed run` command to CLI
3. Implement health check, workflow execution

**Phase 4: MCP Tools**
1. Add supervised agent management tools
2. Add kill_agent with PID lookup

### Files to Modify

| File | Action |
|------|--------|
| `swf-monitor/src/monitor_app/models.py` | Add pid, hostname, operational_state |
| `swf-common-lib/src/swf_common_lib/base_agent.py` | Populate new fields in heartbeat |
| `swf-testbed/agents.supervisord.conf` | CREATE - agent programs |
| `swf-testbed/workflows/orchestrator.py` | CREATE - orchestration logic |
| `swf-testbed/workflows/testbed.toml` | Extend with [workflow], [agents] |
| `swf-testbed/src/swf_testbed_cli/main.py` | Add `run` command, rename to `testbed` |
| `swf-testbed/pyproject.toml` | Rename command to `testbed` |
| `swf-testbed/example_agents/testbed.toml` | DELETE |
| `swf-monitor/src/monitor_app/mcp.py` | Add agent management tools |


## PENDING: STFWorkflow DEPRECATION

STFWorkflow model is unused - WorkflowMessage has all needed fields. UI still references it (dashboard stats, workflow list). Decision: deprecate entirely.
