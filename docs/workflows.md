# Workflow Orchestration Framework

## Overview

The Workflow Orchestration Framework provides a structured approach for defining, executing, and monitoring complex multi-step processes using TOML configuration, Python+SimPy execution logic, ActiveMQ messaging, and database persistence.

**Key Architecture Principles:**
- **One Workflow, Multiple Configurations**: The same DAQ datataking workflow serves different downstream processing strategies through TOML configuration
- **Configuration Composition**: TOML configs can include base configurations for reusability
- **ActiveMQ Messaging**: Workflows broadcast real messages that agents respond to
- **Database as Truth**: Fully expanded configurations stored in database for reproducibility
- **Agent-Driven Processing**: Workflows simulate DAQ; agents implement downstream processing logic

## Configuration Format and Composition

### Basic Configuration
```toml
# workflows/stf_processing_default.toml
[workflow]
name = "stf_datataking"
version = "1.0"
description = "STF datataking workflow for standard processing"
includes = ["daq_state_machine.toml"]

[stf_processing]
# Uses daq_state_machine defaults; add stf_processing-specific values here
```

### Configuration Composition via Includes

Configurations support composition through the `includes` directive. Each config file uses a descriptive section name (e.g., `[daq_state_machine]`, `[fast_processing]`) that identifies the component:

```toml
[workflow]
name = "stf_datataking"
version = "1.0"
includes = ["daq_state_machine.toml"]

[fast_processing]
# Values here override daq_state_machine values and add fast_processing-specific config
stf_count = 10
target_worker_count = 30
```

**Loading Order:**
1. Include files load in array order
2. Later includes override earlier ones
3. Main config parameters have final say

**Database Storage:**
The fully expanded configuration (with all includes merged) is saved to the database, ensuring execution records are complete snapshots with no external file dependencies.

## STF Datataking Workflow Implementation

The unified STF datataking workflow simulates the ePIC DAQ state machine, broadcasting ActiveMQ messages that downstream agents respond to. The same workflow code serves both standard STF processing and fast processing - configuration determines the behavior.

### Workflow Code

```python
# workflows/stf_datataking.py
class WorkflowExecutor:
    def __init__(self, config, runner, execution_id):
        self.config = config
        self.runner = runner  # WorkflowRunner instance (BaseAgent)
        self.execution_id = execution_id
        self.stf_sequence = 0
        self.run_id = None

        # Build merged params: daq_state_machine base, with workflow-specific overrides
        self.daq = config.get('daq_state_machine', {})
        for section in ['fast_processing', 'stf_processing']:
            if section in config:
                self.daq = {**self.daq, **config[section]}

    def execute(self, env):
        # Generate run ID for this execution
        from swf_common_lib.api_utils import get_next_run_number
        self.run_id = get_next_run_number(
            self.runner.monitor_url,
            self.runner.api_session,
            self.runner.logger
        )

        # State 1: no_beam / not_ready (Collider not operating)
        yield env.timeout(self.daq['no_beam_not_ready_delay'])

        # State 2: beam / not_ready (Run start imminent)
        yield env.process(self.broadcast_run_imminent(env))
        yield env.timeout(self.daq['broadcast_delay'])
        yield env.timeout(self.daq['beam_not_ready_delay'])

        # State 3: beam / ready (Ready for physics)
        yield env.timeout(self.daq['beam_ready_delay'])

        # Physics periods loop with standby between them
        period = 0
        while self.daq['physics_period_count'] == 0 or period < self.daq['physics_period_count']:
            # Broadcast start or resume message
            if period == 0:
                yield env.process(self.broadcast_run_start(env))
            else:
                yield env.process(self.broadcast_resume_run(env))
            yield env.timeout(self.daq['broadcast_delay'])

            # STF generation during physics
            yield from self.generate_stfs_during_physics(env, self.daq['physics_period_duration'])

            period += 1

            # Standby between physics periods
            if self.daq['physics_period_count'] == 0 or period < self.daq['physics_period_count']:
                yield env.process(self.broadcast_pause_run(env))
                yield env.timeout(self.daq['broadcast_delay'])
                yield env.timeout(self.daq['standby_duration'])

        # State 7: beam / not_ready + broadcast run end
        yield env.process(self.broadcast_run_end(env))
        yield env.timeout(self.daq['broadcast_delay'])
        yield env.timeout(self.daq['beam_not_ready_end_delay'])

    def broadcast_stf_gen(self, env, stf_filename):
        """Broadcast STF generation via ActiveMQ."""
        message = {
            "msg_type": "stf_gen",
            "execution_id": self.execution_id,
            "run_id": self.run_id,
            "filename": stf_filename,
            "sequence": self.stf_sequence,
            "timestamp": datetime.now().isoformat(),
            "simulation_tick": env.now,
            "state": "run",
            "substate": "physics"
        }
        self.runner.send_message('epictopic', message)
        yield env.timeout(0.1)
```

**Key Features:**
- **ActiveMQ Messaging**: Broadcasts workflow events via `runner.send_message()`
- **Parameter Distribution**: Messages include `execution_id` for agents to query WorkflowExecution
- **8-State DAQ Machine**: Matches ePIC DAQ simulator state transitions
- **SimPy Timing**: Simulates timing for state transitions and STF generation

## Fast Processing Configuration

Fast processing uses the **same stf_datataking.py workflow** as standard STF processing, but with different configuration parameters. The distinction is in downstream agent behavior, not workflow code.

### Configuration

```toml
# workflows/fast_processing_default.toml
[workflow]
name = "stf_datataking"
version = "1.0"
description = "STF datataking workflow for fast processing"
includes = ["daq_state_machine.toml"]

[fast_processing]
# Count-based STF generation
stf_count = 10                  # Generate exactly 10 STF files
physics_period_count = 1        # Single physics period

# Fast processing parameters
target_worker_count = 30        # Target number of workers
stf_sampling_rate = 0.05        # FastMon sampling fraction (5%)
slices_per_sample = 15          # TF slices per STF sample
slice_processing_time = 30      # Processing time per slice (seconds)
worker_rampup_time = 300        # Worker startup time (5 min)
worker_rampdown_time = 60       # Graceful shutdown time (1 min)
```

### Agent-Driven Processing

The workflow broadcasts the same DAQ messages (`run_imminent`, `start_run`, `stf_gen`, `end_run`). The difference is in how agents respond:

**Standard STF Processing:**
- `processing_agent` processes complete STF files
- Creates PanDA tasks for full reconstruction

**Fast Processing:**
- `fastmon_agent` samples STF files, creates TF samples
- `fast_processing_agent` creates slices from TF samples
- Workers process slices for near real-time shifter monitoring

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

Workflows are executed via the `workflow_simulator.py` command-line tool:

```bash
# Run workflow with default configuration (fast simulation mode)
python workflows/workflow_simulator.py stf_datataking --config stf_processing_default --duration 60

# Run with fast processing configuration
python workflows/workflow_simulator.py stf_datataking --config fast_processing_default --duration 600

# Run in REAL-TIME mode (for testing with downstream agents)
python workflows/workflow_simulator.py stf_datataking --config fast_processing_default --duration 120 --realtime

# Override specific parameters
python workflows/workflow_simulator.py stf_datataking \
    --config stf_processing_default \
    --duration 3600 \
    --physics-period-count 5 \
    --physics-period-duration 600 \
    --stf-interval 1.5
```

**Command Line Arguments:**
- `workflow_name` - Name of workflow Python file (e.g., `stf_datataking`)
- `--config` - TOML configuration file name (without .toml extension)
- `--duration` - Simulation duration in seconds (default: 3600)
- `--realtime` - Run in real-time mode (see Simulation Modes below)
- `--physics-period-count` - Override physics period count
- `--physics-period-duration` - Override physics period duration (seconds)
- `--stf-interval` - Override STF generation interval (seconds)

### Simulation Modes

The workflow simulator supports two execution modes:

**Fast Simulation Mode (default)**
- SimPy discrete-event simulation runs as fast as possible
- A 120-second workflow completes in ~2 seconds of wall-clock time
- Useful for testing workflow logic and database integration
- Messages are broadcast instantly without timing constraints

**Real-Time Mode (`--realtime`)**
- Uses SimPy's `RealtimeEnvironment` to tie simulation time to wall-clock time
- A 120-second workflow takes ~120 seconds to complete
- Essential for testing with downstream agents (e.g., `fast_processing_agent`)
- Messages are paced realistically, allowing agents to process them in sequence
- Use `strict=False` to allow the simulation to catch up if it falls behind

**What Happens:**
1. `workflow_simulator.py` creates a WorkflowRunner instance
2. WorkflowRunner inherits from BaseAgent (connects to ActiveMQ, registers as agent)
3. Configuration files are loaded with includes merged
4. Fully expanded config saved to WorkflowDefinition and WorkflowExecution
5. Workflow broadcasts ActiveMQ messages during execution
6. Downstream agents receive messages and query WorkflowExecution for parameters

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
├── stf_datataking.py                    # Unified DAQ datataking workflow
├── daq_state_machine.toml               # Base DAQ parameters (included by others)
├── stf_processing_default.toml          # STF processing configuration
├── fast_processing_default.toml         # Fast processing configuration
├── workflow_runner.py                   # Workflow execution engine (BaseAgent)
└── workflow_simulator.py                # Command-line tool to run workflows
```

## Web Interface

The monitor provides web-based workflow management:

- **Workflow Definitions**: View and manage workflow templates at `/workflows/`
- **Workflow Executions**: Monitor execution instances and their status
- **Execution Details**: View parameters, duration, and performance metrics

All workflow code and configuration data is displayed with syntax highlighting for improved readability.

## Integration with Agent Infrastructure

Workflows integrate seamlessly with the agent-based messaging system:

**WorkflowRunner as Agent:**
- Inherits from `BaseAgent`
- Registers as `workflow_runner` agent type
- Sends messages to `epictopic` ActiveMQ topic
- Connects to monitor API for database operations

**Agent Communication:**
- Workflows broadcast DAQ state transition messages
- Messages include `execution_id` for parameter lookup
- Agents query `/api/workflow-executions/{execution_id}/` to get full parameters
- Same messages, different agent responses = different workflows

**Example Message Flow:**
1. WorkflowRunner broadcasts `run_imminent` with `execution_id`
2. `fast_processing_agent` receives message, queries WorkflowExecution
3. Agent extracts `target_worker_count`, `slices_per_sample` from parameters
4. Agent initiates worker preparation based on configuration
5. Workflow broadcasts `stf_gen` messages
6. Agent creates TF slices and distributes to workers

This architecture decouples workflow orchestration (DAQ simulation) from processing logic (agent behavior), enabling multiple downstream processing strategies with the same workflow code.