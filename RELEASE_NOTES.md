# Release Notes

## v26 (2025-12-31)

### Namespaces

Workflows now operate within **namespaces**, allowing users to isolate their work from others sharing the same infrastructure.

On shared systems like pandaserver02, multiple users can run workflows simultaneously. Namespaces let you filter the monitor UI to see only your workflows, agents, and messages, and avoid conflicts with other users.

Configure your namespace in `workflows/testbed.toml` before running any workflows:

```toml
[testbed]
namespace = "your-namespace"  # e.g., "alice-dev", "team-fastmon"
```

All workflow messages now include the namespace, and the monitor UI provides namespace filtering on agents, executions, and messages.

### Monitor UI

- **Namespace pages**: List and detail views; namespace column and filter on agents, executions, messages
- **Agent list**: Type and status filters; click agent to see detail
- **Agent detail**: Streamlined view linking to filtered workflow messages
- **Workflow messages**: execution_id and run_id filters; STF count column; click for message detail
- **Message detail**: Full message content view
- **Drill-down links**: Click execution_id, run_id, namespace, or agent anywhere to navigate to details
- **Source links**: GitHub links on workflow definition (branch) and execution (commit) pages

### Workflow Refinements

**Count-based workflow completion:** Workflows can now run until a specific number of STF files are generated, rather than requiring a duration limit:

```bash
python workflows/workflow_simulator.py stf_datataking \
    --workflow-config fast_processing_default \
    --stf-count 10
```

**Immutable definitions:** Workflow definitions are now immutable once created. The definition captures the source code and configuration at creation time. Each execution records its specific git version for reproducibility.

**Source traceability:** Workflow definitions now link to their source script on GitHub. Executions record the exact git commit, so you can always trace back to the code that ran.

### Fast Processing Support

New infrastructure for fast processing workflows that sample STF data for near real-time monitoring:

- **Fast processing agent** (`example_agents/fast_processing_agent.py`) creates TF slices from STF samples
- Configurable sampling rate, slices per sample, and processing time
- Agents can start mid-run and extract context from messages
- New monitor views: TF Slices (`/tf-slices/`) and Run States (`/run-states/`)

### Agent Improvements

- Agents now register using the workflow name as their type (e.g., `STF_Datataking` instead of generic `workflow_runner`)
- Retry logic for initial ActiveMQ connection improves reliability on startup
- Agent list in monitor now supports type and status filters

### Infrastructure

- Docker-compose updated with Redis and health checks
- Artemis queue configuration guide added (`docs/artemis-queue-configuration.md`)
- Fixed environment loading that was breaking git commands when `~/.env` contained PATH references

---

*For detailed technical changes, see the pull requests for [swf-testbed](https://github.com/BNLNPPS/swf-testbed/pulls), [swf-common-lib](https://github.com/BNLNPPS/swf-common-lib/pulls), and [swf-monitor](https://github.com/BNLNPPS/swf-monitor/pulls).*
