"""
Workflow Runner - Executes workflow definitions with SimPy
"""

import os
import json
import tomllib
import simpy
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any


class WorkflowRunner:
    """Loads, registers, and executes workflow definitions"""

    def __init__(self, monitor_url: str, api_session: Optional[requests.Session] = None):
        """
        Initialize WorkflowRunner

        Args:
            monitor_url: URL of the SWF monitor API
            api_session: Optional requests session with auth configured
        """
        self.monitor_url = monitor_url.rstrip('/')
        self.api_session = api_session or requests.Session()
        self.workflows_dir = Path(__file__).parent  # workflows/ directory

    def run_workflow(self, workflow_name: str, config_name: Optional[str] = None,
                     duration: float = 3600, **override_params) -> str:
        """
        Run a workflow by name

        Args:
            workflow_name: Name of the workflow (e.g., 'stf_processing')
            config_name: Name of config file (defaults to {workflow_name}_default.toml)
            duration: Simulation duration in seconds
            **override_params: Parameters to override from config

        Returns:
            execution_id: The ID of the workflow execution
        """
        # Load workflow definition and config
        workflow_code = self._load_workflow_code(workflow_name)
        config = self._load_workflow_config(workflow_name, config_name)

        # Apply parameter overrides
        if override_params:
            config['parameters'].update(override_params)

        # Generate execution ID
        execution_id = self._generate_execution_id(workflow_name)

        # Register/update workflow definition in database
        self._register_workflow_definition(
            name=config['workflow']['name'],
            version=config['workflow']['version'],
            code=workflow_code,
            config=config
        )

        # Create execution record
        self._create_execution_record(
            execution_id=execution_id,
            workflow_name=config['workflow']['name'],
            workflow_version=config['workflow']['version'],
            parameters=config['parameters']
        )

        # Execute the workflow
        self._execute_workflow(
            execution_id=execution_id,
            workflow_code=workflow_code,
            parameters=config['parameters'],
            duration=duration
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
        """Load workflow TOML configuration"""
        if config_name is None:
            config_name = f"{workflow_name}_default.toml"
        elif not config_name.endswith('.toml'):
            config_name = f"{config_name}.toml"

        config_file = self.workflows_dir / config_name
        if not config_file.exists():
            raise FileNotFoundError(f"Config {config_name} not found in {self.workflows_dir}")

        with open(config_file, 'rb') as f:
            return tomllib.load(f)

    def _generate_execution_id(self, workflow_name: str) -> str:
        """Generate human-readable execution ID"""
        # Get next ID from persistent state API
        response = self.api_session.post(
            f"{self.monitor_url}/api/persistent-state/next-workflow-execution-id/",
            json={'workflow_name': workflow_name}
        )

        if response.status_code == 200:
            data = response.json()
            sequence = data.get('sequence', 1)
        else:
            # Fallback if API unavailable
            import random
            sequence = random.randint(1000, 9999)

        # Format: workflow-YYYYMMDD-NNNN
        date_str = datetime.now().strftime('%Y%m%d')
        return f"{workflow_name}-{date_str}-{sequence:04d}"

    def _register_workflow_definition(self, name: str, version: str, code: str, config: Dict[str, Any]):
        """Register or update workflow definition in database"""
        payload = {
            'workflow_name': name,
            'version': version,
            'workflow_type': 'simulation',
            'workflow_code': code,
            'workflow_config': json.dumps(config),
            'created_by': os.getenv('USER', 'unknown'),
            'created_at': datetime.now().isoformat()
        }

        # Upsert workflow definition
        response = self.api_session.post(
            f"{self.monitor_url}/api/workflow-definitions/upsert/",
            json=payload
        )

        if response.status_code not in [200, 201]:
            print(f"Warning: Failed to register workflow definition: {response.status_code}")

    def _create_execution_record(self, execution_id: str, workflow_name: str,
                                 workflow_version: str, parameters: Dict[str, Any]):
        """Create workflow execution record"""
        payload = {
            'execution_id': execution_id,
            'workflow_name': workflow_name,
            'workflow_version': workflow_version,
            'status': 'running',
            'executed_by': os.getenv('USER', 'unknown'),
            'start_time': datetime.now().isoformat(),
            'parameter_values': parameters
        }

        response = self.api_session.post(
            f"{self.monitor_url}/api/workflow-executions/",
            json=payload
        )

        if response.status_code not in [200, 201]:
            print(f"Warning: Failed to create execution record: {response.status_code}")

    def _execute_workflow(self, execution_id: str, workflow_code: str,
                         parameters: Dict[str, Any], duration: float):
        """Execute workflow using SimPy"""
        # Create SimPy environment
        env = simpy.Environment()

        # Prepare execution namespace
        namespace = {'env': env, 'parameters': parameters}

        # Execute workflow code to get WorkflowExecutor class
        exec(workflow_code, namespace)

        # Instantiate and run workflow
        if 'WorkflowExecutor' in namespace:
            executor = namespace['WorkflowExecutor'](parameters)

            # Start workflow process
            env.process(executor.execute(env))

            # Run simulation for specified duration
            env.run(until=duration)

            print(f"Workflow {execution_id} completed at simulation time {env.now}")
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