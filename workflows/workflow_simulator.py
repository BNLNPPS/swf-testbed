#!/usr/bin/env python3
"""
Workflow Simulator Agent - Executes workflow definitions using WorkflowRunner
Integrates SimPy-based workflows with SWF agent infrastructure
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path

def setup_environment():
    """Auto-activate venv and load environment variables."""
    script_dir = Path(__file__).resolve().parent.parent  # Go up to swf-testbed root

    # Auto-activate virtual environment if not already active
    if "VIRTUAL_ENV" not in os.environ:
        venv_path = script_dir / ".venv"
        if venv_path.exists():
            print("🔧 Auto-activating virtual environment...")
            venv_python = venv_path / "bin" / "python"
            if venv_python.exists():
                os.environ["VIRTUAL_ENV"] = str(venv_path)
                os.environ["PATH"] = f"{venv_path}/bin:{os.environ['PATH']}"
                sys.executable = str(venv_python)
        else:
            print("❌ Error: No Python virtual environment found")
            return False

    # Load ~/.env environment variables (they're already exported)
    env_file = Path.home() / ".env"
    if env_file.exists():
        print("🔧 Loading environment variables from ~/.env...")
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    if line.startswith('export '):
                        line = line[7:]  # Remove 'export '
                    key, value = line.split('=', 1)
                    os.environ[key] = value.strip('"\'')

    # Unset proxy variables to prevent localhost routing through proxy
    for proxy_var in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
        if proxy_var in os.environ:
            del os.environ[proxy_var]

    return True

if __name__ == "__main__":
    if not setup_environment():
        sys.exit(1)

# Import after environment setup
from swf_common_lib.base_agent import BaseAgent
sys.path.append(str(Path(__file__).parent.parent / "workflows"))
from workflow_runner import WorkflowRunner


class WorkflowSimulatorAgent(BaseAgent):
    """Agent that executes workflows using WorkflowRunner"""

    def __init__(self, workflow_name, config_name=None, duration=3600, **workflow_params):
        super().__init__(agent_type='WORKFLOW_SIMULATOR', subscription_queue='workflow_simulator')

        self.workflow_name = workflow_name
        self.config_name = config_name
        self.duration = duration
        self.workflow_params = workflow_params
        self.execution_id = None

        # Initialize WorkflowRunner with monitor URL and API session
        self.workflow_runner = WorkflowRunner(self.monitor_url, self.api)

        # Enhanced status for workflow execution
        self.workflow_status = "initialized"
        self.current_execution = None

    def on_message(self, frame):
        """Handle incoming workflow control messages"""
        try:
            message_data, msg_type = self.log_received_message(frame)

            if msg_type == 'start_workflow':
                self.handle_start_workflow(message_data)
            elif msg_type == 'stop_workflow':
                self.handle_stop_workflow(message_data)
            elif msg_type == 'workflow_status_request':
                self.handle_status_request(message_data)
            else:
                self.logger.info(f"Workflow simulator received unhandled message type: {msg_type}")

        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
            self.workflow_status = "error"
            self.send_enhanced_heartbeat({
                'workflow_status': self.workflow_status,
                'error': str(e)
            })

    def handle_start_workflow(self, message_data):
        """Start workflow execution"""
        try:
            self.logger.info(f"Starting workflow: {self.workflow_name}")
            self.workflow_status = "running"

            # Send enhanced heartbeat with workflow metadata
            self.send_enhanced_heartbeat({
                'workflow_status': self.workflow_status,
                'workflow_name': self.workflow_name,
                'execution_phase': 'starting'
            })

            # Execute workflow
            self.execution_id = self.workflow_runner.run_workflow(
                workflow_name=self.workflow_name,
                config_name=self.config_name,
                duration=self.duration,
                **self.workflow_params
            )

            self.workflow_status = "completed"
            self.logger.info(f"Workflow completed successfully: {self.execution_id}")

            # Send completion heartbeat
            self.send_enhanced_heartbeat({
                'workflow_status': self.workflow_status,
                'execution_id': self.execution_id,
                'execution_phase': 'completed'
            })

            # Broadcast workflow completion
            self.broadcast_workflow_status('workflow_completed', {
                'execution_id': self.execution_id,
                'workflow_name': self.workflow_name,
                'status': 'completed'
            })

        except Exception as e:
            self.logger.error(f"Workflow execution failed: {e}")
            self.workflow_status = "failed"
            self.send_enhanced_heartbeat({
                'workflow_status': self.workflow_status,
                'error': str(e),
                'execution_phase': 'failed'
            })

            # Broadcast failure
            self.broadcast_workflow_status('workflow_failed', {
                'workflow_name': self.workflow_name,
                'status': 'failed',
                'error': str(e)
            })

    def handle_stop_workflow(self, message_data):
        """Handle workflow stop request"""
        self.logger.info("Received workflow stop request")
        self.workflow_status = "stopped"
        self.send_enhanced_heartbeat({
            'workflow_status': self.workflow_status,
            'execution_phase': 'stopped'
        })

    def handle_status_request(self, message_data):
        """Handle workflow status request"""
        self.logger.info("Sending workflow status")
        self.broadcast_workflow_status('workflow_status_response', {
            'workflow_name': self.workflow_name,
            'status': self.workflow_status,
            'execution_id': self.execution_id
        })

    def broadcast_workflow_status(self, msg_type, data):
        """Broadcast workflow status to other agents"""
        message = {
            'msg_type': msg_type,
            'timestamp': json.dumps(str(self.get_current_time()), default=str),
            'agent_name': self.agent_name,
            **data
        }

        # Broadcast to workflow status queue
        self.send_message('/queue/workflow_status', message)
        self.logger.info(f"Broadcast {msg_type}: {data}")

    def get_current_time(self):
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now()



def main():
    """Main entry point with command line argument support"""
    parser = argparse.ArgumentParser(description='Workflow Simulator Agent')
    parser.add_argument('workflow_name', help='Name of the workflow to execute')
    parser.add_argument('--config', help='Configuration file name')
    parser.add_argument('--duration', type=float, default=3600, help='Simulation duration in seconds')
    parser.add_argument('--physics-period-count', type=int, help='Override physics period count')
    parser.add_argument('--physics-period-duration', type=float, help='Override physics period duration')
    parser.add_argument('--stf-interval', type=float, help='Override STF interval')
    parser.add_argument('--realtime', action='store_true',
                        help='Run simulation in real-time (1 sim second = 1 wall-clock second)')

    args = parser.parse_args()

    # Build workflow parameters from arguments
    workflow_params = {}
    if args.physics_period_count is not None:
        workflow_params['physics_period_count'] = args.physics_period_count
    if args.physics_period_duration is not None:
        workflow_params['physics_period_duration'] = args.physics_period_duration
    if args.stf_interval is not None:
        workflow_params['stf_interval'] = args.stf_interval

    # Create workflow simulator
    simulator = WorkflowSimulatorAgent(
        workflow_name=args.workflow_name,
        config_name=args.config,
        duration=args.duration,
        **workflow_params
    )

    # Run workflow directly
    try:
        simulator.logger.info(f"Starting workflow execution: {args.workflow_name}")

        # Execute workflow
        execution_id = simulator.workflow_runner.run_workflow(
            workflow_name=args.workflow_name,
            config_name=args.config,
            duration=args.duration,
            realtime=args.realtime,
            **workflow_params
        )

        simulator.logger.info(f"Workflow completed successfully: {execution_id}")

    except Exception as e:
        simulator.logger.error(f"Workflow execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()