# Workflow Orchestration Framework

## Overview

The Workflow Orchestration Framework provides a structured approach for defining, executing, and monitoring complex multi-step processes using TOML configuration, Python+SimPy execution logic, and database persistence.

## Configuration Format
```toml
# workflows/stf_processing_default.toml
[workflow]
name = "stf_processing"
version = "1.0"

[parameters]
no_beam_not_ready_delay = 10
broadcast_delay = 1
beam_not_ready_delay = 5
beam_ready_delay = 2
physics_period_count = 3
physics_period_duration = 180
standby_duration = 30
beam_not_ready_end_delay = 5
stf_interval = 2
stf_generation_time = 0.1
```

## STF Processing Workflow Implementation

The reference implementation demonstrates the complete DAQ cycle with state transitions:

```python
# workflows/stf_processing.py
class WorkflowExecutor:
    def __init__(self, parameters):
        self.parameters = parameters
        self.stf_sequence = 0

    def execute(self, env):
        # State 1: no_beam / not_ready (Collider not operating)
        yield env.timeout(self.parameters['no_beam_not_ready_delay'])

        # State 2: beam / not_ready (Run start imminent) + broadcast run imminent
        yield env.timeout(self.parameters['broadcast_delay'])  # broadcast_run_imminent
        yield env.timeout(self.parameters['beam_not_ready_delay'])

        # State 3: beam / ready (Ready for physics)
        yield env.timeout(self.parameters['beam_ready_delay'])

        # Physics periods loop with standby between them
        period = 0
        while self.parameters['physics_period_count'] == 0 or period < self.parameters['physics_period_count']:
            # Broadcast appropriate message
            if period == 0:
                yield env.timeout(self.parameters['broadcast_delay'])  # broadcast_run_start
            else:
                yield env.timeout(self.parameters['broadcast_delay'])  # broadcast_resume_run

            # STF generation during physics
            yield from self.generate_stfs_during_physics(env, self.parameters['physics_period_duration'])

            period += 1

            # Standby between physics periods (always for infinite mode, except after last for finite mode)
            if self.parameters['physics_period_count'] == 0 or period < self.parameters['physics_period_count']:
                yield env.timeout(self.parameters['broadcast_delay'])  # broadcast_pause_run
                yield env.timeout(self.parameters['standby_duration'])

        # State 7: beam / not_ready + broadcast run end
        yield env.timeout(self.parameters['broadcast_delay'])  # broadcast_run_end
        yield env.timeout(self.parameters['beam_not_ready_end_delay'])

    def generate_stfs_during_physics(self, env, duration_seconds):
        interval = self.parameters['stf_interval']
        start_time = env.now

        while (env.now - start_time) < duration_seconds:
            yield from self.generate_single_stf(env)

            # Only wait for interval if not at end of physics period
            if (env.now - start_time) < duration_seconds:
                yield env.timeout(interval)

    def generate_single_stf(self, env):
        self.stf_sequence += 1
        generation_time = self.parameters['stf_generation_time']
        yield env.timeout(generation_time)
```

## Fast Processing Workflow Implementation

The fast processing workflow simulates near real-time processing of STF samples using parallel workers for shifter monitoring. See [docs/fast-processing.md](fast-processing.md) for complete architectural details.

### Configuration

```toml
# workflows/fast_processing_default.toml
[workflow]
name = "fast_processing"
version = "1.0"

[parameters]
# Run configuration
run_duration = 600              # Total run duration (seconds)
target_worker_count = 30        # Target number of workers

# STF and sampling
stf_rate = 0.5                  # STF generation rate (Hz)
stf_sampling_rate = 0.05        # FastMon sampling fraction (5%)

# Slice parameters
slices_per_sample = 15          # TF slices per STF sample
slice_processing_time = 30      # Processing time per slice (seconds)

# Worker lifecycle
worker_rampup_time = 300        # Worker startup time (seconds)
worker_rampdown_time = 60       # Graceful shutdown time (seconds)
```

### Workflow Phases

The implementation models the three-phase fast processing workflow:

**Phase 1: Run Imminent**
- Broadcast run imminent message
- Ramp up workers (staggered deployment over `worker_rampup_time`)
- Workers establish connections and prepare for slice assignment

**Phase 2: Run Running**
- Broadcast run start
- Generate STF samples at `stf_rate` (FastMon samples from STF files)
- Create `slices_per_sample` TF slices for each sample
- Workers process slices in parallel (~30 sec per slice)
- Continue for `run_duration`

**Phase 3: Run End**
- Broadcast run end message
- Workers enter soft-ending mode (finish current slices)
- Graceful shutdown over `worker_rampdown_time`

### Performance Metrics

With default parameters:
- STF rate: 0.5 Hz → 1 STF sample every 2 seconds
- Slices created: 15/sample × 0.5 Hz = 7.5 slices/sec
- Processing capacity: 30 workers ÷ 30 sec/slice = 1 slice/sec per worker
- Total capacity: 30 workers = real-time processing at 0.5 Hz

### Database Integration

During execution, the workflow populates:
- `RunState`: phase, worker counts, slice statistics
- `TFSlice`: individual slice tracking with status
- `Worker`: worker lifecycle and performance
- `SystemStateEvent`: complete event history for replay


## Workflow Management Framework

### Database Models
```python
class WorkflowDefinition(models.Model):
    workflow_name = models.CharField(max_length=200)
    version = models.CharField(max_length=50)
    workflow_type = models.CharField(max_length=100)  # e.g. "fast_processing", "stf_processing", "custom"
    definition = models.TextField(max_length=5000)  # Python code content
    parameter_values = models.JSONField()  # Default parameter values and schema
    created_by = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('workflow_name', 'version')

class WorkflowExecution(models.Model):
    execution_id = models.CharField(primary_key=True, max_length=100)  # e.g. "stf_processing-wenauseic-0001"
    workflow_definition = models.ForeignKey(WorkflowDefinition, on_delete=CASCADE)
    parameter_values = models.JSONField()  # Actual values used for this execution
    performance_metrics = models.JSONField(null=True)
    execution_environment = models.JSONField(null=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True)
    status = models.CharField(max_length=20)  # running, completed, failed
    executed_by = models.CharField(max_length=100)
    error_message = models.TextField(null=True)
    stack_trace = models.TextField(null=True)
```

### Running Workflows

The `WorkflowRunner` class provides the execution engine:

```python
from workflows.workflow_runner import WorkflowRunner

# Initialize with monitor URL and optional authentication
runner = WorkflowRunner(monitor_url="http://localhost:8002")

# Run workflow with default configuration
execution_id = runner.run_workflow('stf_processing')

# Override parameters
execution_id = runner.run_workflow(
    'stf_processing',
    duration=7200,  # 2 hours
    physics_period_count=5,
    stf_interval=1.5
)
```

### Execution ID Generation

Workflow executions use human-readable IDs following the pattern:
```
workflow-username-NNNN
```

For example: `stf_processing-wenauseic-0001`

The sequence numbers are generated atomically via the monitor API to ensure uniqueness.

## Directory Structure
```
workflows/
├── stf_processing.py                    # STF processing workflow implementation
├── stf_processing_default.toml          # Default parameters
├── fast_processing.py                   # Fast processing workflow implementation
├── fast_processing_default.toml         # Default parameters
└── workflow_runner.py                   # Workflow execution engine
```

## Web Interface

The monitor provides web-based workflow management:

- **Workflow Definitions**: View and manage workflow templates at `/workflows/`
- **Workflow Executions**: Monitor execution instances and their status
- **Execution Details**: View parameters, duration, and performance metrics

All workflow code and configuration data is displayed with syntax highlighting for improved readability.

## Integration with Agent Infrastructure

Workflows integrate seamlessly with the existing agent-based messaging system while providing structured execution patterns for complex multi-step processes.