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


# SESSION STATUS 2026-01-09

## Uncommitted Changes - NEEDS TESTING

### Phase 2: WorkflowRunner as Persistent Agent - IMPLEMENTED

**Files changed:**
- `swf-testbed/workflows/workflow_runner.py` - Major changes
- `swf-testbed/pyproject.toml` - Added simpy dependency
- `swf-common-lib/base_agent.py` - run() skips connect if already connected
- `swf-testbed/workflows/send_workflow_command.py` - NEW utility for sending commands

**WorkflowRunner changes:**
1. **on_message()** - Handles `run_workflow`, `stop_workflow`, `status_request`
2. **Threaded execution** - Workflows run in background thread, agent stays responsive
3. **Stop support** - `stop_event` flag checked via `_on_simulation_step()` callback
4. **CLI modes**:
   - Default: Persistent agent mode, listens on `workflow_control` queue
   - `--run-once WORKFLOW`: CLI mode, runs single workflow and exits

**CLI mode tested and working:**
```bash
source .venv/bin/activate && source ~/.env
python workflows/workflow_runner.py --run-once stf_datataking --workflow-config fast_processing_default --stf-count 2 --no-realtime
# Works: PROCESSING → runs workflow → READY
```

**Persistent mode starts correctly:**
```bash
python workflows/workflow_runner.py
# Registers as daq_simulator-agent-*, subscribes to workflow_control, state READY
```

### NEEDS TESTING: Message-Driven Workflow Execution

The command sender (`send_workflow_command.py`) has STOMP connection issues.
We have working message senders elsewhere (WorkflowExecutor uses `runner.send_message()`).
Fix should be simple - use same connection pattern as existing senders.

**Test scenario:**
1. Start agent: `python workflows/workflow_runner.py`
2. Send command to `workflow_control` queue with `msg_type: run_workflow`
3. Agent should receive message and start workflow in background thread

---

## NEXT STEPS

### 1. Fix send_workflow_command.py Connection
Use same pattern as WorkflowExecutor/BaseAgent for STOMP connection. The connection code exists and works - just need to use it consistently.

### 2. Test Stop Functionality
- Start long workflow (realtime mode)
- Send stop_workflow command
- Verify `_on_simulation_step()` returns False and workflow exits early

### 3. Phase 3: MCP Workflow Tools
Add to mcp.py:
- `run_workflow(workflow_name, config, params)` - Send command to DAQ simulator
- `stop_workflow(execution_id)` - Send stop command
- `get_simulator_status()` - Return DAQ simulator state

### 4. Phase 4: Supervisord & Orchestrator
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
  └── _handle_stop_workflow() sets stop_event
  └── Returns immediately, agent stays responsive

Workflow thread: _run_workflow_thread()
  └── run_workflow() → _execute_workflow()
  └── SimPy loop with _on_simulation_step() callback
  └── Checks stop_event between simulation events
```

### Stop Mechanism
```python
# _on_simulation_step() called between SimPy events
def _on_simulation_step(self, env, execution_id) -> bool:
    if self.stop_event.is_set():
        return False  # Stop simulation
    return True  # Continue
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
| Workflows | `list_workflow_definitions`, `list_workflow_executions`, `get_workflow_execution`, `end_execution` |
| Data | `list_runs`, `get_run`, `list_stf_files`, `get_stf_file`, `list_tf_slices`, `get_tf_slice` |
| Messages | `list_messages` |
| Logs | `list_logs`, `get_log_entry` |
| Actions | `start_workflow` (stub), `end_execution` |

**Endpoint:** `https://pandaserver02.sdcc.bnl.gov/swf-monitor/mcp/`
