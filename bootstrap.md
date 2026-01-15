# Bootstrap Guide for LLMs

**Attention AIs:** This is not a chronicle of completed work. This is quick essential background to current status and next steps.
Be concise and to the point. When something is done and isn't essential background for next steps, remove it.

**Repos** (siblings in /data/wenauseic/github/):
- **swf-testbed** - workflows, example agents
- **swf-monitor** - Django web app, REST API, MCP service
- **swf-common-lib** - BaseAgent class

**Host:** pandaserver02.sdcc.bnl.gov

## Current Status

**Per-user config override implemented via SWF_TESTBED_CONFIG env var:**
- User's ~/.env sets: `export SWF_TESTBED_CONFIG=fast_processing_default.toml`
- BaseAgent (swf-common-lib) resolves config: env var > default `workflows/testbed.toml`
- Agent argparse defaults to None, BaseAgent handles resolution
- agents.supervisord.conf no longer passes --testbed-config
- Agent manager auto-loads config from env var on startup

**Signal handling added to BaseAgent:**
- SIGTERM/SIGQUIT handlers raise KeyboardInterrupt for graceful shutdown
- Agents now properly report EXITED status when stopped

**Current issue - testbed partially started:**
- Agent manager: OK, namespace=torre2 (correct)
- Workflow runner (daq_simulator-agent-460): OK, namespace=torre2 (correct)
- BUT: data agent, fastmon agent, fast_processing agent did NOT start
- No errors in logs

## Next Steps

1. **Debug why other agents didn't start** - check supervisord status, agent manager logs (file logs, not REST)
2. **Once agents running**, test the fast processing pipeline:
   - DAQ Simulator [stf_gen] -> Data Agent [stf_ready] -> FastMon Agent [tf_file_registered] -> Fast Processing Agent [slice]
3. Verify namespace=torre2 throughout the pipeline
