#!/usr/bin/env python3
"""
User Agent Manager - A lightweight per-user daemon for testbed control.

Listens on /queue/agent_control.<username> for commands from MCP:
- start_testbed: Start agents and workflow runner
- stop_testbed: Stop all agents
- status: Report current status

Sends periodic heartbeats so MCP can check if it's alive.
"""

import getpass
import json
import os
import signal
import subprocess
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path

import stomp
from swf_common_lib.rest_logging import setup_rest_logging

# Heartbeat interval in seconds
HEARTBEAT_INTERVAL = 30

# Supervisord config for agents
AGENTS_CONF = 'agents.supervisord.conf'

# Default config file (can be overridden via SWF_TESTBED_CONFIG env var)
DEFAULT_CONFIG = os.getenv('SWF_TESTBED_CONFIG', 'workflows/testbed.toml')

# Map testbed.toml agent names to supervisord program names
AGENT_PROGRAM_MAP = {
    'data': 'example-data-agent',
    'processing': 'example-processing-agent',
    'fastmon': 'example-fastmon-agent',
    'fast_processing': 'fast-processing-agent',
}


class UserAgentManager(stomp.ConnectionListener):
    """
    Lightweight agent manager for a single user.

    Manages the user's testbed agents via supervisord.
    """

    def __init__(self, testbed_dir: Path = None):
        self.username = getpass.getuser()
        self.control_queue = f'/queue/agent_control.{self.username}'
        self.testbed_dir = testbed_dir or Path(__file__).parent.parent.parent

        # ActiveMQ connection settings from environment
        self.mq_host = os.getenv('ACTIVEMQ_HOST', 'localhost')
        self.mq_port = int(os.getenv('ACTIVEMQ_PORT', 61612))
        self.mq_user = os.getenv('ACTIVEMQ_USER', 'admin')
        self.mq_password = os.getenv('ACTIVEMQ_PASSWORD', 'admin')
        self.use_ssl = os.getenv('ACTIVEMQ_USE_SSL', 'false').lower() == 'true'
        self.ssl_ca_certs = os.getenv('ACTIVEMQ_SSL_CA_CERTS', '')

        # Monitor API for heartbeats (use production monitor)
        self.monitor_url = os.getenv('SWF_MONITOR_URL', 'https://pandaserver02.sdcc.bnl.gov/swf-monitor')
        self.api_token = os.getenv('SWF_API_TOKEN')

        # Set up API session with auth token (like BaseAgent)
        import requests
        self.api = requests.Session()
        if self.api_token:
            self.api.headers.update({'Authorization': f'Token {self.api_token}'})
        self.api.verify = False  # Allow self-signed certs

        # State
        self.running = True
        self.last_heartbeat = None
        self.agents_running = False
        self.namespace = None  # Set when config is loaded
        self.config = None  # Current testbed config

        # Auto-load config from SWF_TESTBED_CONFIG env var on startup
        env_config = os.getenv('SWF_TESTBED_CONFIG')
        if env_config:
            self.load_config(env_config)

        # Set up REST logging
        self.instance_name = f'agent-manager-{self.username}'
        base_url = os.getenv('SWF_MONITOR_HTTP_URL', 'http://localhost:8002')
        self.logger = setup_rest_logging('agent_manager', self.instance_name, base_url)

        # Set up connection (matching BaseAgent configuration)
        self.conn = stomp.Connection(
            host_and_ports=[(self.mq_host, self.mq_port)],
            vhost=self.mq_host,
            try_loopback_connect=False,
            heartbeats=(30000, 30000),
            auto_content_length=False
        )

        # Configure SSL if enabled
        if self.use_ssl and self.ssl_ca_certs:
            import ssl
            self.conn.transport.set_ssl(
                for_hosts=[(self.mq_host, self.mq_port)],
                ca_certs=self.ssl_ca_certs,
                ssl_version=ssl.PROTOCOL_TLS_CLIENT
            )

        self.conn.set_listener('', self)

        # Signal handling for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"\nReceived signal {signum}, shutting down...")
        self.running = False

    def connect(self):
        """Connect to ActiveMQ and subscribe to control queue."""
        self.logger.info(f"Connecting to ActiveMQ at {self.mq_host}:{self.mq_port}...")
        self.conn.connect(self.mq_user, self.mq_password, wait=True)

        self.logger.info(f"Subscribing to {self.control_queue}...")
        self.conn.subscribe(destination=self.control_queue, id='control', ack='auto')

        self.logger.info(f"User Agent Manager ready for {self.username}")

    def disconnect(self):
        """Disconnect from ActiveMQ."""
        if self.conn.is_connected():
            self.conn.disconnect()

    def on_message(self, frame):
        """Handle incoming control messages."""
        try:
            message = json.loads(frame.body)
            command = message.get('command')

            self.logger.info(f"[{datetime.now().strftime('%H:%M:%S')}] Received command: {command}")

            if command == 'start_testbed':
                config_name = message.get('config_name')
                self.handle_start_testbed(config_name)
            elif command == 'stop_testbed':
                self.handle_stop_testbed()
            elif command == 'restart':
                self.handle_restart()
            elif command == 'status':
                self.handle_status(message.get('reply_to'))
            elif command == 'ping':
                self.handle_ping(message.get('reply_to'))
            else:
                self.logger.info(f"Unknown command: {command}")

        except Exception as e:
            self.logger.error(f"Error processing message: {e}")

    def on_error(self, frame):
        """Handle connection errors."""
        self.logger.error(f"STOMP error: {frame.body}")

    def on_disconnected(self):
        """Handle disconnection."""
        if self.running:
            self.logger.info("Disconnected from ActiveMQ, attempting reconnect...")
            time.sleep(5)
            try:
                self.connect()
            except Exception as e:
                self.logger.error(f"Reconnect failed: {e}")

    def load_config(self, config_name: str = None) -> dict:
        """Load testbed config and update namespace.

        Args:
            config_name: Config file name (default: testbed.toml)
                         Can be just name (looked up in workflows/) or full path

        Returns:
            Parsed config dict
        """
        if config_name is None:
            config_path = self.testbed_dir / DEFAULT_CONFIG
        elif '/' in config_name:
            # Full relative path provided
            config_path = self.testbed_dir / config_name
        else:
            # Just a name, look in workflows/
            if not config_name.endswith('.toml'):
                config_name = f'{config_name}.toml'
            config_path = self.testbed_dir / 'workflows' / config_name

        if not config_path.exists():
            self.logger.error(f"Config not found: {config_path}")
            return {}

        self.logger.info(f"Loading config: {config_path}")
        with open(config_path, 'rb') as f:
            self.config = tomllib.load(f)

        # Update namespace from config
        self.namespace = self.config.get('testbed', {}).get('namespace')
        if self.namespace:
            self.logger.info(f"Namespace: {self.namespace}")
        else:
            self.logger.warning("No namespace in config")

        return self.config

    def get_enabled_agents(self) -> list:
        """Get list of supervisord program names for enabled agents."""
        if not self.config:
            return []

        agents_config = self.config.get('agents', {})
        enabled = []

        for agent_name, agent_conf in agents_config.items():
            if agent_conf.get('enabled', False):
                program_name = AGENT_PROGRAM_MAP.get(agent_name)
                if program_name:
                    enabled.append(program_name)
                else:
                    self.logger.warning(f"Unknown agent '{agent_name}' - no program mapping")

        return enabled

    def handle_start_testbed(self, config_name: str = None):
        """Start the testbed agents and workflow runner."""
        self.logger.info(f"Starting testbed (config: {config_name or 'default'})...")

        # Load config to get namespace and enabled agents
        self.load_config(config_name)

        # Ensure supervisord is running
        if not self._ensure_supervisord():
            self.logger.error("Failed to start supervisord")
            return False

        # Start workflow runner
        if not self._start_program('workflow-runner'):
            self.logger.error("Failed to start workflow-runner")
            return False

        # Start enabled agents from config
        enabled_agents = self.get_enabled_agents()
        if not enabled_agents:
            self.logger.warning("No agents enabled in config")

        for agent in enabled_agents:
            self._start_program(agent)

        self.agents_running = True
        self.logger.info("Testbed started")
        return True

    def handle_stop_testbed(self):
        """Stop all testbed agents."""
        self.logger.info("Stopping testbed...")
        supervisorctl = self._get_venv_bin('supervisorctl')

        result = subprocess.run(
            [supervisorctl, '-c', str(self.testbed_dir / AGENTS_CONF), 'stop', 'all'],
            capture_output=True,
            text=True,
            cwd=self.testbed_dir
        )

        if result.returncode not in [0, 4]:  # 4 = can't connect (already stopped)
            self.logger.error(f"Error stopping testbed: {result.stderr}")
            return False

        self.agents_running = False
        self.logger.info("Testbed stopped")
        return True

    def handle_restart(self):
        """Restart the agent manager with fresh code."""
        self.logger.info("Restarting agent manager...")
        self.handle_stop_testbed()

        # Spawn new agent manager process
        testbed = self._get_venv_bin('testbed')
        subprocess.Popen(
            ['nohup', testbed, 'agent-manager'],
            stdout=open('/tmp/agent-manager.log', 'a'),
            stderr=subprocess.STDOUT,
            cwd=self.testbed_dir,
            start_new_session=True
        )

        self.logger.info("New agent manager spawned, exiting")
        # Clean disconnect before exit
        self.running = False
        try:
            self.disconnect()
        except Exception:
            pass
        os._exit(0)

    def handle_status(self, reply_to: str = None):
        """Get status of testbed agents."""
        supervisorctl = self._get_venv_bin('supervisorctl')
        result = subprocess.run(
            [supervisorctl, '-c', str(self.testbed_dir / AGENTS_CONF), 'status'],
            capture_output=True,
            text=True,
            cwd=self.testbed_dir
        )

        status = {
            'username': self.username,
            'agents_running': self.agents_running,
            'supervisord_status': result.stdout,
            'timestamp': datetime.now().isoformat()
        }

        if reply_to:
            self.conn.send(destination=reply_to, body=json.dumps(status))

        return status

    def handle_ping(self, reply_to: str = None):
        """Respond to ping (liveness check)."""
        response = {
            'status': 'alive',
            'username': self.username,
            'timestamp': datetime.now().isoformat()
        }

        if reply_to:
            self.conn.send(destination=reply_to, body=json.dumps(response))

        return response

    def _get_venv_bin(self, cmd: str) -> str:
        """Get full path to command in venv bin directory."""
        venv_bin = self.testbed_dir / '.venv' / 'bin' / cmd
        if venv_bin.exists():
            return str(venv_bin)
        # Fallback to bare command (may work if venv is activated)
        return cmd

    def _ensure_supervisord(self) -> bool:
        """Start supervisord if not running."""
        conf_path = self.testbed_dir / AGENTS_CONF
        supervisorctl = self._get_venv_bin('supervisorctl')
        supervisord = self._get_venv_bin('supervisord')

        if not conf_path.exists():
            self.logger.error(f"{AGENTS_CONF} not found in {self.testbed_dir}")
            return False

        # Check if already running
        result = subprocess.run(
            [supervisorctl, '-c', str(conf_path), 'status'],
            capture_output=True,
            text=True,
            cwd=self.testbed_dir
        )

        if result.returncode == 4:  # Can't connect - not running
            self.logger.info("Starting supervisord...")
            start_result = subprocess.run(
                [supervisord, '-c', str(conf_path)],
                capture_output=True,
                text=True,
                cwd=self.testbed_dir
            )
            if start_result.returncode != 0:
                self.logger.error(f"Error starting supervisord: {start_result.stderr}")
                return False
            time.sleep(1)

        return True

    def _start_program(self, program_name: str) -> bool:
        """Start a supervisord program."""
        supervisorctl = self._get_venv_bin('supervisorctl')
        result = subprocess.run(
            [supervisorctl, '-c', str(self.testbed_dir / AGENTS_CONF), 'start', program_name],
            capture_output=True,
            text=True,
            cwd=self.testbed_dir
        )

        if result.returncode == 0 or 'already started' in result.stdout.lower():
            self.logger.info(f"  {program_name}: started")
            return True
        else:
            self.logger.error(f"{program_name}: failed - {result.stderr.strip()}")
            return False

    def send_heartbeat(self):
        """Send heartbeat to monitor API (using authenticated session like BaseAgent)."""
        try:
            # Build description with current state
            desc_parts = [f'Agent manager for {self.username}']
            if self.namespace:
                desc_parts.append(f'namespace: {self.namespace}')
            desc_parts.append('MQ: connected')

            data = {
                'instance_name': f'agent-manager-{self.username}',
                'agent_type': 'agent_manager',
                'status': 'OK',
                'operational_state': 'READY',
                'namespace': self.namespace,  # From config, or None if not yet loaded
                'pid': os.getpid(),
                'hostname': os.uname().nodename,
                'description': '. '.join(desc_parts),
            }

            response = self.api.post(
                f"{self.monitor_url}/api/systemagents/heartbeat/",
                json=data,
                timeout=5,
            )

            if response.ok:
                self.last_heartbeat = datetime.now()

        except Exception as e:
            # Heartbeat failure is not fatal
            pass

    def run(self):
        """Main run loop."""
        self.connect()

        # Send immediate heartbeat so MCP can detect us quickly
        self.send_heartbeat()
        last_heartbeat_time = time.time()

        self.logger.info(f"Listening for commands on {self.control_queue}")
        self.logger.info("Press Ctrl+C to stop")

        while self.running:
            try:
                # Send periodic heartbeat
                now = time.time()
                if now - last_heartbeat_time >= HEARTBEAT_INTERVAL:
                    self.send_heartbeat()
                    last_heartbeat_time = now

                time.sleep(1)

            except KeyboardInterrupt:
                break

        self.logger.info("Shutting down...")
        self.disconnect()


def main():
    """Entry point."""
    # Load environment
    from pathlib import Path
    env_file = Path.home() / '.env'
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    if line.startswith('export '):
                        line = line[7:]
                    key, value = line.split('=', 1)
                    os.environ[key] = value.strip('"\'')

    manager = UserAgentManager()
    manager.run()


if __name__ == '__main__':
    main()
