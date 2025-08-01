# CLAUDE.md

# 🚨 MANDATORY CHECKLIST - READ FIRST - NO EXCEPTIONS 🚨

**BEFORE RUNNING ANY PYTHON COMMANDS:**
1. ✅ **ALWAYS ACTIVATE VENV FIRST**: `cd /eic/u/wenauseic/github/swf-testbed && source .venv/bin/activate`
2. ✅ **LOAD ENVIRONMENT**: `source ~/.env` (all variables are exported)
3. ✅ **VERIFY LOCATION**: Run `pwd` to confirm current directory

**FAILURE TO FOLLOW THIS CHECKLIST CAUSES COMMAND FAILURES AND WASTES TIME**

---

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository and other repositories in the swf-* family. It outlines critical thinking requirements, development practices, and operational guidelines to ensure effective and efficient coding.

## ⚠️ CRITICAL RULES - ABSOLUTE REQUIREMENTS ⚠️

### File Operations Rule
**MAJOR ERROR WARNING: Deleting files, directories, database tables, databases or other entities without explicit user request or authorization is strictly forbidden and constitutes a major error. NEVER use rm, delete, DROP TABLE, or any deletion operations unless explicitly instructed by the user.**

### Environment Setup Rule
**DO NOT RUN PYTHON COMMANDS WITHOUT VENV:** Every Python command must be preceded by:
```bash
cd /eic/u/wenauseic/github/swf-testbed && source .venv/bin/activate && source ~/.env
```
**This includes:** python, pip, pytest, any example_agents scripts, or swf-testbed commands

## Critical Thinking Requirements

Before implementing ANY solution, Claude must explain:

1. **Complete Data Flow Analysis**
   - Where does data come from?
   - Where does it get stored?
   - Where does it get used?
   - What persists between runs?
   - What gets cached or reused?

2. **Problem Definition**
   - What is the actual problem vs what I think it is?
   - What assumptions am I making?
   - What evidence do I have that my understanding is correct?

3. **Solution Validation**
   - Why will this solution work?
   - What could go wrong?
   - How can I verify it worked?
   - What side effects might occur?

## DO NOT CODE UNTIL:
- You can trace the complete data flow
- You can explain why the current behavior is happening
- You can explain exactly what needs to change
- You have stated all assumptions explicitly

## Common Failure Patterns to Avoid:
- Jumping to implementation without understanding the system
- Assuming data behaves as expected without verification
- Ignoring data persistence between script runs
- Making changes without understanding their scope
- Failing to clear cached/persistent data

## When Stuck:
1. Stop coding
2. Explain what you think is happening
3. Ask for verification of your understanding
4. Only proceed when understanding is confirmed

## Development Environment

### Claude Code Setup
- **Launch Claude Code from the parent directory** containing all swf-* repositories (e.g., `/Users/username/github/`)
- This enables access to all core repositories for coordinated multi-repository development
- Do not launch from within individual repository directories as this restricts cross-repo operations

## Development Commands

### Testing
- `./run_tests.py` - Run tests for swf-testbed only (uses pytest)
- `./run_all_tests.py` - Run tests across all swf-* repositories in parent directory
- Tests are located in `tests/` directory and use pytest framework
- **Auto-activation**: Test scripts automatically activate the virtual environment if needed
  - Just run `./run_all_tests.py` directly - no manual setup required!
  - Scripts set up their own environment variables internally
  - **EXAMPLE AGENTS NEED THE SAME PATTERN** - they should auto-load venv and ~/.env

### Testbed Management
- `swf-testbed init` - Initialize environment (creates logs/ directory and supervisord.conf)
- `swf-testbed start` - Start testbed with Docker services (PostgreSQL, ActiveMQ) + agents
- `swf-testbed stop` - Stop all Docker services and agents
- `swf-testbed status` - Check status of Docker services and agents
- `swf-testbed start-local` - Start agents only (assumes PostgreSQL/ActiveMQ running locally)
- `swf-testbed stop-local` - Stop local agents only
- `swf-testbed status-local` - Check status of local services and agents

### Installation and Dependencies
**🚨 CRITICAL: ALWAYS ACTIVATE VIRTUAL ENVIRONMENT FIRST 🚨**

**EVERY PYTHON COMMAND MUST START WITH:**
```bash
cd /eic/u/wenauseic/github/swf-testbed && source .venv/bin/activate && source ~/.env
```

**Commands:**
- `source .venv/bin/activate && source ~/.env && pip install -e .` - Install in development mode
- Dependencies managed via `pyproject.toml`
- `source .venv/bin/activate && source ~/.env && pip install .[test]` - Install test dependencies
- Virtual environment located at `.venv/` - **NEVER SKIP ACTIVATION**

**Initial Setup**
- Run `source install.sh` once when setting up the development environment
- This installs all dependencies and creates the virtual environment
- After initial setup, test scripts handle their own environment activation

**CRITICAL: Django .env Configuration Required**
- Copy `.env.example` to `.env` in swf-monitor directory: `cp ../swf-monitor/.env.example ../swf-monitor/.env`
- Update database password in `.env` to match Docker: `DB_PASSWORD='your_db_password'`
- Set Django secret key: `SECRET_KEY='django-insecure-dev-key-for-testing-only-change-for-production-12345678901234567890'`
- Run Django migrations: `cd ../swf-monitor/src && python manage.py migrate`
- Without proper .env setup, Django tests will fail with authentication errors

## Architecture Overview

### Multi-Repository Structure
This is part of a coordinated multi-repository system with sibling repositories:
- **swf-testbed**: Core infrastructure, CLI, and orchestration (this repo)
- **swf-monitor**: Django web application for monitoring and data management
- **swf-common-lib**: Shared utilities and common code
- Additional agent repositories: swf-daqsim-agent, swf-data-agent, swf-processing-agent, swf-fastmon-agent

All repositories must be cloned as siblings in the same parent directory for proper operation.

### Agent-Based Architecture
The system implements loosely coupled agents that communicate via ActiveMQ messaging:
- Agents are Python processes managed by supervisord
- Each agent has a specific role in the streaming workflow
- Communication is asynchronous via message broker
- Process management configuration in `supervisord.conf`

### Infrastructure Components
- **Process Management**: supervisord manages all Python agent processes
- **Message Broker**: ActiveMQ provides messaging backbone
- **Database**: PostgreSQL for monitoring data and metadata
- **Web Interface**: Django application (swf-monitor) for system monitoring
- **CLI**: Typer-based command line interface for testbed management

### Environment Setup
- `SWF_HOME` environment variable automatically set to parent directory containing all swf-* repos
- Docker Compose provides PostgreSQL and ActiveMQ services for development
- Local installation supported for users who prefer host-managed services

## Development Practices

### Multi-Repository Development
- **Always use infrastructure branches**: `infra/baseline-v1`, `infra/baseline-v2`, etc. for all development
- Create coordinated branches with same name across all affected repositories
- **CRITICAL: Always push with `-u` flag on first push**: `git push -u origin branch-name`
  - This sets up branch tracking which is essential for VS Code and git status
  - Without `-u`, branches appear "unpublished" even after pushing
  - Example: `git push -u origin infra/baseline-v10`
- Document specific features and changes through descriptive commit messages
- Never push directly to main - always use branches and pull requests
- Run `./run_all_tests.sh` before merging infrastructure changes
- Maintain sibling directory structure for all swf-* repositories

### Code Organization
- Shared code goes in `swf-common-lib` package to prevent duplication
- Agent-specific code stays in respective agent repositories
- CLI implementation in `src/swf_testbed_cli/main.py`
- Configuration templates in repository root

### Testing Strategy
- Pytest for unit tests
- Test infrastructure designed for cross-platform compatibility
- Tests assert on outcomes and structure, not exact output strings
- Automated test discovery across all swf-* repositories

## Documentation Maintenance

### README Table of Contents
The README.md contains a manual Table of Contents that must be kept synchronized with the document structure. When making changes to README.md:

1. **Check the TOC** against actual section headings after any structural changes
2. **Update anchor links** if section names change (use GitHub-style `#section-name` format)
3. **Add new sections** to the TOC in the correct order
4. **Remove deleted sections** from the TOC
5. **Reorder TOC items** to match the document structure

This maintenance should be part of any commit that involves adding, removing, or renaming sections in the README.

## Key Configuration Files

- `pyproject.toml`: Package configuration and dependencies
- `supervisord.conf`: Process management configuration template
- `docker-compose.yml`: Development infrastructure services
- `run_tests.sh` / `run_all_tests.sh`: Test execution scripts

## External Dependencies

- **PanDA**: Distributed workload management system for workflow orchestration
- **Rucio**: Distributed data management system
- **ActiveMQ**: Message broker for agent communication
- **PostgreSQL**: Database for monitoring and metadata storage
- **supervisord**: Process management for Python agents

## 🤖 AI Development Guidelines - MANDATORY FOR CLAUDE

### Environment Setup (Critical - Most Common Failure Point)
**RULE: NO PYTHON COMMANDS WITHOUT ENVIRONMENT SETUP**

**Before ANY Python operation, you MUST run:**
```bash
cd /eic/u/wenauseic/github/swf-testbed && source .venv/bin/activate && source ~/.env
```

**This applies to:**
- `python example_agents/daq_simulator.py`
- `pip install anything`
- `pytest tests/`
- `swf-testbed` commands
- Any Python script execution

**Why this fails:**
- Environment variables from ~/.env are not available to subprocesses
- Virtual environment packages are not in PATH
- Proxy settings (NO_PROXY) are not loaded
- Database credentials are missing

### Directory Awareness (Critical for Claude)
- **ALWAYS use absolute paths** - Never use relative paths like `../swf-monitor`
- **ALWAYS run `pwd` before any file operations** - Claude frequently loses track of current directory
- **NEVER assume your location** - explicitly verify with `pwd` at start of file access attempts
- **Use full paths**: `/eic/u/wenauseic/github/swf-testbed` not `swf-testbed`
- This is a recurring Claude issue that causes confusion and wasted time

### Git Branch Management
- **ALWAYS use `git push -u origin branch-name` on first push** - this is non-negotiable
- After pushing, verify tracking with `git branch -vv` - should show `[origin/branch-name]`
- If tracking is missing, fix immediately with: `git branch --set-upstream-to=origin/branch-name branch-name`
- VS Code "Publish branch" button indicates missing tracking - this must be resolved

### Commit and Push Workflow
1. Create commits with descriptive messages including Claude Code attribution
2. First push: `git push -u origin branch-name` (sets up tracking)
3. Subsequent pushes: `git push` (tracking already established)
4. Always verify tracking is set up correctly before proceeding

## 📝 Example Agent Environment Auto-Loading Pattern

**ALL example agent scripts should include environment auto-loading like the test scripts:**

```python
#!/usr/bin/env python3
import os
import sys
from pathlib import Path

def setup_environment():
    """Auto-activate venv and load environment variables."""
    script_dir = Path(__file__).resolve().parent.parent  # Go up to swf-testbed root
    
    # Auto-activate virtual environment if not already active
    if "VIRTUAL_ENV" not in os.environ:
        venv_path = script_dir / ".venv"
        if venv_path.exists():
            print("🔧 Auto-activating virtual environment...")
            venv_python = venv_path / "bin" / "python"
            if venv_python.exists():
                os.environ["VIRTUAL_ENV"] = str(venv_path)
                os.environ["PATH"] = f"{venv_path}/bin:{os.environ['PATH']}"
                sys.executable = str(venv_python)
        else:
            print("❌ Error: No Python virtual environment found")
            return False
    
    # Load ~/.env environment variables (they're already exported)
    env_file = Path.home() / ".env"
    if env_file.exists():
        print("🔧 Loading environment variables from ~/.env...")
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    if line.startswith('export '):
                        line = line[7:]  # Remove 'export '
                    key, value = line.split('=', 1)
                    os.environ[key] = value.strip('"\'')
    
    return True

if __name__ == "__main__":
    if not setup_environment():
        sys.exit(1)
    
    # Your agent code here...
```

**This pattern ensures:**
- Virtual environment is automatically activated
- All ~/.env variables are loaded (NO_PROXY, SWF_MONITOR_HTTP_URL, etc.)
- Scripts work regardless of how they're invoked
- No more "command not found" or proxy failures