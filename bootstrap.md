# Bootstrap Guide for Claude

**Date:** 2025-12-30
**Branch:** infra/baseline-v26 (all 3 repos)

## Project

ePIC Streaming Workflow Testbed. Agent-based system with ActiveMQ messaging.

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
- Never delete without permission
- FIX problems, don't hide them

## Commands

See [docs/quick-start.md](docs/quick-start.md) for run commands.

---

# SESSION STATUS 2025-12-30

## COMPLETED TODAY

### 1. Sender Link Fix
- **Problem:** sender_agent links in workflow messages list were 404
- **Root cause:** WorkflowRunner wasn't calling `send_heartbeat()` to register in SystemAgent
- **Fix:** `workflows/workflow_runner.py` now calls `send_heartbeat()` after MQ connect
- **Status:** Committed and pushed to all 3 repos

### 2. Namespace/ID Fields Added to Models
- **Purpose:** Namespace is the workflow delineator; execution_id and run_id identify instances within namespace
- **Changes made:**
  - `SystemAgent`: added `namespace` field
  - `STFWorkflow`: added `namespace`, `execution_id`, `run_id` fields
  - `WorkflowMessage`: added `execution_id`, `run_id` fields (namespace already existed)
  - Migration: `0027_add_namespace_execution_run_fields.py`
- **BaseAgent** (swf-common-lib): `send_heartbeat`, `send_enhanced_heartbeat`, `report_agent_status` now include namespace in payload
- **views.py heartbeat endpoint**: accepts namespace from agents
- **activemq_processor**: extracts execution_id, run_id from messages into WorkflowMessage fields
- **Status:** Committed and deployed

### 3. Agent Detail Page Issue - PARTIALLY ADDRESSED
- **Problem:** Agent detail page shows no associated workflows
- **Investigation found:** STFWorkflow model was NEVER populated by any agent code
  - Old `daq_simulator_superseded.py` didn't create them
  - `example_data_agent.py` uses Run/StfFile models via `/runs/` and `/stf-files/` endpoints, NOT STFWorkflow
  - STFWorkflow records in DB are old test data with different filename patterns
- **WorkflowMessage IS being populated** with namespace, execution_id, run_id

---

### 4. activemq_processor.py STFWorkflow Cleanup - COMPLETED
- **File:** `/direct/eic+u/wenauseic/github/swf-monitor/src/monitor_app/activemq_processor.py`
- **Rationale:** STFWorkflow was never wired up; WorkflowMessage carries identity fields directly
- **Changes:**
  1. Removed `STFWorkflow` from import
  2. Changed `workflow=workflow` to `workflow=None` in WorkflowMessage.objects.create()
  3. Removed `_find_related_workflow()` method
- **Status:** Completed, file is clean (181 lines)

---

### 5. agent_detail View Fix - COMPLETED
- **File:** `views.py` (line 1438) and `agent_detail.html` template
- **Change:** Now queries WorkflowMessages by sender_agent instead of STFWorkflow
- **Template:** Shows message activity (timestamp, type, namespace, run_id, status)

---

## REMAINING - STFWorkflow UI CLEANUP

**Next steps:**
- STFWorkflow is used extensively in UI (dashboard stats, workflow list, etc.) - needs cleanup pass
- Consider: deprecate STFWorkflow entirely or wire it up properly

---

## KEY FILES

- `/direct/eic+u/wenauseic/github/swf-monitor/src/monitor_app/activemq_processor.py` - message processor (STFWorkflow cleanup done)
- `/direct/eic+u/wenauseic/github/swf-monitor/src/monitor_app/views.py` - agent_detail fixed (line 1438), STFWorkflow still used elsewhere
- `/direct/eic+u/wenauseic/github/swf-monitor/src/monitor_app/workflow_models.py` - STFWorkflow, WorkflowMessage models
- `/direct/eic+u/wenauseic/github/swf-monitor/src/monitor_app/models.py` - SystemAgent, Run, StfFile models
- `/direct/eic+u/wenauseic/github/swf-common-lib/src/swf_common_lib/base_agent.py` - BaseAgent with namespace support

---

## STFWorkflow USAGE IN CODEBASE

All in swf-monitor, grep for `STFWorkflow`:
- `views.py`: Dashboard stats, workflow list/detail, agent_detail - ALL UI CODE
- `api_urls.py`: `/api/workflows/` endpoint
- `serializers.py`: STFWorkflowSerializer
- `activemq_processor.py`: STFWorkflow references REMOVED

**Decision needed:** Either deprecate STFWorkflow entirely (use WorkflowMessage for grouping), or wire it up properly. Current path is deprecation since WorkflowMessage has all needed fields.

---

## SESSION WORK IN PROGRESS (UNCOMMITTED in swf-monitor)

### Message Detail View - COMPLETED
- Added `message_detail` view, URL (`/workflow/messages/<uuid>/`), template
- Timestamps in agent_detail and workflow_messages list link to message detail
- Message detail shows all model fields + flattened JSON content/metadata tables

### execution_id Filter - COMPLETED
- Added execution_id to workflow_messages filter dropdowns
- Updated view, datatable ajax, filter counts

### Workflow Execution Detail - COMPLETED
- Added "Messages: View Messages" link to execution detail page

### Workflow Executions List - COMPLETED
- Added "STFs" column showing count of stf_gen messages per execution

**Needs commit and push to swf-monitor, then deploy.**

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

[parameters]
# Optional workflow parameter overrides
# physics_period_count = 2
# stf_interval = 5.0
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
