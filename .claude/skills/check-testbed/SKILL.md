---
name: check-testbed
description: Bootstrap and check testbed infrastructure. Ensures agent manager and supervisord are healthy, then reports full status. Run before any testbed operation.
user-invocable: true
---

# Check Testbed Infrastructure

This skill ensures the testbed infrastructure is ready for MCP operations.
After this skill succeeds, MCP tools (swf_start_user_testbed, swf_stop_user_testbed,
swf_start_workflow, etc.) will work reliably.

## Step 1: Check agent manager process locally

Run this bash command to check if the agent manager is running:

```bash
pgrep -f "user_agent_manager" -u $(whoami)
```

- If a PID is returned: agent manager is running. Note the PID. Proceed to Step 2.
- If no PID: agent manager is NOT running. Go to Step 1b.

## Step 1b: Start the agent manager

Start it locally in the background:

```bash
cd /data/wenauseic/github/swf-testbed && source .venv/bin/activate && source ~/.env && nohup testbed agent-manager > /tmp/agent-manager.log 2>&1 &
```

Then wait up to 30 seconds, polling every 5 seconds with `swf_check_agent_manager(username='wenauseic')` until `alive: true` is returned.

If it does not come alive within 30 seconds:
- Check /tmp/agent-manager.log for errors
- Report the failure and STOP. Do not proceed.

## Step 2: Verify supervisord is reachable

Run this bash command:

```bash
cd /data/wenauseic/github/swf-testbed && source .venv/bin/activate && supervisorctl -c agents.supervisord.conf status
```

Check the exit code and output:
- Exit code 0 or 3: supervisord is running and reachable. Report the agent statuses shown.
- Exit code 4: supervisord is NOT reachable (socket missing or process dead).

If exit code 4, check for a stale supervisord process:

```bash
pgrep -f "supervisord.*agents.supervisord.conf" -u $(whoami)
```

- If stale PID found: report it. Tell the user: "Stale supervisord process (PID XXXX) found. Socket is missing. Need to kill it and restart. Kill it?" Wait for approval before killing.
- If no PID: supervisord is simply not running. This is normal — it will be started when testbed is started via MCP. Report this as OK.

## Step 3: Get full status via MCP

Call `swf_get_testbed_status(username='wenauseic')` and report:
- Agent manager: alive/dead, namespace, operational state
- Agents: list with running/stopped status
- Summary: running count, stopped count

## Step 4: Check for recent errors

Call `swf_list_logs(level='ERROR', start_time='<1 hour ago in ISO format>')` and report any errors found. If none, report "No errors in the last hour."

## Final Report

Summarize:
- Agent manager: running (PID) / just started / FAILED
- Supervisord: reachable / not running (normal) / STALE (needs attention)
- Agents: N running, M stopped
- Recent errors: count and brief summary
- Ready for operations: YES / NO (with reason)

If everything is healthy, state: "Infrastructure is ready. Use swf_start_user_testbed() to start the testbed, or swf_start_workflow() if agents are already running."
