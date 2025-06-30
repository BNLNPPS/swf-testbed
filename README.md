# swf-testbed

This is the umbrella repository for the ePIC streaming workflow testbed.

The testbed plan is based on ePIC streaming computing model WG discussions
in the streaming computing model meeting[^1], guided by the ePIC streaming
computing model report[^2], and the ePIC workflow management system
requirements draft[^3].

## Testbed plan

The testbed prototypes the ePIC streaming computing model's workflows and
dataflows from Echelon 0 (E0) egress (the DAQ exit buffer)
through the processing that takes place at the two Echelon 1 computing
facilities at BNL and JLab.

The testbed scope, timeline and workplan are described in a planning
document[^4]. Detailed progress tracking and development discussion is in a
progress document[^5].

See the E0-E1 overview slide deck [^6] for more information on the E0-E1
workflow and dataflow.
The following is a schematic of the system the testbed targets (from the blue
DAQ external subnet rightwards).

![E0-E1 workflow schematic](images/E0-E1_workflow_schematic.png)

*Figure: E0-E1 data flow and processing schematic*

## Design and implementation

Overall system design and implementation notes:

- The implementation language is Python 3.9 or greater.
- Testbed modules are implemented as a set of loosely coupled agents, each
  with a specific role in the system.
- The agents communicate via messaging, using ActiveMQ as the message
  broker.
- The PanDA [^7] distributed workload management system and its ancillary
  components are used for workflow orchestration and workload execution.
- The Rucio [^8] distributed data management system is used for
  management and distribution of data and associated metadata, in close
  orchestration with PanDA.
- High quality monitoring and centralized management of system data (metadata,
  bookkeeping, logs etc.) is a primary design goal. Monitoring and system
  data gathering and distribution is implemented via a web service backed
  by a relational database, with a REST API for data access and reporting.

### Prompt Tips

**Note to the AI Assistant:** The following "Prompt Tips" are a guide for our
collaboration on this project. Please review them carefully and integrate them
into your operational context to ensure your contributions are consistent,
high-quality, and aligned with the project's standards.

#### General

- **Adhere to established standards and conventions.** When implementing new
  features, prioritize the use of established standards, conventions, and
  naming schemes provided by the programming language, frameworks, or
  widely-used libraries. Avoid introducing custom terminology or patterns when a
  standard equivalent exists.
- **Portability is paramount.** All code must work across different platforms
  (macOS, Linux, Windows), Python installations (system, homebrew, pyenv, etc.),
  and deployment environments (Docker, local, cloud). Never hardcode absolute
  paths, assume specific installation directories, or rely on system-specific
  process names or command locations. Use relative paths, environment variables,
  and standard tools (like supervisorctl) rather than platform-specific process
  detection. When in doubt, choose the more portable solution.
- **Favor Simplicity and Maintainability.** Strive for clean, simple, and
  maintainable solutions. When faced with multiple implementation options,
  recommend the one that is easiest to understand, modify, and debug. Avoid
  overly complex or clever code that might be difficult for others (or your
  future self) to comprehend. Adhere to the principle of "Keep It Simple,
  Stupid" (KISS).
- **Follow Markdown Linting Rules.** Ensure all markdown content adheres to the
  project's linting rules. This includes, but is not limited to, line length,
  list formatting, and spacing. Consistent formatting improves readability and
  maintainability.
- **Maintain the prompts.** Proactively suggest additions or modifications to
  these tips as the project evolves and new collaboration patterns emerge.

#### Project-Specific

- **Context Refresh.** To regain context on the SWF Testbed project, follow
  these steps:
    1. Review the high-level goals and architecture in `swf-testbed/README.md`
       and `swf-testbed/docs/architecture_and_design_choices.md`.
    2. Examine the dependencies and structure by checking the `pyproject.toml`
       and `requirements.txt` files in each sub-project (`swf-testbed`,
       `swf-monitor`, `swf-common-lib`).
    3. Use file and code exploration tools to investigate the existing codebase
       relevant to the current task. For data models, check `models.py`; for
       APIs, check `urls.py` and `views.py`.
    4. Consult the conversation summary to understand recent changes and
       immediate task objectives.

- **Verify and Propose Names.** Before implementing new names for variables,
  functions, classes, context keys, or other identifiers, first check for
  consistency with existing names across the relevant context. Once verified,
  propose them for review. This practice ensures clarity and reduces rework.

> **Prompt Tip: Ensuring Robust and Future-Proof Tests**
>
> - Write tests that assert on outcomes, structure, and status codes—not on exact output strings or UI text, unless absolutely required for correctness.
> - For CLI and UI tests, check for valid output structure (e.g., presence of HTML tags, table rows, or any output) rather than specific phrases or case.
> - For API and backend logic, assert on status codes, database state, and required keys/fields, not on full response text.
> - This approach ensures your tests are resilient to minor UI or output changes, reducing maintenance and avoiding false failures.
> - Always run tests using the provided scripts (`./run_tests.sh` or `./run_all_tests.sh`) to guarantee the correct environment and configuration.

### Participants

At present the testbed is a project of the Nuclear and Particle Physics
Software (NPPS) group at BNL; collaborators are welcome.

- Torre Wenaus (lead)
- Maxim Potekhin
- Ejiro Umaka
- Michel Villanueva
- Xin Zhao

## Getting Started

This section provides a complete step-by-step guide to set up and run the SWF
testbed on your local machine.

### Prerequisites

- **Python 3.9 or greater**
- **Git** for cloning repositories
- **Docker Desktop** (recommended) OR **PostgreSQL** and **ActiveMQ** installed locally

### Step 1: Clone the Repositories

Clone all three SWF repositories as siblings in the same parent directory:

```bash
# Create a directory for the SWF project
mkdir swf-project && cd swf-project

# Clone all repositories
git clone https://github.com/BNLNPPS/swf-testbed.git
git clone https://github.com/BNLNPPS/swf-monitor.git
git clone https://github.com/BNLNPPS/swf-common-lib.git

# Your directory structure should now look like:
# swf-project/
# ├── swf-testbed/
# ├── swf-monitor/
# └── swf-common-lib/
```

### Step 2: Set Up Infrastructure Services

Choose one of the following approaches:

#### Option A: Using Docker (Recommended)

1. **Install Docker Desktop** and ensure it's running
2. **Navigate to swf-testbed:**
   ```bash
   cd swf-testbed
   ```
3. **Start services:**
   ```bash
   docker-compose up -d
   ```

#### Option B: Local Installation (macOS with Homebrew)

1. **Install PostgreSQL and ActiveMQ:**
   ```bash
   brew install postgresql@14 activemq
   ```

2. **Start the services:**
   ```bash
   brew services start postgresql@14
   brew services start activemq
   ```

3. **Create database and user:**
   ```bash
   createuser -s admin
   createdb -O admin swfdb
   psql -U admin -d swfdb -c "ALTER USER admin PASSWORD 'admin';"
   ```

### Step 3: Configure Environment Variables

1. **Navigate to swf-testbed:**
   ```bash
   cd swf-testbed
   ```

2. **Configure swf-monitor secrets:**
   ```bash
   cd ../swf-monitor
   cp .env.example .env
   ```

3. **Edit the `.env` file** with your database credentials:
   ```bash
   # For local development, use these values:
   DB_PASSWORD='admin'  # Match your PostgreSQL setup
   SECRET_KEY='django-insecure-your-secret-key-here'  # Generate a new one for production
   ```

### Step 4: Set Up Python Environment and Install Dependencies

**Activate the virtual environment:**

```bash
cd swf-testbed
source venv/bin/activate
```

**Install dependencies for each component:**

```bash
# Install swf-common-lib (shared utilities)
pip install -e ../swf-common-lib

# Install swf-monitor (Django web application)
pip install -e ../swf-monitor

# Install swf-testbed CLI
pip install -e .
```

### Step 5: Initialize and Run the Testbed

1. **Initialize the testbed:**
   ```bash
   cd swf-testbed
   swf-testbed init
   ```

2. **Set up Django database and admin user:**
   ```bash
   # Run Django migrations and create superuser
   python ../swf-monitor/src/manage.py migrate
   python ../swf-monitor/src/manage.py createsuperuser
   ```

3. **Load sample data (optional):**
   ```bash
   # Load fake log data to populate the monitoring interface
   python ../swf-monitor/scripts/load_fake_logs.py
   ```

4. **Start the testbed:**
   ```bash
   # If using Docker:
   swf-testbed start

   # If using local services:
   swf-testbed start-local
   ```

5. **Check status:**
   ```bash
   swf-testbed status  # or status-local
   ```

### Step 6: Verify Setup

1. **Check web interface:**
   - Django admin: http://localhost:8000/admin/ (use superuser credentials created in Step 5)
   - ActiveMQ console: http://localhost:8161/admin/ (admin/admin)

2. **Run tests:**
   ```bash
   # Run all tests across all repositories
   ./run_all_tests.sh

   # Or run tests for individual components
   cd swf-monitor && ./run_tests.sh
   ```

### Quick Start Summary

For experienced users, the minimal setup is:

```bash
# Clone repos, install Docker, then:
cd swf-testbed
docker-compose up -d
cd ../swf-monitor && cp .env.example .env  # Edit DB_PASSWORD='admin'
cd ../swf-testbed
source venv/bin/activate
pip install -e ../swf-common-lib ../swf-monitor .
swf-testbed init
cd ../swf-monitor/src && python manage.py createsuperuser && cd ../../swf-testbed
swf-testbed start
```

## Testbed Infrastructure

### Environment Setup

The testbed automatically sets up the required environment variables when you
run `swf-testbed start` or `swf-testbed start-local`. The `SWF_HOME` environment
variable is automatically detected and configured to point to the parent
directory containing all your `swf-*` repositories.

No manual environment setup is required - the testbed CLI handles this
automatically.

### Secrets and Configuration Management

The testbed uses environment variables to securely manage database credentials,
API keys, and other sensitive configuration. This approach keeps secrets out of
source code and allows for different configurations in development and
production environments.

#### Environment Variable Configuration

Each component that requires secrets uses a `.env` file for local configuration:

- **swf-monitor**: Django application secrets in `swf-monitor/.env` (required - core infrastructure)
- **swf-data-agent**: Agent configuration in `swf-data-agent/.env` (if present)
- **swf-processing-agent**: PanDA credentials in `swf-processing-agent/.env` (if present)

#### Setting Up swf-monitor Environment Variables

The Django monitoring application requires database and messaging credentials.
To configure:

1. **Copy the environment template:**
   ```bash
   cp swf-monitor/.env.example swf-monitor/.env
   ```

2. **Edit the `.env` file** with your actual credentials:
   ```bash
   # Django Secret Key - generate a new one for production
   SECRET_KEY='django-insecure-your-secret-key-here'
   
   # PostgreSQL Database Settings
   DB_NAME='swfdb'
   DB_USER='admin'
   DB_PASSWORD='your_db_password'
   DB_HOST='localhost'
   DB_PORT='5432'
   
   # ActiveMQ Settings
   ACTIVEMQ_HOST='localhost'
   ACTIVEMQ_PORT=61613
   ACTIVEMQ_USER='admin'
   ACTIVEMQ_PASSWORD='admin'
   ```

3. **For production deployments**, also set:
   ```bash
   DEBUG=False
   ALLOWED_HOSTS=your.domain.com,www.your.domain.com
   ```

#### Default Development Credentials

For local development with PostgreSQL and ActiveMQ installed via Homebrew:

- **PostgreSQL**: user `admin`, password `admin`, database `swfdb`
- **ActiveMQ**: user `admin`, password `admin`, default ports

#### Security Notes

- `.env` files are excluded from version control via `.gitignore`
- Never commit actual passwords or API keys to the repository
- Use strong, unique passwords for production deployments
- Generate a new Django `SECRET_KEY` for production (see Django documentation)

## Running the Testbed

You can run the testbed in two modes: using Docker for managing background
services (PostgreSQL and ActiveMQ), or by running these services locally on
your host machine.

### Using Docker (Recommended)

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

### Running Locally (Without Docker)

This mode is for users who prefer to manage the background services directly on
their host machine.

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
  assumes PostgreSQL and ActiveMQ are already running.
- `swf-testbed stop-local`: Stops the Python agents managed by Supervisor.
- `swf-testbed status-local`: Checks the status of local services (PostgreSQL,
  ActiveMQ) and the Python agents managed by Supervisor.

## Development

### Process Management

We use `supervisor` to manage the various Python agent processes. The
configuration is located in `supervisord.conf`. This file is a template and
should be copied to the root of the project during initialization.

The `swf-testbed init` command will create the `logs` directory and copy the
`supervisord.conf` file for you.

The `supervisord.conf` file is configured to use the `SWF_HOME` environment
variable to locate the various `swf-*` repositories. This is automatically
configured when you run any `swf-testbed` commands.

STF availability. It also has a 'watcher' role to identify and report
stalls or anomalies.

Interactions with Rucio are consolidated in this agent.

### [swf-processing-agent](https://github.com/BNLNPPS/swf-processing-agent)

This is the prompt processing agent that configures and submits PanDA
processing jobs to execute the streaming workflows of the testbed.

Interactions with PanDA are consolidated in this agent.

### [swf-fastmon-agent](https://github.com/BNLNPPS/swf-fastmon-agent)

This is the fast monitoring agent designed to consume (fractions of) STF data
for quick, near real-time monitoring. This agent resides at E1 and performs
remote data reads from STF files in the DAQ exit buffer, skimming a fraction
of the data of interest for fast monitoring. The agent is notified of new
STF availability by the swf-data-agent.

### [swf-mcp-agent](https://github.com/BNLNPPS/swf-mcp-agent)

This agent may be added in the future for managing Model Context Protocol
(MCP) services. For the moment, this is done in swf-monitor (Colocated with
the agent data the MCP services provide)


Note Paul Nilsson's [ask-panda
example](https://github.com/PalNilsson/ask-panda) of
  MCP server and client.

## System infrastructure

This repository hosts overall system infrastructure for the testbed software,
including the following.

### Agent process management

The testbed agents are managed by a process manager, which is
responsible for configuring, starting, stopping, and monitoring the agents.

The python [supervisor](http://supervisord.org/) process manager is used.

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

#### Production Broker

In a production environment, the agents should be configured to use the centrally
provided ActiveMQ service. This is done by setting the same environment variables
 to point to the production broker's host, port, and credentials.

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

  in the desired repo directory.

- The test infrastructure is designed to automatically use the active Python
  environment or a local venv if present. If neither is available, the test
  runner will exit with a clear error message.

Test results are printed to the console. For more details, consult the logs or
output of individual test runs.

## Development Workflow

### Multi-Repository Development Strategy

The SWF testbed consists of multiple coordinated repositories that work together
as an integrated system. Development across these repositories requires careful
coordination to maintain system stability and integration.

#### Repository Structure

The testbed is composed of three core repositories that must be kept as siblings:

- **swf-testbed**: Core testbed infrastructure, CLI, and orchestration
- **swf-monitor**: Django web application for monitoring and data management
- **swf-common-lib**: Shared utilities and common code

Additional repositories will be added as the testbed expands with new agents,
services, and functionality.

#### Branching Strategy

We use a **coordinated infrastructure branching strategy** for cross-repository
development work:

##### Infrastructure Development (Recommended)

For infrastructure improvements, testing framework enhancements, and foundational
changes that span multiple repositories:

```bash
# Create synchronized infrastructure branches across all repos
cd swf-testbed && git checkout -b infra/baseline-v1
cd ../swf-monitor && git checkout -b infra/baseline-v1
cd ../swf-common-lib && git checkout -b infra/baseline-v1

# Work freely across repositories
# Commit frequently with descriptive messages
# Let commit messages document the nature and progression of changes

# When infrastructure phase is complete:
# 1. Test full system integration with ./run_all_tests.sh
# 2. Create coordinated pull requests across all repositories
# 3. Merge to main simultaneously across all repos
# 4. Start next infrastructure iteration (infra/baseline-v2)
```

##### Feature Development

For features that primarily affect a single repository:

```bash
# Create feature branch in the primary repository
git checkout -b feature/your-feature-name

# Work, commit, and create pull request as normal
# If cross-repo changes are needed, coordinate with infrastructure approach
```

#### Milestone Tagging

For significant milestones and releases, create coordinated tags across all repositories:

```bash
# Create tags simultaneously across all core repositories
git tag -a milestone-name -m "Milestone description"
git -C ../swf-monitor tag -a milestone-name -m "Milestone description"
git -C ../swf-common-lib tag -a milestone-name -m "Milestone description"

# Push tags to all repositories
git push origin milestone-name
git -C ../swf-monitor push origin milestone-name
git -C ../swf-common-lib push origin milestone-name
```

This ensures that milestone references point to coordinated states across the
entire testbed system.

#### Development Guidelines

1. **Never push directly to main** - Always use branches and pull requests
2. **Always coordinate across repositories** - Use matching branch names, tags, and timing for all cross-repo operations
3. **Test system integration** - Run `./run_all_tests.sh` before merging infrastructure changes
4. **Maintain test coverage** - As you add functionality, extend the tests to ensure `./run_all_tests.sh` reliably evaluates system integrity
5. **Document through commits** - Use descriptive commit messages to explain the progression of work
6. **Maintain sibling structure** - Keep all `swf-*` repositories as siblings in the same parent directory

#### Pull Request Process

1. **Create descriptive pull requests** with clear titles and descriptions
2. **Reference related PRs** in other repositories when applicable
3. **Ensure tests pass** across all affected repositories
4. **Coordinate merge timing** for cross-repo infrastructure changes
5. **Clean up branches** after successful merges

This workflow ensures that the testbed remains stable and integrated while
allowing for rapid infrastructure development and feature additions.

## Glossary

- STF: super time frame. A contiguous set of ~1000 TFs containing about ~0.6s
  of ePIC data, corresponding to ~2GB. The STF is the atomic unit of
  streaming data processing.
- TF: time frame. Atomic unit of ePIC detector readout ~0.6ms in duration.

## References

[^1]: [ePIC streaming computing model meeting page](https://docs.google.com/document/d/1t5vBfgro8Kb6MKc-bz2Y67u3cOCpHK4dfepbJX-nEbE/edit?tab=t.0#heading=h.y3evqgz3sc98)

[^2]: [ePIC streaming computing model report](https://zenodo.org/records/14675920)

[^3]: [ePIC workflow management system requirements draft](https://docs.google.com/document/d/1OmAGzFgZgEP6ntuRkP51kiOqF_0uh_RPjq8wgdTwb2A/edit?tab=t.0#heading=h.g1vlz8vqp7ht)

[^4]: [ePIC streaming workflow testbed planning document](https://docs.google.com/document/d/1mPqMsjHiymkeAB7uih_8TjFIluwM8MENIWZF3EDwNrU/edit?tab=t.0)

[^5]: [ePIC streaming workflow testbed progress document](https://docs.google.com/document/d/1PUoo-W6dCeOKsD4VubYTgSxBHBUb4D5dYfVy1oLYh7E/edit?tab=t.0#heading=h.qovfena71s)

[^6]: [E0-E1 overview slide deck](https://docs.google.com/presentation/d/1Vbt68LwBDA-eDghlWWg8278ys_K0axbX/edit?slide=id.g2fdc8697d63_0_18#slide=id.g2fdc8697d63_0_18)

[^7]: [PanDA: Production and Distributed Analysis System](https://link.springer.com/article/10.1007/s41781-024-00114-3)
  [PanDA documentation](https://panda-wms.readthedocs.io/en/latest/index.html)
  [BNL PanDA startup guide](https://docs.google.com/document/d/1zxtpDb44yNmd3qMW6CS7bXCtqZk-li2gPwIwnBfMNNI/edit?tab=t.0#heading=h.iiqfpuwcgs2k)

[^8]: [Rucio: A Distributed Data Management System](https://link.springer.com/article/10.1007/s41781-019-0026-3)
    [Rucio home](https://rucio.cern.ch/)
