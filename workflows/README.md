# Workflows

## Starting Workflows

```bash
testbed run                     # Uses testbed.toml
testbed run fast_processing     # Uses fast_processing_default.toml
```

**NEVER** run agents directly with `python` or `nohup`. Use `testbed run`.

## Debugging

Use MCP tools, not log files:
```
list_logs(instance_name='daq_simulator-agent-user-123')
list_logs(level='ERROR')                                   # Find failures
list_messages(execution_id='stf_datataking-user-0044')
```

## Files

- `testbed.toml` - Main testbed configuration
- `*_default.toml` - Workflow-specific configs
- `workflow_runner.py` - Persistent agent (started by supervisord)
- `stf_datataking.py` - SimPy workflow definition
- `orchestrator.py` - Starts agents via supervisord, triggers workflows

## ActiveMQ Destinations

Always use explicit prefix:
- `/queue/name` - anycast (one consumer)
- `/topic/name` - multicast (all consumers)

**NEVER** use bare names like `'epictopic'`.
