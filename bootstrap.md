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

## User Agent Manager - JUST IMPLEMENTED

Per-user daemon for MCP-controlled testbed management.

**swf-testbed:**
- `src/swf_testbed_cli/user_agent_manager.py` - UserAgentManager class
  - Listens on `/queue/agent_control.<username>` for MCP commands
  - Commands: start_testbed, stop_testbed, status, ping
  - Sends heartbeats to monitor API
- `src/swf_testbed_cli/main.py` - Added `testbed agent-manager` CLI command

**swf-monitor MCP tools:**
- `check_agent_manager(username)` - Check if user's agent manager is alive
- `start_user_testbed(username, config)` - Start testbed via agent manager
- `stop_user_testbed(username)` - Stop testbed via agent manager

**Also committed:**
- Agent detail page: added logs link
- BaseAgent: `_log_extra()` helper with username/execution_id/run_id
- rest_logging.py: captures username field

## TODO

1. Redeploy monitor: `sudo bash /data/wenauseic/github/swf-monitor/deploy-swf-monitor.sh branch infra/baseline-v28`
2. Test agent manager: `testbed agent-manager` then use MCP tools
3. Test full flow: agent manager → start_user_testbed → start_workflow

