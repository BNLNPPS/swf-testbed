# Bootstrap Guide for Claude

**Date:** 2025-12-29
**Branch:** infra/baseline-v26 (all 3 repos)

## Project Overview

ePIC Streaming Workflow Testbed - agent-based system with ActiveMQ messaging.

**Core Repositories** (siblings in /eic/u/wenauseic/github/):
- **swf-testbed** - workflows, example agents, CLI
- **swf-monitor** - Django web app, REST API
- **swf-common-lib** - BaseAgent class, shared utilities

**Host:** pandaserver02.sdcc.bnl.gov (system PostgreSQL, Artemis, Redis)

## Namespace Feature (IMPLEMENTED)

Messages include `sender` (unique agent name) and `namespace` (user-defined testbed instance). Agents filter by namespace.

**Config:** `testbed.toml` with `[testbed]` section, `namespace = ""` (must set before running)

**Usage:**
```bash
# Set namespace in config
vi workflows/testbed.toml  # namespace = "my-namespace"

# Run workflow
python workflows/workflow_simulator.py stf_datataking \
    --testbed-config workflows/testbed.toml \
    --workflow-config fast_processing_default --realtime

# Run agent (separate terminal)
python example_agents/fast_processing_agent.py \
    --testbed-config example_agents/testbed.toml
```

## Next Tasks

1. Test end-to-end with namespace configured
2. Consider implementing `[parameters]` override merging in workflow_runner.py

## Key Files

- `workflows/workflow_simulator.py` - CLI to run workflows
- `workflows/workflow_runner.py` - SimPy execution engine
- `example_agents/*.py` - all accept `--testbed-config`
- `swf-common-lib/.../base_agent.py` - namespace injection/filtering
- `swf-common-lib/.../config_utils.py` - testbed config loader

## Critical Rules

- Activate venv: `source .venv/bin/activate && source ~/.env`
- All 3 repos on same branch (v26)
- Commit to branch, never main
- Redeploy swf-monitor after Django changes
- Never delete without permission
- Fail fast and loud - no defensive silent failures
