# Release Notes

## v28 (2026-01-13)

### ActiveMQ Destination Prefix Requirement (Breaking Change)

**All ActiveMQ destinations now require explicit `/queue/` or `/topic/` prefix.** This is a breaking change that affects all agent code sending messages.

**Before (incorrect):**
```python
self.send_message('epictopic', message)  # WRONG - bare name
```

**After (correct):**
```python
self.send_message('/topic/epictopic', message)  # Correct - explicit prefix
```

**Why this matters:**
- Bare destination names were ambiguous - ActiveMQ behavior depends on broker configuration
- Explicit prefixes make the routing intention clear: `/queue/` for anycast (one consumer) vs `/topic/` for multicast (all consumers)
- BaseAgent now validates destination format and raises `ValueError` for bare names

Existing code using bare names will fail immediately with a clear error message explaining the required format. All example agents and workflow code have been updated.

### MCP Workflow Control - AI-Driven Operations

The MCP service now provides **full workflow control**, enabling AI assistants to start, stop, and monitor workflows without requiring CLI access. This is the key enabler for AI-driven testbed operations.

**New workflow control tools:**
- `start_workflow` - Start a workflow by sending a command to the DAQ Simulator agent. All parameters are optional; defaults are read from the user's `testbed.toml`. Override specific parameters (e.g., `stf_count=5`) while inheriting others from config.
- `stop_workflow` - Stop a running workflow gracefully by execution_id. The workflow stops at the next checkpoint.
- `end_execution` - Mark a stuck execution as terminated in the database. Use this to clean up stale executions that the agent can no longer reach.

**New agent management tools:**
- `kill_agent` - Send SIGKILL to an agent process by instance name. Looks up the agent's PID and hostname, kills if on the same host, and always marks the agent as EXITED in the database.

**New monitoring tools:**
- `get_workflow_monitor` - Aggregated view of workflow execution: status, phase, STF count, key events, and errors (from both messages and logs). Single-call alternative to polling multiple tools.
- `list_workflow_monitors` - List recent executions (last 24h) that can be monitored.

The MCP tool count has grown from 20 to **27 tools**. Documentation in `swf-monitor/docs/MCP.md` has been updated to reflect all tools.

### User Agent Manager - Per-User Testbed Control via MCP

A new **agent manager daemon** enables MCP-driven control of per-user testbed agents. This allows AI assistants to start and stop a user's testbed without requiring SSH or terminal access.

**Architecture:**
- Each user runs a lightweight `testbed agent-manager` daemon in their swf-testbed directory
- The daemon listens on a user-specific queue (`/queue/agent_control.<username>`) for commands
- It manages supervisord-controlled agents and reports status via heartbeats

**New MCP tools:**
- `check_agent_manager(username)` - Check if a user's agent manager is alive. Returns heartbeat status, control queue name, and whether agents are running.
- `start_user_testbed(username, config_name)` - Send start command to agent manager. Agents start asynchronously.
- `stop_user_testbed(username)` - Send stop command to agent manager.

**Usage:**
```bash
# Start the agent manager daemon (run once, keeps running)
cd /data/<username>/github/swf-testbed
source .venv/bin/activate && source ~/.env
testbed agent-manager
```

Then an AI assistant can:
1. Check readiness: `check_agent_manager(username='wenauseic')`
2. Start testbed: `start_user_testbed(username='wenauseic')`
3. Run workflows: `start_workflow()`
4. Stop when done: `stop_user_testbed(username='wenauseic')`

### Persistent WorkflowRunner with Message-Driven Execution

The WorkflowRunner agent has been redesigned as a **persistent, message-driven service** rather than a one-shot script.

**Key changes:**
- WorkflowRunner now starts with supervisord and listens on `/queue/workflow_control` for commands
- Commands include `run_workflow` (from MCP `start_workflow`) and `stop_workflow`
- Each execution gets a unique `execution_id` (e.g., `stf_datataking-wenauseic-0044`)
- The `stop_workflow` command targets a specific execution by ID, enabling graceful termination

**Why this matters:**
- The WorkflowRunner is always ready to receive workflow commands - it doesn't need to be started for each run
- This models the actual ePIC system more realistically, where the DAQ system is a persistent service
- Workflows can be started and stopped via MCP without CLI access
- Multiple workflows can be managed by execution_id

### Enhanced get_system_state - User Context and Readiness

The `get_system_state` MCP tool now accepts a `username` parameter and provides user-specific context.

**New fields returned:**
- `user_context` - Namespace and workflow defaults from user's `testbed.toml`
- `agent_manager` - Status of user's agent manager daemon (healthy/unhealthy/missing/exited)
- `workflow_runner` - Status of DAQ Simulator in user's namespace
- `ready_to_run` - Boolean indicating if the user can start a workflow
- `last_execution` - Most recent workflow execution in user's namespace
- `errors_last_hour` - Count of ERROR logs in user's namespace

This enables AI assistants to answer questions like "Am I ready to run a workflow?" with a single call.

### EXITED Status and Agent Lifecycle

Improved agent lifecycle management with explicit EXITED status handling.

**Changes:**
- Agents now set `status='EXITED'` and `operational_state='EXITED'` on clean shutdown
- `list_agents` **excludes EXITED agents by default** - use `status='EXITED'` to see only exited, or `status='all'` to see all
- `kill_agent` always marks agents as EXITED, even if the kill fails
- EXITED agents don't clutter the active agent list but remain queryable for debugging

**Migration:** A database migration (`0014_systemagent_exited_status.py`) adds the EXITED choice to the status field.

### Logging Context with execution_id

Improved log traceability with execution context in log records.

**Changes:**
- New `_log_extra()` helper in BaseAgent returns consistent extra fields: `username`, `execution_id`, `run_id`
- All agent log calls should use: `logger.info("message", extra=self._log_extra())`
- `list_logs` MCP tool now supports `execution_id` parameter to filter logs by workflow execution

**Usage:**
```python
# In agent code
self.logger.info("Processing STF", extra=self._log_extra())

# Via MCP
list_logs(execution_id='stf_datataking-wenauseic-0044')
```

This enables tracing all log messages for a specific workflow execution, essential for debugging workflow failures.

### Monitor UI Improvements

**Log detail page:** The log detail view (`/logs/<id>/`) now displays the `extra_data` JSON field when present. This shows execution context (execution_id, run_id, namespace, username) that agents include via `_log_extra()`. Previously this context was captured but not visible in the UI.

**Log list filtering:** The log list now supports filtering by execution_id, complementing the existing app_name, instance_name, and level filters.

### Documentation Updates

- **MCP.md** completely rewritten to document all 27 tools with accurate parameters and return values
- Removed "Not Yet Implemented" section - all documented tools are now functional
- Added sections for Workflow Control, Agent Management, User Agent Manager, and Workflow Monitoring
- Updated tool count from 20 to 27

---

## v27 (2026-01-08)

### MCP Integration

The swf-monitor now exposes a **Model Context Protocol (MCP)** API, enabling AI assistants like Claude to query and interact with the testbed system.

**20+ MCP tools** for:
- **System state**: `get_system_state`, `list_agents`, `get_agent`, `list_namespaces`
- **Workflows**: `list_workflow_definitions`, `list_workflow_executions`, `get_workflow_execution`
- **Data**: `list_runs`, `get_run`, `list_stf_files`, `get_stf_file`, `list_tf_slices`
- **Messages & Logs**: `list_messages`, `list_logs`, `get_log_entry`

**Auto-discovery**: Add `.mcp.json` to your project root for Claude Code to automatically connect:
```json
{
  "mcpServers": {
    "swf-testbed": {
      "type": "sse",
      "url": "https://pandaserver02.sdcc.bnl.gov/swf-monitor/mcp/"
    }
  }
}
```

**Endpoint**: `https://pandaserver02.sdcc.bnl.gov/swf-monitor/mcp/`

### Agent Lifecycle Management

Agents now report process information for lifecycle management:
- **pid**: Process ID for kill operations
- **hostname**: Host where agent is running
- **operational_state**: STARTING → READY → PROCESSING → EXITED

These fields enable future orchestration features like agent health monitoring and remote termination.

### Database Logging

New `DbLogHandler` sends Python log records to the monitor database, enabling centralized log viewing:
- View logs via monitor UI at `/logs/`
- Filter by app, instance, level, time range
- Query via MCP: `list_logs(level='ERROR')`, `get_log_entry(log_id)`

### BaseAgent Improvements

- Agents report EXITED status on shutdown
- Warning logged when sending messages without namespace set
- Heartbeats include pid, hostname, operational_state

---

## v26 (2025-12-31)

### Namespaces

Workflows now operate within **namespaces**, allowing users to isolate their work from others sharing the same infrastructure.

On shared systems like pandaserver02, multiple users can run workflows simultaneously. Namespaces let you filter the monitor UI to see only your workflows, agents, and messages, and avoid conflicts with other users.

Configure your namespace in `workflows/testbed.toml` before running any workflows:

```toml
[testbed]
namespace = "your-namespace"  # e.g., "alice-dev", "team-fastmon"
```

All workflow messages now include the namespace, and the monitor UI provides namespace filtering on agents, executions, and messages.

### Monitor UI

- **Namespace pages**: List and detail views; namespace column and filter on agents, executions, messages
- **Agent list**: Type and status filters; click agent to see detail
- **Agent detail**: Streamlined view linking to filtered workflow messages
- **Workflow messages**: execution_id and run_id filters; STF count column; click for message detail
- **Message detail**: Full message content view
- **Drill-down links**: Click execution_id, run_id, namespace, or agent anywhere to navigate to details
- **Source links**: GitHub links on workflow definition (branch) and execution (commit) pages

### Workflow Refinements

**Count-based workflow completion:** Workflows can now run until a specific number of STF files are generated, rather than requiring a duration limit:

```bash
python workflows/workflow_simulator.py stf_datataking \
    --workflow-config fast_processing_default \
    --stf-count 10
```

**Immutable definitions:** Workflow definitions are now immutable once created. The definition captures the source code and configuration at creation time. Each execution records its specific git version for reproducibility.

**Source traceability:** Workflow definitions now link to their source script on GitHub. Executions record the exact git commit, so you can always trace back to the code that ran.

### Fast Processing Support

New infrastructure for fast processing workflows that sample STF data for near real-time monitoring:

- **Fast processing agent** (`example_agents/fast_processing_agent.py`) creates TF slices from STF samples
- Configurable sampling rate, slices per sample, and processing time
- Agents can start mid-run and extract context from messages
- New monitor views: TF Slices (`/tf-slices/`) and Run States (`/run-states/`)

### Agent Improvements

- Agents now register using the workflow name as their type (e.g., `STF_Datataking` instead of generic `workflow_runner`)
- Retry logic for initial ActiveMQ connection improves reliability on startup
- Agent list in monitor now supports type and status filters

### Infrastructure

- Docker-compose updated with Redis and health checks
- Artemis queue configuration guide added (`docs/artemis-queue-configuration.md`)
- Fixed environment loading that was breaking git commands when `~/.env` contained PATH references

---

*For detailed technical changes, see the pull requests for [swf-testbed](https://github.com/BNLNPPS/swf-testbed/pulls), [swf-common-lib](https://github.com/BNLNPPS/swf-common-lib/pulls), and [swf-monitor](https://github.com/BNLNPPS/swf-monitor/pulls).*
