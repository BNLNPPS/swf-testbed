# Bootstrap Guide for Claude

**Date:** 2025-12-23
**Branch:** infra/baseline-v26 (all 3 repos)

## Project Overview

ePIC Streaming Workflow Testbed - prototypes streaming computing workflows from DAQ (E0) through processing at E1 facilities (BNL/JLab).

**Core Repositories** (siblings in /eic/u/wenauseic/github/):
- **swf-testbed** - orchestration, CLI, workflows, example agents
- **swf-monitor** - Django web app, REST API, database models
- **swf-common-lib** - BaseAgent class, shared utilities

**Architecture:** Agent-based with ActiveMQ messaging. Agents inherit from BaseAgent.

## Current System

- **Host:** pandaserver02.sdcc.bnl.gov
- **Services:** PostgreSQL, Artemis (ActiveMQ), Redis - all system services
- **Django:** Production deployment at /opt/swf-monitor, accessed via Apache
- **Deploy:** `sudo bash /eic/u/wenauseic/github/swf-monitor/deploy-swf-monitor.sh branch infra/baseline-v26`

## Recent Work (This Session)

1. **Added --realtime flag** to workflow_simulator.py
   - Without it: SimPy runs instantly (120 sec sim in ~2 sec)
   - With it: Uses RealtimeEnvironment (1 sim sec = 1 wall sec)
   - Essential for testing with downstream agents

2. **Tested fast_processing_agent.py** - WORKING
   - Receives workflow messages from epictopic
   - Creates RunState in database
   - Samples STFs at 5%, creates 15 TFSlices per sample
   - Sends slices to `/queue/panda.transformer.slices`
   - NOTE: Start agent BEFORE simulator

## Artemis Queue Config - DONE (2025-12-23)

**Location:** /var/lib/swfbroker/etc/broker.xml

Configured correctly:
- `/queue/panda.transformer.slices` → **anycast** (workers compete)
- `/topic/panda.transformer.slices.monitor` → **multicast** (monitor sees all)
- Divert copies messages from queue to monitor topic

See: [docs/artemis-queue-configuration.md](docs/artemis-queue-configuration.md)

## Key Files

**Workflows:**
- workflows/workflow_simulator.py - CLI to run workflows
- workflows/workflow_runner.py - SimPy execution engine
- workflows/stf_datataking.py - DAQ state machine workflow
- workflows/fast_processing_default.toml - config (5% sampling, 15 slices/sample)

**Agents:**
- example_agents/fast_processing_agent.py - samples STFs, creates TF slices
- swf-common-lib/src/swf_common_lib/base_agent.py - base class

**Monitor:**
- swf-monitor/src/monitor_app/models.py - RunState, TFSlice, Worker, etc.
- swf-monitor/src/monitor_app/api_urls.py - REST endpoints

## Running Tests

```bash
# Terminal 1: Start agent FIRST
cd /eic/u/wenauseic/github/swf-testbed && source .venv/bin/activate && source ~/.env
python example_agents/fast_processing_agent.py --debug

# Terminal 2: Start simulator
python workflows/workflow_simulator.py stf_datataking --config fast_processing_default --duration 120 --realtime
```

## Next Steps (from next_steps.md)

1. ~~Test Fast Processing Agent~~ - DONE
2. ~~Artemis queue config (anycast vs multicast)~~ - DONE
3. Transformer Worker integration
4. Monitor UI for fast processing views

## Critical Rules

- Always activate venv: `source .venv/bin/activate && source ~/.env`
- All 3 repos must be on same branch (currently v26)
- Commit to branch, never main directly
- Redeploy swf-monitor after Django changes
- Never delete without explicit permission
