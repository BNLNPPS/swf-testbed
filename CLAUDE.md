# CLAUDE.md

## Essential Commands

```bash
# Environment (required before any Python command)
cd /data/wenauseic/github/swf-testbed && source .venv/bin/activate && source ~/.env

# Run workflows
testbed run                     # Uses workflows/testbed.toml
testbed run fast_processing     # Uses workflows/fast_processing_default.toml

# Check status
testbed status-local            # System services + agents
```

```python
# MCP tools (preferred over CLI for AI operations)
swf_get_testbed_status(username)          # Comprehensive status
swf_start_user_testbed(username)          # Start testbed
swf_stop_user_testbed(username)           # Stop testbed
swf_start_workflow()                      # Start workflow
swf_stop_workflow(execution_id)           # Stop workflow
swf_list_logs(level='ERROR')              # Find failures
swf_list_logs(execution_id='...')         # Workflow logs
```

## Project-Specific Rules

**Branch:** All 3 repos must be on `infra/baseline-v34`

**First push:** `git push -u origin branch-name` sets up tracking.

**ActiveMQ destinations:** Must have prefix — use `'/topic/epictopic'` not `'epictopic'`.

**MCP tool changes:** When adding/modifying MCP tools, update: (1) `swf_list_available_tools()` hardcoded list in mcp.py, (2) server instructions in settings.py, (3) docs/MCP.md.

## Gotchas

| Wrong | Right |
|-------|-------|
| `nohup python agent.py &` | `testbed run` |
| `tail -f logs/file.log` | `swf_list_logs()` via MCP |
| `swf_list_logs()` (no filter) | `swf_list_logs(level='ERROR')` or `swf_list_logs(execution_id='...')` |
| Relative paths `../swf-monitor` | Absolute `/data/wenauseic/github/swf-monitor` |

**MCP query limits:** Always filter queries. Unbounded `swf_list_agents(status='all')` or `swf_list_logs()` can exceed context limits.

Docs: See `README.md`, `docs/` in each repo, and [MCP.md](../swf-monitor/docs/MCP.md) for tool reference.
