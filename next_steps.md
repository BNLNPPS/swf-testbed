# Next Steps - Streaming Workflow Testbed

**Last Updated:** 2025-12-23
**Branch:** infra/baseline-v26

---

## 1. Test Fast Processing Agent - DONE (2025-12-23)

Verified: RunState created, 5% sampling, 15 TFSlices/sample, slices sent to queue.
Start agent BEFORE simulator.

```bash
# Terminal 1: Start workflow simulator (use --realtime for proper pacing)
cd /eic/u/wenauseic/github/swf-testbed && source .venv/bin/activate && source ~/.env
python workflows/workflow_simulator.py stf_datataking --config fast_processing_default --duration 120 --realtime

# Terminal 2: Start fast processing agent
cd /eic/u/wenauseic/github/swf-testbed && source .venv/bin/activate && source ~/.env
python example_agents/fast_processing_agent.py --debug
```

**Note:** The `--realtime` flag is essential when testing with downstream agents.
Without it, the workflow runs in fast simulation mode (completing instantly),
which doesn't allow agents time to process messages.

Verify:
- Agent receives `run_imminent`, queries WorkflowExecution API
- `RunState` record created in database
- `stf_gen` messages sampled per `stf_sampling_rate` (5%)
- `TFSlice` records created and pushed to `/queue/panda.transformer.slices`

---

## 2. Verify Artemis Queue Configuration

Ensure `/queue/panda.transformer.slices` exists in Artemis broker config.

Reference: https://github.com/wguanicedew/documents/blob/main/artemis/configure.md

---

## 3. Transformer Worker Integration

Workers consume from `/queue/panda.transformer.slices`:
- One message per worker (load-balanced by Artemis)
- Worker processes slice, sends result, ACKs message
- Worker completion updates `TFSlice` status via API

Message format (per Wen's iDDS design):
```python
{
    'msg_type': 'slice',
    'run_id': run_id,
    'created_at': timestamp,
    'content': {
        'req_id': uuid,
        'filename': stf_filename,
        'start': tf_first,
        'end': tf_last,
        ...
    }
}
```

---

## 4. Monitor UI for Fast Processing

Add views for:
- `RunState` - current run phase/state, worker counts, slice statistics
- `TFSlice` - slice status (queued/processing/completed/failed)
- `SystemStateEvent` - event log for debugging/replay

---

## Reference

- Fast processing config: `workflows/fast_processing_default.toml`
- Message formats: https://github.com/wguanicedew/iDDS/blob/dev/main/prompt.md
- Queue pattern: topic broadcast for workflow messages, queue for slice distribution
