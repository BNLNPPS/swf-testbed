#!/usr/bin/env python3
"""
Send workflow commands to the DAQ Simulator agent.

Uses the same connection infrastructure as other agents.
"""

import os
import sys
import json
import argparse
from pathlib import Path


def setup_environment():
    """Auto-activate venv and load environment variables."""
    script_dir = Path(__file__).resolve().parent.parent

    if "VIRTUAL_ENV" not in os.environ:
        venv_path = script_dir / ".venv"
        if venv_path.exists():
            os.environ["VIRTUAL_ENV"] = str(venv_path)
            os.environ["PATH"] = f"{venv_path}/bin:{os.environ['PATH']}"
            sys.executable = str(venv_path / "bin" / "python")

    env_file = Path.home() / ".env"
    if env_file.exists():
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

    for proxy_var in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
        if proxy_var in os.environ:
            del os.environ[proxy_var]

    return True


if __name__ == "__main__":
    if not setup_environment():
        sys.exit(1)

import stomp
import ssl
import tomllib
from datetime import datetime


class CommandSender:
    """Lightweight message sender using agent infrastructure."""

    def __init__(self, config_path: str = None):
        script_dir = Path(__file__).parent
        if config_path is None:
            config_path = script_dir / 'testbed.toml'

        # Load namespace from config
        self.namespace = None
        if Path(config_path).exists():
            with open(config_path, 'rb') as f:
                config = tomllib.load(f)
                self.namespace = config.get('testbed', {}).get('namespace')

        # Connection settings from environment (matching BaseAgent)
        self.mq_host = os.getenv('ACTIVEMQ_HOST', 'localhost')
        self.mq_port = int(os.getenv('ACTIVEMQ_PORT', 61612))
        self.mq_user = os.getenv('ACTIVEMQ_USER', 'admin')
        self.mq_password = os.getenv('ACTIVEMQ_PASSWORD', 'admin')
        self.use_ssl = os.getenv('ACTIVEMQ_USE_SSL', 'False').lower() == 'true'
        self.ssl_ca_certs = os.getenv('ACTIVEMQ_SSL_CA_CERTS', '')

        # Create connection (matching BaseAgent pattern)
        self.conn = stomp.Connection(
            host_and_ports=[(self.mq_host, self.mq_port)],
            vhost=self.mq_host,
            try_loopback_connect=False,
            heartbeats=(30000, 30000),
            auto_content_length=False
        )

        # Configure SSL if enabled (matching BaseAgent pattern)
        if self.use_ssl and self.ssl_ca_certs:
            self.conn.transport.set_ssl(
                for_hosts=[(self.mq_host, self.mq_port)],
                ca_certs=self.ssl_ca_certs,
                ssl_version=ssl.PROTOCOL_TLS_CLIENT
            )

    def connect(self):
        self.conn.connect(
            self.mq_user,
            self.mq_password,
            wait=True,
            version='1.1',
            headers={'client-id': f'cmd-sender-{os.getpid()}', 'heart-beat': '30000,30000'}
        )

    def disconnect(self):
        if self.conn.is_connected():
            self.conn.disconnect()

    def send_run_workflow(self, workflow_name: str, config: str = None,
                          realtime: bool = True, **params):
        """Send run_workflow command."""
        msg = {
            'msg_type': 'run_workflow',
            'namespace': self.namespace,
            'workflow_name': workflow_name,
            'config': config,
            'realtime': realtime,
            'params': params,
            'timestamp': datetime.now().isoformat()
        }
        self.conn.send(destination='/queue/workflow_control', body=json.dumps(msg))
        print(f"Sent run_workflow: {workflow_name} (namespace: {self.namespace})")

    def send_stop_workflow(self, execution_id: str = None):
        """Send stop_workflow command."""
        msg = {
            'msg_type': 'stop_workflow',
            'namespace': self.namespace,
            'timestamp': datetime.now().isoformat()
        }
        if execution_id:
            msg['execution_id'] = execution_id
        self.conn.send(destination='/queue/workflow_control', body=json.dumps(msg))
        print(f"Sent stop_workflow (execution_id: {execution_id}, namespace: {self.namespace})")

    def send_status_request(self):
        """Send status_request command."""
        msg = {
            'msg_type': 'status_request',
            'namespace': self.namespace,
            'timestamp': datetime.now().isoformat()
        }
        self.conn.send(destination='/queue/workflow_control', body=json.dumps(msg))
        print(f"Sent status_request (namespace: {self.namespace})")


def main():
    parser = argparse.ArgumentParser(description='Send workflow commands to DAQ Simulator')
    parser.add_argument('command', choices=['run', 'stop', 'status'],
                        help='Command to send')
    parser.add_argument('--workflow', default='stf_datataking',
                        help='Workflow name (for run command)')
    parser.add_argument('--config', help='Workflow config name')
    parser.add_argument('--stf-count', type=int, help='STF count parameter')
    parser.add_argument('--realtime', action='store_true', default=True)
    parser.add_argument('--no-realtime', action='store_false', dest='realtime')
    parser.add_argument('--execution-id', help='Execution ID (for stop command)')
    parser.add_argument('--testbed-config', help='Path to testbed.toml')

    args = parser.parse_args()

    sender = CommandSender(config_path=args.testbed_config)
    sender.connect()

    try:
        if args.command == 'run':
            params = {}
            if args.stf_count:
                params['stf_count'] = args.stf_count
            sender.send_run_workflow(
                args.workflow,
                config=args.config,
                realtime=args.realtime,
                **params
            )
        elif args.command == 'stop':
            sender.send_stop_workflow(execution_id=args.execution_id)
        elif args.command == 'status':
            sender.send_status_request()
    finally:
        sender.disconnect()


if __name__ == "__main__":
    main()
