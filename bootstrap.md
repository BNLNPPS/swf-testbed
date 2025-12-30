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
