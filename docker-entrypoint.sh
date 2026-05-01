#!/bin/bash
set -e

# ---- Environment variables required by agents.supervisord.conf ----
# %(ENV_SWF_HOME)s/swf-testbed  →  /opt/swf-testbed  →  /app  (via symlink)
export SWF_HOME=/opt
# %(ENV_USER)s — used for the supervisord socket path
export USER=${USER:-root}
# %(ENV_SWF_TESTBED_CONFIG)s — config path passed to agents
export SWF_TESTBED_CONFIG=${SWF_TESTBED_CONFIG:-workflows/testbed.toml}
# Skip venv activation in workflow_runner.py and agent scripts
export VIRTUAL_ENV=${VIRTUAL_ENV:-/usr/local}

# PostgreSQL and ActiveMQ readiness is guaranteed by docker-compose healthchecks
# (depends_on with condition: service_healthy), so no wait loops needed here.

echo "==> Running database migrations …"
python /opt/swf-monitor/src/manage.py migrate --noinput

echo "==> Generating API token for agents …"
# get_token outputs: '... token for user "admin": <hex>'  — extract the 40-char hex token
SWF_API_TOKEN=$(python /opt/swf-monitor/src/manage.py get_token admin 2>/dev/null | grep -oP '[0-9a-f]{40}')
export SWF_API_TOKEN
echo "==> API token ready"

echo "==> Starting: $@"
"$@"
CMD_EXIT=$?

if [ $CMD_EXIT -ne 0 ]; then
    echo "==> Command failed with exit code $CMD_EXIT"
    exit $CMD_EXIT
fi

# Keep the container alive so supervisord-managed agents can keep running.
# testbed run triggers the workflow and exits, but the agents (workflow-runner,
# processing-agent, etc.) are background processes under supervisord.
AGENTS_PID_FILE=/app/agents-supervisord.pid
if [ -f "$AGENTS_PID_FILE" ]; then
    SUPD_PID=$(cat "$AGENTS_PID_FILE")
    echo "==> Agents running under supervisord (pid $SUPD_PID). Tailing logs …"
    # Forward SIGTERM/SIGINT to supervisord so 'docker stop' shuts down cleanly
    trap "echo '==> Shutting down supervisord …'; kill -TERM $SUPD_PID; wait $SUPD_PID 2>/dev/null; exit 0" TERM INT
    # Tail agent logs to keep the container alive and stream output
    tail -F /app/logs/*.log 2>/dev/null &
    TAIL_PID=$!
    # Wait until supervisord exits
    while kill -0 "$SUPD_PID" 2>/dev/null; do
        sleep 2
    done
    kill $TAIL_PID 2>/dev/null
    echo "==> Supervisord exited."
else
    echo "==> No supervisord pid file found. Exiting."
fi
