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

- Activate venv before any python
- All 3 repos on same branch (currently v26, shorthand for infra/baseline-v26)
- Redeploy swf-monitor after Django changes: `sudo bash /eic/u/wenauseic/github/swf-monitor/deploy-swf-monitor.sh branch infra/baseline-v26`
- Never delete without permission, never take action on the code base without careful thinking on correctness and consequences of the change, and get approval
- FIX problems, don't hide them. No silent failures, no toleration of unexpected/illogical states.

# Current work and next tasks

## Namespace Feature (IMPLEMENTED)

Messages include `sender` and `namespace` fields. Agents filter by namespace.

Config: `testbed.toml` with `[testbed]` section, `namespace = ""` (must set before running)

## Sender Link Fix - IN PROGRESS

**Problem:** In workflow messages list, sender_agent links were broken (404).
- Root cause: WorkflowRunner wasn't calling `send_heartbeat()` to register in SystemAgent table

**Fixed (2025-12-30):** `workflows/workflow_runner.py` now calls `send_heartbeat()` after MQ connection (uncommitted)

**Next steps:**
1. Run a workflow to create valid SystemAgent data
2. Revert the sender link removal in swf-monitor views.py (the "hide the problem" fix)
3. Commit changes

## Uncommitted Changes

**swf-testbed:** WorkflowRunner now calls `send_heartbeat()` after MQ connect - registers agent properly

**swf-monitor:** recipient_agent column removal + broken sender link "fix" - REVERT the sender link removal, keep recipient_agent removal

**swf-common-lib:** retry logic for initial connection (3 attempts, 5 sec delay) - OK to keep

## Commands

```bash
# Simulator (creates SystemAgent data via send_heartbeat)
cd /eic/u/wenauseic/github/swf-testbed/workflows && source ../.venv/bin/activate && source ~/.env && python workflow_simulator.py stf_datataking --workflow-config fast_processing_default --duration 120 --realtime

# Processing agent
cd /eic/u/wenauseic/github/swf-testbed/example_agents && source ../.venv/bin/activate && source ~/.env && python example_processing_agent.py
```
