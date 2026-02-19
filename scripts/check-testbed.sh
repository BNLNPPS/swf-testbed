#!/bin/bash
# check-testbed.sh - Bootstrap and verify testbed infrastructure
# Ensures agent manager and supervisord are healthy.
# Starts agent manager if not running.
# Reports all problems loudly.

set -euo pipefail

TESTBED_DIR="/data/wenauseic/github/swf-testbed"
AGENTS_CONF="agents.supervisord.conf"
VENV="$TESTBED_DIR/.venv/bin"
SUPERVISORCTL="$VENV/supervisorctl"
STATUS=0

echo "=== Testbed Infrastructure Check ==="
echo ""

# --- Agent Manager ---
echo "--- Agent Manager ---"
AM_PID=$(pgrep -f "testbed agent-manager" -u "$(whoami)" 2>/dev/null || true)

if [ -n "$AM_PID" ]; then
    echo "RUNNING (PID $AM_PID)"
else
    echo "NOT RUNNING - starting..."
    cd "$TESTBED_DIR"
    source "$VENV/activate"
    source ~/.env 2>/dev/null || true
    nohup testbed agent-manager > /tmp/agent-manager.log 2>&1 &

    STARTED=false
    for i in $(seq 1 6); do
        sleep 5
        AM_PID=$(pgrep -f "testbed agent-manager" -u "$(whoami)" 2>/dev/null || true)
        if [ -n "$AM_PID" ]; then
            echo "STARTED (PID $AM_PID) after ${i}0s"
            STARTED=true
            break
        fi
        echo "  ...waiting (${i}0s elapsed)"
        tail -3 /tmp/agent-manager.log 2>/dev/null || true
    done

    if [ "$STARTED" = false ]; then
        echo "ERROR: Agent manager failed to start after 30s"
        echo "Log output:"
        tail -20 /tmp/agent-manager.log 2>/dev/null || echo "(no log)"
        STATUS=1
    fi
fi

echo ""

# --- Supervisord ---
echo "--- Supervisord ---"
SV_OUTPUT=$("$SUPERVISORCTL" -c "$TESTBED_DIR/$AGENTS_CONF" status 2>&1) || true

if echo "$SV_OUTPUT" | grep -q "no such file"; then
    SV_EXIT=4
elif echo "$SV_OUTPUT" | grep -q "refused"; then
    SV_EXIT=4
else
    # Check for actual running/stopped agents
    SV_EXIT=0
fi

if [ "$SV_EXIT" -eq 0 ]; then
    echo "REACHABLE"
    echo "$SV_OUTPUT"
elif [ "$SV_EXIT" -eq 4 ]; then
    STALE_PID=$(pgrep -f "supervisord.*$AGENTS_CONF" -u "$(whoami)" 2>/dev/null || true)
    if [ -n "$STALE_PID" ]; then
        echo "Stale process found (PID $STALE_PID) - killing..."
        kill "$STALE_PID" 2>/dev/null || true
        sleep 2
        if kill -0 "$STALE_PID" 2>/dev/null; then
            echo "SIGTERM didn't work, sending SIGKILL..."
            kill -9 "$STALE_PID" 2>/dev/null || true
            sleep 1
        fi
        if kill -0 "$STALE_PID" 2>/dev/null; then
            echo "ERROR: Failed to kill stale supervisord (PID $STALE_PID)"
            STATUS=1
        else
            echo "Killed. Supervisord will be started fresh when testbed starts."
        fi
    else
        echo "NOT RUNNING (normal when testbed is stopped)"
    fi
fi

echo ""

# --- Refresh heartbeat ---
# After any fixes, signal agent manager to send immediate heartbeat
# so MCP status reflects the current verified state.
AM_PID=$(pgrep -f "testbed agent-manager" -u "$(whoami)" 2>/dev/null || true)
if [ -n "$AM_PID" ] && [ "$STATUS" -eq 0 ]; then
    kill -USR1 "$AM_PID" 2>/dev/null || true
    sleep 2
fi

# --- Summary ---
echo "--- Summary ---"
if [ "$STATUS" -eq 0 ]; then
    echo "Infrastructure OK. Ready for MCP operations."
else
    echo "PROBLEMS DETECTED. Fix issues above before proceeding."
fi

exit $STATUS
