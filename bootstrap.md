# Bootstrap Guide for Claude

**Date:** 2025-12-31
**Branch:** infra/baseline-v26 (all 3 repos)

## POST-COMPRESS: READ THIS FIRST

After context compression, you lose critical knowledge. Immediately:
1. Re-read this entire file
2. Check `git status` in all 3 repos for uncommitted work
3. Ask user what we were doing if unclear

## Project

ePIC Streaming Workflow Testbed. Agent-based system with ActiveMQ messaging.

**Attention AIs:** This is not a chronicle of completed work. This is quick essential background to current status and next steps.
Be concise and to the point. When something is done and isn't essential background for next steps, remove it.

**Repos** (siblings in /eic/u/wenauseic/github/):
- **swf-testbed** - workflows, example agents
- **swf-monitor** - Django web app, REST API
- **swf-common-lib** - BaseAgent class

**Host:** pandaserver02.sdcc.bnl.gov

## Critical Rules

- **COMMIT BEFORE DEPLOY** - Deploy pulls from git repo, not local files. Always commit and push changes before running deploy script.
- Activate venv before any python
- All 3 repos on same branch (currently v26, shorthand for infra/baseline-v26)
- Redeploy swf-monitor after Django changes: `sudo bash /eic/u/wenauseic/github/swf-monitor/deploy-swf-monitor.sh branch infra/baseline-v26`

## Commands

See [docs/quick-start.md](docs/quick-start.md) for run commands.

---

# SESSION STATUS 2025-12-31

## UNCOMMITTED CHANGES - TEST BEFORE COMMIT

**swf-testbed** has uncommitted changes:
- `example_agents/fast_processing_agent.py` - Fixed to extract run_id/execution_id from each message (agents can start mid-run)
- `workflows/fast_processing_default.toml` - Sampling rate set to 1.0 (100%)
- `docs/quick-start.md` - Added fast processing test commands

**swf-monitor** has uncommitted changes:
- Log summary: Agent/Agent Instance filters
- Namespace list: Uses Namespace model, shows owner/description/modified

Test fast processing with commands from `docs/quick-start.md`, then commit both repos.

## PENDING: STFWorkflow DEPRECATION

STFWorkflow model is unused - WorkflowMessage has all needed fields. UI still references it (dashboard stats, workflow list). Decision: deprecate entirely.

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

