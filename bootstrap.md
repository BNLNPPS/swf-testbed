# Bootstrap Guide for Claude

**Date:** 2026-01-09
**Branch:** infra/baseline-v28 (all 3 repos)

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
- All 3 repos on same branch (currently v28, shorthand for infra/baseline-v28)
- Redeploy swf-monitor after Django changes: `sudo bash /data/wenauseic/github/swf-monitor/deploy-swf-monitor.sh branch infra/baseline-v28`

## Commands

See [docs/quick-start.md](docs/quick-start.md) for run commands.


# CURRENT STATUS 2026-01-09

## Phase 2: WorkflowRunner as Persistent Agent - COMPLETE

WorkflowRunner operates in two modes:
- **Persistent mode** (default): Listens on `workflow_control` queue for commands
- **CLI mode** (`--run-once`): Runs single workflow and exits

**Message handlers:** `run_workflow`, `stop_workflow`, `status_request`

## MCP Workflow Tools - COMPLETE

| Tool | Description |
|------|-------------|
| `start_workflow` | Send run command to DAQ Simulator agent |
| `stop_workflow` | Send stop command by execution_id |
| `end_execution` | Mark execution terminated in DB (no agent message) |
| `kill_agent` | SIGKILL agent process by name |
| `list_workflow_executions` | Query executions (use `currently_running=True`) |

**start_workflow params:** workflow_name, namespace, config, realtime, duration, stf_count, physics_period_count, physics_period_duration, stf_interval

## CLI Utility

```bash
# Send commands to persistent WorkflowRunner
python workflows/send_workflow_command.py run --workflow stf_datataking --stf-count 2 --no-realtime
python workflows/send_workflow_command.py stop --execution-id <exec_id>
python workflows/send_workflow_command.py status
```

---

## FIRST: Clean Up Stale Agents

```
mcp: list_agents(agent_type='workflow_runner')
mcp: kill_agent(name='workflow_runner-agent-wenauseic-XXX')  # for each stale agent
```

---

## NEEDS TESTING

1. **Full message-driven flow:**
   - Start persistent agent: `python workflows/workflow_runner.py`
   - Send run_workflow via MCP or CLI
   - Verify agent executes workflow

2. **Stop functionality:**
   - Start long workflow (realtime mode)
   - Send stop_workflow with execution_id
   - Verify graceful stop at checkpoint

---

## NEXT STEPS

### Phase 4: Supervisord & Orchestrator
- Create agents.supervisord.conf
- Create workflows/orchestrator.py
- Add `testbed run` CLI command

---

## Key Architecture

### WorkflowRunner Threading Model
```
Main thread: BaseAgent.run() loop
  └── sleep(60), send_heartbeat()

STOMP receiver thread: on_message()
  └── _handle_run_workflow() starts workflow_thread
  └── _handle_stop_workflow() sets stop_event (checks execution_id)
  └── Returns immediately, agent stays responsive

Workflow thread: _run_workflow_thread()
  └── run_workflow() → _execute_workflow()
  └── SimPy loop with _on_simulation_step() callback
  └── Checks stop_event between simulation events
```

---

## REFERENCE: Agent States

**operational_state** (what agent is doing):
- `STARTING` - process coming up
- `READY` - connected to MQ, waiting for work
- `PROCESSING` - actively doing work
- `EXITED` - process terminated

---

## REFERENCE: MCP Tools

| Category | Tools |
|----------|-------|
| System | `get_system_state`, `list_agents`, `get_agent`, `list_namespaces`, `get_namespace` |
| Workflows | `list_workflow_definitions`, `list_workflow_executions`, `get_workflow_execution` |
| Actions | `start_workflow`, `stop_workflow`, `end_execution`, `kill_agent` |
| Data | `list_runs`, `get_run`, `list_stf_files`, `get_stf_file`, `list_tf_slices`, `get_tf_slice` |
| Messages | `list_messages` |
| Logs | `list_logs`, `get_log_entry` |

**Endpoint:** `https://pandaserver02.sdcc.bnl.gov/swf-monitor/mcp/`
