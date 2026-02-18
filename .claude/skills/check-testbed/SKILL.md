---
name: check-testbed
description: Bootstrap and check testbed infrastructure. Ensures agent manager and supervisord are healthy. Run before any testbed operation.
user-invocable: true
---

# Check Testbed Infrastructure

Local infrastructure check:
!`/data/wenauseic/github/swf-testbed/scripts/check-testbed.sh 2>&1`

## After script completes

If the script reports "Infrastructure OK", call `swf_get_testbed_status(username='wenauseic')` and report the full status to the user.

If the script reports "PROBLEMS DETECTED", report the problems. Do not call MCP.
