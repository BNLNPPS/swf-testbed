# Workflow Implementation Guide

## Fast Processing Workflows (TOML + Python+SimPy)

### Configuration Format
```toml
# workflows/epic_fast_10_workers.toml
[workflow]
name = "epic_fast_processing"
version = "1.0"

[parameters]
worker_count = 10
stf_interval_sec = 2.0
target_processing_sec = 30
sample_fraction = 0.1
physics_duration_min = 60

[infrastructure]
activemq_streams = 10
node_parallelism = 10
retry_max_attempts = 3
```

### STF Processing Workflow (Current DAQ Pattern)
```python
# workflows/stf_processing.py
class WorkflowExecutor:
    def __init__(self, parameters):
        self.parameters = parameters

    def execute(self, env):
        yield from self.run_daq_cycle(env)

    def run_daq_cycle(self, env):
        """Complete DAQ cycle following current state transitions"""
        yield from self.broadcast_run_imminent(env)
        yield from self.broadcast_run_start(env)
        yield from self.generate_stfs_during_physics(env)
        yield from self.broadcast_run_end(env)

    def broadcast_run_imminent(self, env):
        # Send run_imminent message
        yield env.timeout(1)

    def broadcast_run_start(self, env):
        # Send start_run message
        yield env.timeout(1)

    def generate_stfs_during_physics(self, env):
        interval = self.parameters.get('stf_interval_sec', 2.0)
        duration = self.parameters.get('physics_duration_min', 60) * 60

        start_time = env.now
        while env.now - start_time < duration:
            yield env.timeout(interval)
            yield from self.generate_stf(env)

    def broadcast_run_end(self, env):
        # Send end_run message
        yield env.timeout(1)

    def generate_stf(self, env):
        # Generate STF and send stf_gen message
        yield env.timeout(0.1)
```

### Fast Processing Workflow
```python
# workflows/fast_processing.py
class WorkflowExecutor:
    def __init__(self, parameters):
        self.parameters = parameters

    def execute(self, env):
        yield from self.run_preparation_phase(env)
        yield from self.stf_generation_loop(env)

    def run_preparation_phase(self, env):
        worker_count = self.parameters['worker_count']
        # Setup workers and streams
        yield env.timeout(1)

    def stf_generation_loop(self, env):
        interval = self.parameters['stf_interval_sec']
        duration = self.parameters['physics_duration_min'] * 60

        start_time = env.now
        while env.now - start_time < duration:
            yield env.timeout(interval)
            yield from self.generate_stf_with_workers(env)

    def generate_stf_with_workers(self, env):
        # STF generation with worker assignment
        yield env.timeout(0.1)
```

## Workflow Management

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
    execution_id = models.CharField(primary_key=True, max_length=100)  # e.g. "epic-fast-wenauseic-123"
    workflow_definition = models.ForeignKey(WorkflowDefinition, on_delete=CASCADE)
    parameter_values = models.JSONField()  # Actual values used for this execution
    performance_metrics = models.JSONField(null=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True)
    status = models.CharField(max_length=20)  # running, completed, failed
    executed_by = models.CharField(max_length=100)
```

### Command Line Interface
```bash
# Run workflow by name - auto-registers if not in DB
swf-testbed run-workflow stf_processing --version 1.0

# Override specific parameters
swf-testbed run-workflow epic_fast_processing --version 1.0 --worker-count 25

# Use local TOML file (takes priority over DB)
swf-testbed run-workflow epic_fast_processing --config ./my_config.toml
```

### Dynamic Workflow Loading with Auto-Registration
```python
# workflows/workflow_runner.py
class WorkflowRunner:
    def run_by_name(self, workflow_name, version, parameter_overrides=None):
        try:
            # Try to get workflow definition from database
            definition = WorkflowDefinition.objects.get(
                workflow_name=workflow_name,
                version=version
            )
        except WorkflowDefinition.DoesNotExist:
            # Auto-register workflow from file
            definition = self.register_workflow_from_file(workflow_name, version)

        # Load parameter values (DB defaults + overrides)
        parameters = definition.parameter_values.copy()
        if parameter_overrides:
            parameters.update(parameter_overrides)

        # Execute workflow definition code dynamically
        workflow_code = definition.definition
        exec_globals = {'simpy': simpy}
        exec(workflow_code, exec_globals)

        # Instantiate workflow
        workflow_class = exec_globals['WorkflowExecutor']
        executor = workflow_class(parameters)

        # Create execution record
        execution_id = self.generate_execution_id(workflow_name)
        execution = WorkflowExecution.objects.create(
            execution_id=execution_id,
            workflow_definition=definition,
            parameter_values=parameters,
            start_time=timezone.now(),
            status='running',
            executed_by=getpass.getuser()
        )

        return executor

    def register_workflow_from_file(self, workflow_name, version):
        """Auto-register workflow from workflows/ directory"""
        workflow_file = f"workflows/{workflow_name}.py"
        config_file = f"workflows/{workflow_name}_default.toml"

        with open(workflow_file) as f:
            definition_code = f.read()

        if os.path.exists(config_file):
            with open(config_file) as f:
                parameter_values = toml.load(f)
        else:
            parameter_values = {}

        definition = WorkflowDefinition.objects.create(
            workflow_name=workflow_name,
            version=version,
            workflow_type=workflow_name,
            definition=definition_code,
            parameter_values=parameter_values,
            created_by=getpass.getuser()
        )
        return definition

def generate_execution_id(workflow_name):
    """Generate human-readable execution ID like agent IDs"""
    username = getpass.getuser()
    next_id = get_next_execution_id()  # From persistent state
    return f"{workflow_name}-{username}-{next_id}"
```

## Directory Structure
```
workflows/
├── stf_processing.py                    # Current DAQ workflow pattern
├── stf_processing_default.toml          # Default parameters for STF processing
├── epic_fast_10_workers.toml
├── epic_fast_25_workers.toml
├── epic_fast_50_workers.toml
├── fast_processing.py
├── workflow_runner.py
└── config_validator.py
```

## New Workflow Simulator
```python
# example_agents/workflow_simulator.py
class WorkflowSimulator:
    def __init__(self, env, workflow_name, version=None, config_file=None):
        self.env = env
        self.runner = WorkflowRunner()

        if config_file:
            # Use local TOML file (takes priority)
            self.config = toml.load(config_file)
            self.workflow_executor = self.load_from_config()
        else:
            # Load workflow from database (auto-registers if needed)
            self.workflow_executor = self.runner.run_by_name(workflow_name, version)

    def run_simulation(self):
        """Run simulation using loaded workflow"""
        yield from self.workflow_executor.execute(self.env)

    def load_from_config(self):
        # Load workflow definition based on config
        workflow_name = self.config['workflow']['name']
        return self.runner.load_workflow_from_config(self.config)
```