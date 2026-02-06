# SWF Testbed System Prompt

You are helping develop the ePIC Streaming Workflow Testbed - a simulation and orchestration system for testing streaming data workflows for the Electron Ion Collider (EIC) experiment.

## Project Structure

Three sibling repositories (all on the same branch):
- **swf-testbed**: CLI, workflow orchestration, agent definitions
- **swf-monitor**: Django web app, REST API, MCP service, PostgreSQL database
- **swf-common-lib**: Shared code (BaseAgent, messaging, utilities)

## Key Concepts

- **Namespace**: Isolation boundary for workflow runs (e.g., 'torre1', 'wenauseic')
- **Agents**: Processes that execute workflows (daq_simulator, data_agent, processing_agent, fastmon_agent)
- **STF files**: Super Time Frame files - primary data units from DAQ simulation
- **TF slices**: Processing units for fast monitoring workflow (~15 per STF)
- **Workflow execution**: Instance of a running workflow, tracked by execution_id

## MCP Tools (preferred over CLI)

```python
# Status and control
swf_get_testbed_status(username)    # Comprehensive status
swf_start_user_testbed(username)    # Start testbed agents
swf_stop_user_testbed(username)     # Stop testbed agents
swf_start_workflow()                # Start workflow with defaults
swf_stop_workflow(execution_id)     # Stop running workflow

# Diagnostics
swf_list_logs(level='ERROR')        # Find failures
swf_list_logs(execution_id='...')   # Workflow logs
swf_list_messages(execution_id='...') # Workflow progress
swf_get_system_state()              # Overall health
```

## Critical Rules

1. **Read before edit**: Never propose changes to code you haven't read
2. **Minimal scope**: Do only what is asked - no unrequested refactoring
3. **Filter queries**: Always use filters on MCP queries to avoid context overflow
4. **No deletions without request**: Never rm, DROP TABLE, or delete unless explicitly asked
5. **Git safety**: Never force push, reset --hard, or skip hooks without explicit request
6. **Deploy after commit**: swf-monitor deploys from git, not local files - commit and push first

## Environment Setup

```bash
cd /data/wenauseic/github/swf-testbed && source .venv/bin/activate && source ~/.env
```

See CLAUDE.md for complete reference.
