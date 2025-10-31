"""
Workflow Runner - Executes workflow definitions with SimPy
"""

import os
import sys
import json
import tomllib
import simpy
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

# Add swf-common-lib to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "swf-common-lib" / "src"))
from swf_common_lib.base_agent import BaseAgent


class WorkflowRunner(BaseAgent):
    """Loads, registers, and executes workflow definitions"""

    def __init__(self, monitor_url: Optional[str] = None, debug: bool = False):
        """
        Initialize WorkflowRunner as an agent

        Args:
            monitor_url: Optional override for SWF monitor URL (uses env if not provided)
            debug: Enable debug logging
        """
        # Initialize as BaseAgent (workflow_runner type, workflow_control queue)
        super().__init__(
            agent_type='workflow_runner',
            subscription_queue='workflow_control',
            debug=debug
        )

        # Override monitor_url if provided
        if monitor_url:
            self.monitor_url = monitor_url.rstrip('/')

        # Use self.api from BaseAgent (already configured with auth)
        self.api_session = self.api
        self.workflows_dir = Path(__file__).parent  # workflows/ directory

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

        self.logger.info(f"WorkflowRunner initialized and connected to ActiveMQ: {self.agent_name}")

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
        executed_by = os.getenv('USER', 'unknown')
        execution_id = self._generate_execution_id(workflow_name, executed_by)

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
        """Load workflow TOML configuration with includes support"""
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
            # No includes, return main config as-is
            return main_config

        # Merge included configs
        merged_params = {}

        # Load and merge each included file in order
        for include_file in includes:
            include_path = self.workflows_dir / include_file
            if not include_path.exists():
                raise FileNotFoundError(f"Included config {include_file} not found in {self.workflows_dir}")

            with open(include_path, 'rb') as f:
                included_config = tomllib.load(f)
                # Merge parameters from included file
                if 'parameters' in included_config:
                    merged_params.update(included_config['parameters'])

        # Final override: main config parameters have final say
        if 'parameters' in main_config:
            merged_params.update(main_config['parameters'])

        # Replace parameters section with fully merged parameters
        main_config['parameters'] = merged_params

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

    def _register_workflow_definition(self, name: str, version: str, code: str, config: Dict[str, Any]):
        """Register or update workflow definition in database"""
        # Check if workflow definition already exists
        check_url = f"{self.monitor_url}/api/workflow-definitions/"
        check_response = self.api_session.get(
            check_url,
            params={'workflow_name': name, 'version': version}
        )

        # Build expanded config for database storage (no includes directive)
        expanded_config = {
            'workflow': {
                'name': config['workflow']['name'],
                'version': config['workflow']['version']
            },
            'parameters': config['parameters']  # Already merged/expanded
        }
        # Preserve description if present
        if 'description' in config['workflow']:
            expanded_config['workflow']['description'] = config['workflow']['description']

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
                # Update existing definition
                definition_id = existing_definition['id']
                response = self.api_session.put(
                    f"{self.monitor_url}/api/workflow-definitions/{definition_id}/",
                    json=payload
                )
            else:
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
                                 workflow_version: str, parameters: Dict[str, Any]):
        """Create workflow execution record"""
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

        payload = {
            'execution_id': execution_id,
            'workflow_definition': workflow_definition_id,
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
            print(f"Error: Failed to create execution record: {response.status_code}")
            try:
                error_detail = response.json()
                print(f"API error response: {error_detail}")
            except:
                print(f"Raw response: {response.text}")
            raise Exception(f"Failed to create execution record: {response.status_code}")

    def _execute_workflow(self, execution_id: str, workflow_code: str,
                         parameters: Dict[str, Any], duration: float):
        """Execute workflow using SimPy"""
        # Create SimPy environment
        env = simpy.Environment()

        # Prepare execution namespace with runner access
        namespace = {
            'env': env,
            'parameters': parameters,
            'runner': self,
            'execution_id': execution_id
        }

        # Execute workflow code to get WorkflowExecutor class
        exec(workflow_code, namespace)

        # Instantiate and run workflow
        if 'WorkflowExecutor' in namespace:
            # Pass parameters, runner (for messaging), and execution_id
            executor = namespace['WorkflowExecutor'](
                parameters=parameters,
                runner=self,
                execution_id=execution_id
            )

            # Start workflow process
            env.process(executor.execute(env))

            # Run simulation for specified duration
            env.run(until=duration)
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