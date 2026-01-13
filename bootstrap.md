# Bootstrap Guide for Claude

**Date:** 2026-01-13
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

## Current Status

### MCP start_workflow() defaults

`start_workflow()` now reads defaults from `workflows/testbed.toml`:
- `[testbed].namespace` - default namespace
- `[workflow].name/config/realtime` - workflow defaults
- `[parameters]` section - passes through ALL params without hardcoding

Call `start_workflow()` with no args to use configured defaults.

### User Agent Manager

Per-user daemon: `testbed agent-manager`
- Listens on `/queue/agent_control.<username>`
- Fixed: SSL support, API auth (like BaseAgent)
- MCP tools: check_agent_manager, start_user_testbed, stop_user_testbed
