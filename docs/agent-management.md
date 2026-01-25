# Agent Management

This document describes how workflow agents are started, stopped, and managed in the ePIC Streaming Workflow Testbed.

## Overview

Agents are managed through two control paths:
- **CLI** (`testbed` command) - for local operation
- **MCP** (Model Context Protocol) - for AI-assisted remote operation

Both paths use supervisord for process management, ensuring consistent behavior.

![Agent Management Overview](images/agent-management-overview-v4.svg)

## CLI Control Path

### Starting Agents and Workflows

```bash
testbed run                     # Uses workflows/testbed.toml
testbed run fast_processing     # Uses workflows/fast_processing_default.toml
```

**Startup sequence:**

```mermaid
sequenceDiagram
    participant User
    participant CLI as testbed CLI
    participant Orch as orchestrator.py
    participant Supv as supervisord
    participant Agents

    User->>CLI: testbed run
    CLI->>Orch: run(config_name)
    Orch->>Orch: Load config (testbed.toml)
    Orch->>Supv: Check running agents

    alt Agents already running
        Supv-->>Orch: Running agents list
        Orch-->>CLI: Error: agents running
        CLI-->>User: "Run testbed stop-agents first"
    else No agents running
        Orch->>Supv: Restart supervisord
        Note over Supv: Picks up fresh env vars
        Orch->>Supv: Start workflow-runner
        Orch->>Supv: Start enabled agents
        Supv->>Agents: Launch processes
        Orch->>Agents: Send run_workflow command
        Orch-->>CLI: Success
        CLI-->>User: "Workflow triggered"
    end
```

### Stopping Agents

```bash
testbed stop-agents             # Stop all workflow agents
```

This command:
1. Connects to supervisord using `agents.supervisord.conf`
2. Issues `supervisorctl stop all`
3. All agent processes are terminated

**Important:** `testbed stop-agents` uses `agents.supervisord.conf` (for workflow agents), not `supervisord.conf` (which manages web services).

## MCP Control Path

### Agent Manager Daemon

The Agent Manager is a per-user daemon that bridges MCP commands to local supervisord:

```bash
testbed agent-manager           # Run in foreground
nohup testbed agent-manager &   # Run in background
```

The daemon:
- Listens on `/queue/testbed.{username}.control`
- Sends heartbeats to the monitor
- Executes start/stop commands via supervisorctl

```mermaid
flowchart LR
    subgraph Django["Django Monitor"]
        MCP["MCP Tool"]
    end

    subgraph AMQ["ActiveMQ"]
        CQ["Control Queue<br/>/queue/testbed.{user}.control"]
    end

    subgraph Local["User's Session"]
        AM["Agent Manager"]
        SUPV["supervisord"]
    end

    MCP -->|"send command"| CQ
    CQ -->|"receive"| AM
    AM -->|"supervisorctl"| SUPV
    AM -.->|"heartbeat"| Django
```

### MCP Tools

```python
# Check agent manager status
check_agent_manager(username)

# Start testbed (agents + workflow runner)
start_user_testbed(username, config_name="testbed.toml")

# Stop all agents
stop_user_testbed(username)

# Start a workflow (after agents are running)
start_workflow(namespace="torre2", stf_count=10)

# Stop a running workflow
stop_workflow(execution_id="stf_datataking-wenauseic-0049")

# Comprehensive status
get_testbed_status(username)
```

### MCP Startup Sequence

```mermaid
sequenceDiagram
    participant MCP as MCP Tool
    participant AMQ as ActiveMQ
    participant AM as Agent Manager
    participant Supv as supervisord
    participant Agents

    MCP->>AMQ: start_testbed command
    AMQ->>AM: Receive command
    AM->>AM: Load config
    AM->>Supv: Check running agents

    alt Agents already running
        AM-->>MCP: Error: agents running
    else No agents running
        AM->>Supv: Restart supervisord
        AM->>Supv: Start all agents
        Supv->>Agents: Launch processes
        AM-->>MCP: Success
    end
```

## Configuration

### testbed.toml Structure

```toml
[testbed]
namespace = "torre2"              # Isolation namespace

[agents.data]
enabled = true                    # Enable this agent
script = "example_agents/example_data_agent.py"

[agents.fastmon]
enabled = true

[agents.fast_processing]
enabled = true

[workflow]
name = "stf_datataking"           # Default workflow
config = "fast_processing_default"
realtime = true
```

### Environment Variables

Supervisord passes environment variables to agents:

```ini
# agents.supervisord.conf
[program:example-data-agent]
command=python example_agents/example_data_agent.py
directory=%(ENV_SWF_HOME)s/swf-testbed
environment=SWF_TESTBED_CONFIG="%(ENV_SWF_TESTBED_CONFIG)s"
autostart=false
autorestart=true
```

Key variables:
| Variable | Purpose |
|----------|---------|
| `SWF_HOME` | Parent directory containing swf-* repos |
| `SWF_TESTBED_CONFIG` | Path to testbed.toml |
| `SWF_MONITOR_HTTP_URL` | Monitor REST API URL |
| `SWF_API_TOKEN` | API authentication token |

**Important:** Supervisord must be restarted to pick up environment variable changes. Both CLI and MCP paths automatically restart supervisord on start.

## Process Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Stopped: Initial

    Stopped --> Starting: testbed run /<br/>start_user_testbed
    Starting --> Running: Agents started
    Running --> Stopping: testbed stop-agents /<br/>stop_user_testbed
    Stopping --> Stopped: Agents stopped

    Running --> Running: start_workflow /<br/>stop_workflow

    note right of Starting
        1. Check no agents running
        2. Restart supervisord
        3. Start enabled agents
    end note
```

## Troubleshooting

### Agents Won't Start: "agents already running"

```bash
# Check what's running
supervisorctl -c agents.supervisord.conf status

# Stop existing agents
testbed stop-agents

# Now start fresh
testbed run
```

### Wrong Namespace

Agents use the namespace from the config file that was active when supervisord started. If agents are using the wrong namespace:

```bash
testbed stop-agents
# Edit testbed.toml or set SWF_TESTBED_CONFIG
testbed run
```

The restart of supervisord picks up the new configuration.

### Agent Manager Not Responding

```bash
# Check if agent manager is running
ps aux | grep user_agent_manager

# Check MCP status
# (via MCP tool)
check_agent_manager(username)

# Restart agent manager
pkill -f user_agent_manager
nohup testbed agent-manager &
```

## See Also

- [Architecture Overview](architecture.md) - System design and components
- [Fast Processing Workflow](fast-processing-workflow.md) - Workflow sequence diagram
- [Operations Guide](operations.md) - Day-to-day operations
