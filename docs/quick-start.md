# Quick Start Guide

Minimal setup for experienced users who want to get the testbed running quickly.

## Prerequisites

- Docker Desktop (running)
- Python 3.8+
- Git

## One-Command Setup

```bash
# Clone repos, install Docker, then:
cd swf-testbed
docker-compose up -d
cd ../swf-monitor && cp .env.example .env  # Edit DB_PASSWORD='admin'
cd ../swf-testbed
source .venv/bin/activate
pip install -e ../swf-common-lib ../swf-monitor .
swf-testbed init
cd ../swf-monitor/src && python manage.py createsuperuser && cd ../../swf-testbed
../swf-monitor/start_django_dual.sh &  # Start monitor (HTTP:8002, HTTPS:8443)
swf-testbed start
```

## Configure Namespace

Before running workflows, set your namespace in `workflows/testbed.toml`:

```toml
[testbed]
namespace = "your-namespace"  # e.g., "myname-dev", "team-test1"
```

This isolates your workflows from others in the system.

## Verification

**Check these URLs work:**
- Monitor: http://localhost:8002/
- ActiveMQ: http://localhost:8161/admin/ (admin/admin)

**Run a processing agent test (two terminals):**
```bash
# Terminal 1: Workflow simulator
cd swf-testbed && source .venv/bin/activate && source ~/.env
python workflows/workflow_simulator.py stf_datataking --workflow-config fast_processing_default --stf-count 5 --realtime

# Terminal 2: Processing agent
cd swf-testbed && source .venv/bin/activate && source ~/.env
python example_agents/example_processing_agent.py
```

**Check STF files appear:**
- http://localhost:8002/stf-files/

## Fast Processing Test

**Run a fast processing test (two terminals):**
```bash
# Terminal 1: Workflow simulator
cd swf-testbed && source .venv/bin/activate && source ~/.env
python workflows/workflow_simulator.py stf_datataking --workflow-config fast_processing_default --stf-count 5 --realtime

# Terminal 2: Fast processing agent
cd swf-testbed && source .venv/bin/activate && source ~/.env
python example_agents/fast_processing_agent.py --testbed-config workflows/testbed.toml
```

**Check results:**
- TF Slices: http://localhost:8002/tf-slices/
- Run States: http://localhost:8002/run-states/

## Key Environment Variables

Add to `~/.env`:
```bash
# Required for BNL/corporate proxy environments
export NO_PROXY=localhost,127.0.0.1,0.0.0.0

# Monitor configuration  
export SWF_MONITOR_URL=https://localhost:8443      # API calls
export SWF_MONITOR_HTTP_URL=http://localhost:8002  # Logging
export SWF_API_TOKEN=<get_from_django_admin>
```

## Common Issues

- **STF files empty**: Monitor not serving HTTPS → Use `start_django_dual.sh`
- **Proxy timeouts**: Add `NO_PROXY` to `~/.env`
- **ActiveMQ connection failed**: Check Docker services running

For detailed setup: [Installation Guide](installation.md)
For troubleshooting: [Troubleshooting](troubleshooting.md)