#!/usr/bin/env python3
"""
Workflow Runner - Executes workflow definitions with SimPy

Default mode: Persistent agent listening for workflow commands on 'workflow_control' queue.
CLI mode (--run-once): Execute single workflow and exit.
"""

import os
import re
import subprocess
import sys
import json
import tomllib
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any


def setup_environment():
    """Auto-activate venv and load environment variables."""
    script_dir = Path(__file__).resolve().parent.parent  # Go up to swf-testbed root

    # Auto-activate virtual environment if not already active
    if "VIRTUAL_ENV" not in os.environ:
        venv_path = script_dir / ".venv"
        if venv_path.exists():
            print("Auto-activating virtual environment...")
            venv_python = venv_path / "bin" / "python"
            if venv_python.exists():
                os.environ["VIRTUAL_ENV"] = str(venv_path)
                os.environ["PATH"] = f"{venv_path}/bin:{os.environ['PATH']}"
                sys.executable = str(venv_python)
        else:
            print("Error: No Python virtual environment found")
            return False

    # Load ~/.env environment variables
    env_file = Path.home() / ".env"
    if env_file.exists():
        print("Loading environment variables from ~/.env...")
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    if line.startswith('export '):
                        line = line[7:]
                    key, value = line.split('=', 1)
                    value = value.strip('"\'')
                    if '$' in value:
                        continue
                    os.environ[key] = value

    # Unset proxy variables for localhost connections
    for proxy_var in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
        if proxy_var in os.environ:
            del os.environ[proxy_var]

    return True


if __name__ == "__main__":
    if not setup_environment():
        sys.exit(1)

# Project imports (after environment setup)
import simpy
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "swf-common-lib" / "src"))
from swf_common_lib.base_agent import BaseAgent
from swf_common_lib.api_utils import ensure_namespace


def get_github_source_info(file_path: Path) -> Optional[Dict[str, str]]:
    """
    Discover GitHub source info for a file in a git checkout.
    Returns dict with org, repo, script_path, branch, or None if not in a git repo.
    """
    try:
        file_path = Path(file_path).resolve()
        file_dir = file_path.parent

        # Get git root
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            cwd=file_dir, capture_output=True, text=True
        )
        if result.returncode != 0:
            return None
        git_root = Path(result.stdout.strip())

        # Get remote URL
        result = subprocess.run(
            ['git', 'remote', 'get-url', 'origin'],
            cwd=git_root, capture_output=True, text=True
        )
        if result.returncode != 0:
            return None
        remote_url = result.stdout.strip()

        # Parse org/repo from URL (handles https and ssh formats)
        match = re.search(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$', remote_url)
        if not match:
            return None
        org, repo = match.groups()

        # Get relative path within repo
        script_path = str(file_path.relative_to(git_root))

        # Get current branch
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=git_root, capture_output=True, text=True
        )
        branch = result.stdout.strip() if result.returncode == 0 else 'main'

        return {
            'org': org,
            'repo': repo,
            'script_path': script_path,
            'branch': branch
        }
    except Exception:
        return None


def get_git_version(directory: Path) -> Optional[Dict[str, str]]:
    """
    Get git version info for a directory.
    Returns dict with commit, tag (if on tag), branch.
    """
    try:
        directory = Path(directory).resolve()

        # Get commit hash
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=directory, capture_output=True, text=True
        )
        if result.returncode != 0:
            return None
        commit = result.stdout.strip()

        # Get tag if on one
        result = subprocess.run(
            ['git', 'describe', '--tags', '--exact-match'],
            cwd=directory, capture_output=True, text=True
        )
        tag = result.stdout.strip() if result.returncode == 0 else None

        # Get branch
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=directory, capture_output=True, text=True
        )
        branch = result.stdout.strip() if result.returncode == 0 else None

        version_info = {'commit': commit}
        if tag:
            version_info['tag'] = tag
        if branch:
            version_info['branch'] = branch

        return version_info
    except Exception:
        return None


class WorkflowRunner(BaseAgent):
    """
    Loads, registers, and executes workflow definitions.

    Operates in two modes:
    - Persistent mode (default): Runs as agent listening for workflow commands
    - CLI mode (--run-once): Executes single workflow and exits
    """

    # Message types this agent handles
    COMMAND_MESSAGE_TYPES = {'run_workflow', 'stop_workflow', 'status_request'}

    def __init__(self, monitor_url: Optional[str] = None, debug: bool = False,
                 config_path: Optional[str] = None, workflow_name: Optional[str] = None):
        """
        Initialize WorkflowRunner as an agent

        Args:
            monitor_url: Optional override for SWF monitor URL (uses env if not provided)
            debug: Enable debug logging
            config_path: Path to testbed.toml config file
            workflow_name: Name of workflow to run (used for agent_type registration)
        """
        if workflow_name:
            agent_type = workflow_name.replace(' ', '_')
        else:
            agent_type = 'DAQ_Simulator'

        super().__init__(
            agent_type=agent_type,
            subscription_queue='/queue/workflow_control',
            debug=debug,
            config_path=config_path
        )

        # Track current workflow execution
        self.current_execution_id = None
        self.current_workflow_name = None
        self.workflow_thread = None
        self.stop_event = threading.Event()

        # Override monitor_url if provided
        if monitor_url:
            self.monitor_url = monitor_url.rstrip('/')

        # Use self.api from BaseAgent (already configured with auth)
        self.api_session = self.api
        self.workflows_dir = Path(__file__).parent  # workflows/ directory

        # Load testbed config overrides (all sections including [testbed] for namespace)
        self.testbed_overrides = {}
        if self.config_path:
            testbed_config_file = Path(self.config_path)
            if testbed_config_file.exists():
                with open(testbed_config_file, 'rb') as f:
                    testbed_config = tomllib.load(f)
                    for section, values in testbed_config.items():
                        if isinstance(values, dict):
                            self.testbed_overrides[section] = values

        # Connect to ActiveMQ (we only send, don't need to subscribe)
        self.conn.connect(
            self.mq_user,
            self.mq_password,
            wait=True,
            version='1.1',
            headers={
                'client-id': self.agent_name,
                'heart-beat': '30000,30000'
            }
        )
        self.mq_connected = True

        # Register agent in SystemAgent table
        self.send_heartbeat()

        self.logger.info(f"WorkflowRunner initialized and connected to ActiveMQ: {self.agent_name}")

    def run_workflow(self, workflow_name: str, config_name: Optional[str] = None,
                     duration: float = 3600, realtime: bool = False, **override_params) -> str:
        """
        Run a workflow by name

        Args:
            workflow_name: Name of the workflow (e.g., 'stf_processing')
            config_name: Name of config file (defaults to {workflow_name}_default.toml)
            duration: Simulation duration in seconds
            realtime: If True, run in real-time mode (1 sim second = 1 wall-clock second)
            **override_params: Parameters to override from config

        Returns:
            execution_id: The ID of the workflow execution
        """
        # Load workflow definition and config
        workflow_code = self._load_workflow_code(workflow_name)
        config = self._load_workflow_config(workflow_name, config_name)

        # Apply testbed config overrides (by section)
        for section, values in self.testbed_overrides.items():
            if section in config:
                config[section].update(values)
            else:
                config[section] = values

        # Apply CLI parameter overrides (highest priority) to all matching sections
        if override_params:
            for section, values in config.items():
                if section != 'workflow' and isinstance(values, dict):
                    for key, value in override_params.items():
                        if key in values:
                            values[key] = value

        # Generate execution ID
        executed_by = os.getenv('USER', 'unknown')
        execution_id = self._generate_execution_id(workflow_name, executed_by)

        # Track for status reporting
        self.current_execution_id = execution_id

        # Register/update workflow definition in database
        workflow_file = self.workflows_dir / f"{workflow_name}.py"
        self._register_workflow_definition(
            name=config['workflow']['name'],
            version=config['workflow']['version'],
            code=workflow_code,
            config=config,
            workflow_file=workflow_file
        )

        # Create execution record (store full config for auditability)
        self._create_execution_record(
            execution_id=execution_id,
            workflow_name=config['workflow']['name'],
            workflow_version=config['workflow']['version'],
            config=config
        )

        # Execute the workflow
        self._execute_workflow(
            execution_id=execution_id,
            workflow_code=workflow_code,
            config=config,
            duration=duration,
            realtime=realtime
        )

        # Update execution status to completed
        self._update_execution_status(execution_id, 'completed')

        return execution_id

    def _load_workflow_code(self, workflow_name: str) -> str:
        """Load workflow Python code from file"""
        workflow_file = self.workflows_dir / f"{workflow_name}.py"
        if not workflow_file.exists():
            raise FileNotFoundError(f"Workflow {workflow_name}.py not found in {self.workflows_dir}")

        with open(workflow_file, 'r') as f:
            return f.read()

    def _load_workflow_config(self, workflow_name: str, config_name: Optional[str] = None) -> Dict[str, Any]:
        """Load workflow TOML configuration with includes support.

        Config files use descriptive section names (e.g., [daq_state_machine], [fast_processing]).
        Included configs are loaded first, then main config sections are added/merged.
        Sections are kept intact for explicit access by workflow code.
        """
        if config_name is None:
            config_name = f"{workflow_name}_default.toml"
        elif not config_name.endswith('.toml'):
            config_name = f"{config_name}.toml"

        config_file = self.workflows_dir / config_name
        if not config_file.exists():
            raise FileNotFoundError(f"Config {config_name} not found in {self.workflows_dir}")

        # Load main config
        with open(config_file, 'rb') as f:
            main_config = tomllib.load(f)

        # Check for includes in workflow section
        includes = main_config.get('workflow', {}).get('includes', [])

        if not includes:
            return main_config

        # Load included configs and add their sections to main_config
        for include_file in includes:
            include_path = self.workflows_dir / include_file
            if not include_path.exists():
                raise FileNotFoundError(f"Included config {include_file} not found in {self.workflows_dir}")

            with open(include_path, 'rb') as f:
                included_config = tomllib.load(f)
                # Add each section from included file (don't overwrite existing)
                for section, values in included_config.items():
                    if section != 'workflow' and section not in main_config:
                        main_config[section] = values

        return main_config

    def _generate_execution_id(self, workflow_name: str, executed_by: str) -> str:
        """Generate human-readable execution ID"""
        # Get next ID from persistent state API
        response = self.api_session.post(
            f"{self.monitor_url}/api/state/next-workflow-execution-id/",
            json={'workflow_name': workflow_name}
        )

        if response.status_code == 200:
            data = response.json()
            sequence = data.get('sequence', 1)
        else:
            # NO RANDOM FALLBACK - get proper count from database
            print(f"WARNING: Persistent state API failed: {response.status_code}")
            count_response = self.api_session.get(
                f"{self.monitor_url}/api/workflow-executions/",
                params={'workflow_name': workflow_name}
            )
            if count_response.status_code == 200:
                count_data = count_response.json()
                if isinstance(count_data, dict) and 'results' in count_data:
                    sequence = len(count_data['results']) + 1
                elif isinstance(count_data, list):
                    sequence = len(count_data) + 1
                else:
                    sequence = 1
            else:
                print(f"ERROR: Cannot get execution count: {count_response.status_code}")
                raise Exception(f"Failed to generate execution ID - API unavailable")

        # Format: workflow-username-NNNN
        return f"{workflow_name}-{executed_by}-{sequence:04d}"

    def _register_workflow_definition(self, name: str, version: str, code: str, config: Dict[str, Any],
                                       workflow_file: Path = None):
        """Register or update workflow definition in database"""
        # Check if workflow definition already exists
        check_url = f"{self.monitor_url}/api/workflow-definitions/"
        check_response = self.api_session.get(
            check_url,
            params={'workflow_name': name, 'version': version}
        )

        # Discover GitHub source info from workflow file
        source_info = get_github_source_info(workflow_file) if workflow_file else None

        # Build expanded config for database storage
        expanded_config = {
            'workflow': {
                'name': config['workflow']['name'],
                'version': config['workflow']['version']
            }
        }
        if source_info:
            expanded_config['source'] = source_info
        # Preserve description if present
        if 'description' in config['workflow']:
            expanded_config['workflow']['description'] = config['workflow']['description']
        # Copy all parameter sections (daq_state_machine, fast_processing, etc.)
        for section, values in config.items():
            if section != 'workflow' and isinstance(values, dict):
                expanded_config[section] = values

        payload = {
            'workflow_name': name,
            'version': version,
            'workflow_type': 'simulation',
            'definition': code,
            'parameter_values': expanded_config,
            'created_by': os.getenv('USER', 'unknown'),
            'created_at': datetime.now().isoformat()
        }

        if check_response.status_code == 200:
            definitions = check_response.json()
            existing_definition = None

            # Handle both list and paginated response formats
            if isinstance(definitions, list):
                existing_definition = definitions[0] if definitions else None
            else:
                results = definitions.get('results', [])
                existing_definition = results[0] if results else None

            if existing_definition:
                # Definition is immutable - don't update, just return existing
                return existing_definition

            # Create new definition
            response = self.api_session.post(
                f"{self.monitor_url}/api/workflow-definitions/",
                json=payload
            )
        else:
            # Create new definition
            response = self.api_session.post(
                f"{self.monitor_url}/api/workflow-definitions/",
                json=payload
            )

        if response.status_code not in [200, 201]:
            print(f"Error: Failed to register workflow definition: {response.status_code}")
            try:
                error_detail = response.json()
                print(f"API error response: {error_detail}")
            except:
                print(f"Raw response: {response.text}")
            raise Exception(f"Failed to register workflow definition: {response.status_code}")

        return response.json()

    def _create_execution_record(self, execution_id: str, workflow_name: str,
                                 workflow_version: str, config: Dict[str, Any]):
        """Create workflow execution record with full config for auditability."""
        # Get workflow definition ID
        def_response = self.api_session.get(
            f"{self.monitor_url}/api/workflow-definitions/",
            params={'workflow_name': workflow_name, 'version': workflow_version}
        )

        if def_response.status_code != 200:
            print(f"Warning: Could not find workflow definition for {workflow_name} v{workflow_version}")
            return

        definitions = def_response.json()
        if not definitions:
            print(f"Warning: No workflow definition found for {workflow_name} v{workflow_version}")
            return

        # Handle both list and paginated response formats
        if isinstance(definitions, list):
            if not definitions:
                print(f"Warning: No workflow definition found for {workflow_name} v{workflow_version}")
                return
            workflow_definition_id = definitions[0]['id']
        else:
            results = definitions.get('results', [])
            if not results:
                print(f"Warning: No workflow definition found for {workflow_name} v{workflow_version}")
                return
            workflow_definition_id = results[0]['id']

        # Get namespace from testbed config and ensure it exists in database
        namespace = config.get('testbed', {}).get('namespace')
        if namespace:
            try:
                ensure_namespace(self.monitor_url, self.api_session, namespace, logger=self.logger)
            except Exception:
                pass  # Warning already logged by ensure_namespace

        # Add git version to config for auditability
        git_version = get_git_version(self.workflows_dir)
        config_with_version = dict(config)
        if git_version:
            config_with_version['git_version'] = git_version

        payload = {
            'execution_id': execution_id,
            'workflow_definition': workflow_definition_id,
            'namespace': namespace,
            'status': 'running',
            'executed_by': os.getenv('USER', 'unknown'),
            'start_time': datetime.now().isoformat(),
            'parameter_values': config_with_version
        }

        response = self.api_session.post(
            f"{self.monitor_url}/api/workflow-executions/",
            json=payload
        )

        if response.status_code not in [200, 201]:
            print(f"Error: Failed to create execution record: {response.status_code}")
            try:
                error_detail = response.json()
                print(f"API error response: {error_detail}")
            except:
                print(f"Raw response: {response.text}")
            raise Exception(f"Failed to create execution record: {response.status_code}")

    def _on_simulation_step(self, env, execution_id: str) -> bool:
        """
        Called between simulation events.

        Override or extend this method to add per-step behavior such as:
        - Progress reporting to monitor
        - Periodic heartbeats during long workflows
        - Logging/metrics collection

        Args:
            env: SimPy environment
            execution_id: Current execution ID

        Returns:
            True to continue simulation, False to stop
        """
        # Check stop flag
        if self.stop_event.is_set():
            self.logger.info("Stop requested - ending simulation")
            return False

        return True

    def _execute_workflow(self, execution_id: str, workflow_code: str,
                         config: Dict[str, Any], duration: float,
                         realtime: bool = False):
        """Execute workflow using SimPy with step callback support.

        Args:
            execution_id: Unique identifier for this execution
            workflow_code: Python code containing WorkflowExecutor class
            config: Full workflow config with descriptive sections
            duration: Simulation duration in seconds
            realtime: If True, use RealtimeEnvironment (1 sim sec = 1 wall sec)

        The simulation calls _on_simulation_step() between events to allow
        graceful stopping and other per-step behaviors.
        """
        # Create SimPy environment
        if realtime:
            # RealtimeEnvironment ties simulation time to wall-clock time
            # factor=1 means 1 simulation second = 1 real second
            self.logger.info("Using real-time simulation mode")
            env = simpy.rt.RealtimeEnvironment(factor=1, strict=False)
        else:
            # Standard discrete-event simulation (runs as fast as possible)
            env = simpy.Environment()

        # Prepare execution namespace with runner access
        namespace = {
            'env': env,
            'config': config,
            'runner': self,
            'execution_id': execution_id
        }

        # Execute workflow code to get WorkflowExecutor class
        exec(workflow_code, namespace)

        # Instantiate and run workflow
        if 'WorkflowExecutor' in namespace:
            # Pass config, runner (for messaging), and execution_id
            executor = namespace['WorkflowExecutor'](
                config=config,
                runner=self,
                execution_id=execution_id
            )

            # Start workflow process
            workflow_process = env.process(executor.execute(env))

            # Run simulation with step callbacks
            end_time = duration if duration and duration > 0 else float('inf')

            while True:
                # Step callback - check stop flag and other per-step actions
                if not self._on_simulation_step(env, execution_id):
                    break

                # Check if workflow process completed
                if workflow_process.processed:
                    break

                # Check duration limit
                if env.now >= end_time:
                    self.logger.info(f"Duration limit reached: {duration}s")
                    break

                # Run next simulation event
                try:
                    env.step()
                except simpy.core.EmptySchedule:
                    # No more events - simulation complete
                    break
        else:
            raise ValueError("WorkflowExecutor class not found in workflow code")

    def _update_execution_status(self, execution_id: str, status: str):
        """Update workflow execution status"""
        payload = {
            'status': status,
            'end_time': datetime.now().isoformat() if status == 'completed' else None
        }

        response = self.api_session.patch(
            f"{self.monitor_url}/api/workflow-executions/{execution_id}/",
            json=payload
        )

        if response.status_code != 200:
            print(f"Warning: Failed to update execution status: {response.status_code}")

    def initialize_state(self, state_id: int, execution_id: str, config: dict = None):
        """
        Initialize state machine record for workflow execution.
        Currently creates RunState (run-level subset).
        Future: broader state machine tracking.

        Args:
            state_id: Run number / state identifier
            execution_id: Workflow execution ID
            config: Full workflow config for extracting workflow-specific params
        """
        # Extract workflow-specific params for metadata
        workflow_params = {}
        for section in ['fast_processing', 'daq_state_machine']:
            if config and section in config:
                workflow_params.update(config[section])

        state_data = {
            'run_number': state_id,
            'phase': 'initializing',
            'state': 'imminent',
            'substate': 'preparing',
            'target_worker_count': workflow_params.get('target_worker_count', 0),
            'active_worker_count': 0,
            'stf_samples_received': 0,
            'slices_created': 0,
            'slices_queued': 0,
            'slices_processing': 0,
            'slices_completed': 0,
            'slices_failed': 0,
            'state_changed_at': datetime.now().isoformat(),
            'metadata': {
                'execution_id': execution_id,
                'stf_sampling_rate': workflow_params.get('stf_sampling_rate'),
                'slices_per_sample': workflow_params.get('slices_per_sample')
            }
        }

        response = self.api_session.post(
            f"{self.monitor_url}/api/run-states/",
            json=state_data
        )

        if response.status_code in [200, 201]:
            self.logger.info(f"State initialized: {state_id}")
            return True

        self.logger.error(f"Failed to initialize state: {response.status_code}")
        try:
            self.logger.error(f"Response: {response.json()}")
        except Exception:
            self.logger.error(f"Response: {response.text}")
        return False

    # -------------------------------------------------------------------------
    # Persistent Agent Mode - Message Handling
    # -------------------------------------------------------------------------

    def on_message(self, frame):
        """
        Handle incoming workflow control messages.

        Supported commands:
        - run_workflow: Start a workflow execution
        - stop_workflow: Stop current workflow (future)
        - status_request: Report current status
        """
        message_data, msg_type = self.log_received_message(
            frame, known_types=self.COMMAND_MESSAGE_TYPES
        )

        # Namespace filtering - log_received_message returns (None, None) if filtered
        if message_data is None:
            return

        if msg_type == 'run_workflow':
            self._handle_run_workflow(message_data)
        elif msg_type == 'stop_workflow':
            self._handle_stop_workflow(message_data)
        elif msg_type == 'status_request':
            self._handle_status_request(message_data)
        else:
            self.logger.debug(f"Ignoring unhandled message type: {msg_type}")

    def _handle_run_workflow(self, message_data: Dict[str, Any]):
        """Handle run_workflow command - starts workflow in background thread."""
        # Check if already running a workflow
        if self.operational_state == 'PROCESSING':
            self.logger.warning(
                f"Cannot start workflow - already running: {self.current_workflow_name} "
                f"(execution: {self.current_execution_id})"
            )
            return

        # Extract workflow parameters from message
        workflow_name = message_data.get('workflow_name')
        if not workflow_name:
            self.logger.error("run_workflow message missing 'workflow_name'")
            return

        config_name = message_data.get('config')
        realtime = message_data.get('realtime', True)
        duration = message_data.get('duration', 0)
        params = message_data.get('params', {})

        # Clear stop flag and set state
        self.stop_event.clear()
        self.set_processing()
        self.current_workflow_name = workflow_name

        self.logger.info(
            f"Starting workflow: {workflow_name} (config: {config_name})",
            extra={'workflow_name': workflow_name}
        )

        # Start workflow in background thread
        self.workflow_thread = threading.Thread(
            target=self._run_workflow_thread,
            args=(workflow_name, config_name, duration, realtime, params),
            name=f"workflow-{workflow_name}",
            daemon=True
        )
        self.workflow_thread.start()

    def _run_workflow_thread(self, workflow_name: str, config_name: Optional[str],
                             duration: float, realtime: bool, params: Dict[str, Any]):
        """Run workflow in background thread with proper cleanup."""
        try:
            execution_id = self.run_workflow(
                workflow_name=workflow_name,
                config_name=config_name,
                duration=duration,
                realtime=realtime,
                **params
            )

            if self.stop_event.is_set():
                self.logger.info(
                    f"Workflow stopped: {workflow_name} (execution: {execution_id})",
                    extra={'execution_id': execution_id, 'workflow_name': workflow_name}
                )
                # Mark as terminated in database
                self._update_execution_status(execution_id, 'terminated')
            else:
                self.logger.info(
                    f"Workflow completed: {workflow_name} (execution: {execution_id})",
                    extra={'execution_id': execution_id, 'workflow_name': workflow_name}
                )

        except Exception as e:
            exec_id = getattr(self, 'current_execution_id', None)
            self.logger.error(
                f"Workflow failed: {workflow_name} (execution: {exec_id or 'unknown'}): {e}",
                extra={'execution_id': exec_id, 'workflow_name': workflow_name}
            )
            if exec_id:
                self._update_execution_status(exec_id, 'failed')

        finally:
            self.current_execution_id = None
            self.current_workflow_name = None
            self.workflow_thread = None
            self.set_ready()

    def _handle_stop_workflow(self, message_data: Dict[str, Any]):
        """Handle stop_workflow command - signals workflow to stop gracefully."""
        if self.operational_state != 'PROCESSING':
            self.logger.info("No workflow running to stop")
            return

        # Check execution_id if provided (for targeted stop)
        requested_exec_id = message_data.get('execution_id')
        if requested_exec_id and requested_exec_id != self.current_execution_id:
            self.logger.info(
                f"Stop request for {requested_exec_id} ignored - "
                f"current execution is {self.current_execution_id}"
            )
            return

        self.logger.info(
            f"Stopping workflow: {self.current_workflow_name} (execution: {self.current_execution_id})",
            extra={'execution_id': self.current_execution_id, 'workflow_name': self.current_workflow_name}
        )
        self.stop_event.set()

    def _handle_status_request(self, message_data: Dict[str, Any]):
        """Handle status_request command - logs current status."""
        self.logger.info(
            f"Status: state={self.operational_state}, "
            f"workflow={self.current_workflow_name}, "
            f"execution={self.current_execution_id}"
        )


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    """
    Main entry point for WorkflowRunner.

    Default mode: Persistent agent listening for workflow commands.
    --run-once mode: Execute single workflow and exit (backward compat).
    """
    import argparse

    script_dir = Path(__file__).parent

    parser = argparse.ArgumentParser(
        description='Workflow Runner - DAQ Simulator Agent',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Persistent mode (default) - listens for commands
  python workflow_runner.py

  # Run single workflow and exit
  python workflow_runner.py --run-once stf_datataking --stf-count 5

  # Run with specific config
  python workflow_runner.py --run-once stf_datataking --workflow-config fast_processing_default
        """
    )

    parser.add_argument('--testbed-config', default=None,
                        help='Testbed config file (default: SWF_TESTBED_CONFIG env var or workflows/testbed.toml)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')

    # Mode selection
    parser.add_argument('--run-once', metavar='WORKFLOW',
                        help='Run single workflow and exit (CLI mode)')

    # Workflow parameters (only used with --run-once)
    parser.add_argument('--workflow-config', help='Workflow configuration file name')
    parser.add_argument('--duration', type=float, default=0,
                        help='Max duration in seconds (0 = run until complete)')
    parser.add_argument('--stf-count', type=int, help='Override STF count')
    parser.add_argument('--physics-period-count', type=int, help='Override physics period count')
    parser.add_argument('--physics-period-duration', type=float, help='Override physics period duration')
    parser.add_argument('--stf-interval', type=float, help='Override STF interval')
    parser.add_argument('--realtime', action='store_true', default=True,
                        help='Run in real-time mode (default: True)')
    parser.add_argument('--no-realtime', action='store_false', dest='realtime',
                        help='Run as fast as possible (discrete-event simulation)')

    args = parser.parse_args()

    # Build workflow parameters
    workflow_params = {}
    if args.stf_count is not None:
        workflow_params['stf_count'] = args.stf_count
    if args.physics_period_count is not None:
        workflow_params['physics_period_count'] = args.physics_period_count
    if args.physics_period_duration is not None:
        workflow_params['physics_period_duration'] = args.physics_period_duration
    if args.stf_interval is not None:
        workflow_params['stf_interval'] = args.stf_interval

    if args.run_once:
        # CLI mode: run single workflow and exit
        runner = WorkflowRunner(
            config_path=args.testbed_config,
            debug=args.debug,
            workflow_name=args.run_once
        )

        runner.set_processing()
        try:
            execution_id = runner.run_workflow(
                workflow_name=args.run_once,
                config_name=args.workflow_config,
                duration=args.duration,
                realtime=args.realtime,
                **workflow_params
            )
            runner.logger.info(f"Workflow completed: {execution_id}")
        except Exception as e:
            runner.logger.error(f"Workflow failed: {e}")
            sys.exit(1)
        finally:
            runner.set_ready()
    else:
        # Persistent mode: run as agent listening for commands
        runner = WorkflowRunner(
            config_path=args.testbed_config,
            debug=args.debug
        )
        runner.run()


if __name__ == "__main__":
    main()