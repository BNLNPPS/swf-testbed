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


# SESSION 2026-01-13

## Tested - Message-Driven Workflow WORKS

- MCP `start_workflow` → WorkflowRunner receives on `/queue/workflow_control` → executes → broadcasts to `/topic/epictopic`
- Execution: `stf_datataking-wenauseic-0044`, run 101988, 3 STF files

## Critical Fix: ActiveMQ Destination Naming

BaseAgent now validates destinations must have `/queue/` or `/topic/` prefix. Bare names rejected.

## Uncommitted Changes

**swf-testbed:**
- `CLAUDE.md` - STOP/NEVER sections for AI guidance, updated MCP diagnostic examples
- `workflows/README.md` - New, repeated guidance
- `workflows/stf_datataking.py` - Fixed `/topic/epictopic`
- `workflows/stf_datataking_default.toml` - New default config
- `workflows/workflow_runner.py` - Removed _send_response(), logging with extra={execution_id}, fixed status='failed'

**swf-monitor:**
- `mcp.py` - Updated docstrings, start_workflow monitoring, list_logs(execution_id) filter
- `settings.py` - MCP instructions: added "AFTER start_workflow" section

**swf-common-lib:**
- `base_agent.py` - Destination prefix validation (pushed)
- `rest_logging.py` - Capture execution_id/workflow_name/run_id in extra_data

## TODO

1. Commit uncommitted changes above
2. Test stop functionality
3. Redeploy monitor after commits

