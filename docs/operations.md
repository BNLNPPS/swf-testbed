# Operations Guide

Running and managing the SWF Testbed services.

## Running the Testbed

The testbed supports two deployment modes:

**Development Mode**: Docker manages PostgreSQL and ActiveMQ
**System Mode**: System services manage PostgreSQL and ActiveMQ (e.g., pandaserver02)

Use `python report_system_status.py` to check which services are available and determine the appropriate mode.

### Development Mode (Docker-managed)

This is the recommended approach as it provides a consistent, cross-platform
environment.

**Prerequisites:**

- Docker Desktop installed and running.

**Usage:**

The `swf-testbed` CLI provides commands to manage the entire testbed, including
the Docker containers and the Python agents managed by Supervisor.

- `swf-testbed start`: Starts the Docker containers (PostgreSQL, ActiveMQ) and
  then starts all Python agents.
- `swf-testbed stop`: Stops and removes the Docker containers, and stops all
  Python agents.
- `swf-testbed status`: Shows the status of the Docker containers and the
  Python agents.

### System Mode (System-managed services)

This mode is for environments where PostgreSQL and ActiveMQ are managed as system services.

**Prerequisites:**

You are responsible for installing and running PostgreSQL and ActiveMQ.

- **PostgreSQL:**
  - **macOS (using Homebrew):**

    ```bash
    brew install postgresql
    brew services start postgresql
    # Optional: Create a user and database
    # createuser -s admin
    # createdb -O admin swfdb
    ```

  - **Other Systems:** Follow the official installation guide for your
    operating system.

- **ActiveMQ:**
  - **macOS (using Homebrew):**

    ```bash
    brew install activemq
    brew services start activemq
    ```

  - **Other Systems:** Download and follow the installation instructions from the
    [ActiveMQ website](https://activemq.apache.org/components/classic/download/).

**Usage:**

The `swf-testbed` CLI also provides commands for managing the testbed services
when they are running locally.

- `swf-testbed start-local`: Starts the Python agents using Supervisor. It
  assumes PostgreSQL and ActiveMQ are already running as system services.
- `swf-testbed stop-local`: Stops the Python agents managed by Supervisor.
- `swf-testbed status-local`: Checks the status of system services (PostgreSQL,
  ActiveMQ) and the Python agents managed by Supervisor.
- `python report_system_status.py`: **RECOMMENDED** - Comprehensive system readiness check

### Agent Process Management

The testbed agents are managed by a process manager, which is
responsible for configuring, starting, stopping, and monitoring the agents.

We use `supervisor` to manage the various Python agent processes. The
configuration is located in `supervisord.conf`. This file is a template and
should be copied to the root of the project during initialization.

The `swf-testbed init` command will create the `logs` directory and copy the
`supervisord.conf` file for you.

The `supervisord.conf` file is configured to use the `SWF_HOME` environment
variable to locate the various `swf-*` repositories. This is automatically
configured when you run any `swf-testbed` commands.

### Namespace Configuration

Namespaces isolate workflows and messages, allowing multiple users or projects to share infrastructure without interference.

**Configure your namespace** in `workflows/testbed.toml`:

```toml
[testbed]
namespace = "your-namespace"  # e.g., "epic-fastmon-dev", "team-dec29"
```

**Namespace guidelines:**
- Set namespace before running any workflows
- Use descriptive names (project, team, or purpose)
- Multiple users can collaborate in one namespace
- Filter by namespace in the monitor UI to see only your data

### Message Broker

The [ActiveMQ](https://activemq.apache.org/) message broker provides the
messaging backbone for the testbed agents to communicate.

#### Local Development Broker

For local development and testing, a standalone broker can be run using Docker.
This is managed by the `docker-compose.yml` file in this repository. To start
the local broker, run:

```bash
docker-compose up -d
```

When using the local broker, the agents should be configured with the following
environment variables:

```bash
export ACTIVEMQ_HOST=localhost
export ACTIVEMQ_PORT=61616
export ACTIVEMQ_USER=admin
export ACTIVEMQ_PASSWORD=admin
```

#### System Mode Broker

In system mode environments, the agents should be configured to use the system-managed
ActiveMQ service. This is done by setting the same environment variables
 to point to the system broker's host, port, and credentials.

Each agent (e.g., `swf-monitor`, `swf-data-agent`) will need to be configured
to read these environment variables and use them to connect to the broker. The
`swf-monitor` application, for example, reads these values from its Django
`settings.py` file, which in turn can be populated from environment variables.

## Testing

The testbed provides a unified, robust test runner to ensure all components are
tested consistently and automatically.

- To run all tests across all `swf-*` repositories, simply execute:

  ```bash
  ./run_all_tests.sh
  ```

  This script autodiscovers sibling `swf-*` repositories, runs their test
  suites, and reports results with clear separators.

- To run tests for a specific repository, use its own `run_tests.sh` script
  (if present), e.g.:

  ```bash
  ./run_tests.sh
  ```