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
from datetime import datetime
from pathlib import Path

import stomp

# Heartbeat interval in seconds
HEARTBEAT_INTERVAL = 30

# Supervisord config for agents
AGENTS_CONF = 'agents.supervisord.conf'


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

        # Monitor API for heartbeats
        self.monitor_url = os.getenv('SWF_MONITOR_HTTP_URL', 'http://localhost:8002')

        # State
        self.running = True
        self.last_heartbeat = None
        self.agents_running = False

        # Set up connection
        self.conn = stomp.Connection(
            host_and_ports=[(self.mq_host, self.mq_port)],
            heartbeats=(30000, 30000)
        )
        self.conn.set_listener('', self)

        # Signal handling for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print(f"\nReceived signal {signum}, shutting down...")
        self.running = False

    def connect(self):
        """Connect to ActiveMQ and subscribe to control queue."""
        print(f"Connecting to ActiveMQ at {self.mq_host}:{self.mq_port}...")
        self.conn.connect(self.mq_user, self.mq_password, wait=True)

        print(f"Subscribing to {self.control_queue}...")
        self.conn.subscribe(destination=self.control_queue, id='control', ack='auto')

        print(f"User Agent Manager ready for {self.username}")

    def disconnect(self):
        """Disconnect from ActiveMQ."""
        if self.conn.is_connected():
            self.conn.disconnect()

    def on_message(self, frame):
        """Handle incoming control messages."""
        try:
            message = json.loads(frame.body)
            command = message.get('command')

            print(f"[{datetime.now().strftime('%H:%M:%S')}] Received command: {command}")

            if command == 'start_testbed':
                config_name = message.get('config_name')
                self.handle_start_testbed(config_name)
            elif command == 'stop_testbed':
                self.handle_stop_testbed()
            elif command == 'status':
                self.handle_status(message.get('reply_to'))
            elif command == 'ping':
                self.handle_ping(message.get('reply_to'))
            else:
                print(f"Unknown command: {command}")

        except Exception as e:
            print(f"Error processing message: {e}")

    def on_error(self, frame):
        """Handle connection errors."""
        print(f"STOMP error: {frame.body}")

    def on_disconnected(self):
        """Handle disconnection."""
        if self.running:
            print("Disconnected from ActiveMQ, attempting reconnect...")
            time.sleep(5)
            try:
                self.connect()
            except Exception as e:
                print(f"Reconnect failed: {e}")

    def handle_start_testbed(self, config_name: str = None):
        """Start the testbed agents and workflow runner."""
        print(f"Starting testbed (config: {config_name or 'default'})...")

        # Ensure supervisord is running
        if not self._ensure_supervisord():
            print("Failed to start supervisord")
            return False

        # Start workflow runner
        if not self._start_program('workflow-runner'):
            print("Failed to start workflow-runner")
            return False

        # Start agents based on config
        # For now, start all defined agents
        agents = ['example-data-agent', 'example-processing-agent']
        for agent in agents:
            self._start_program(agent)

        self.agents_running = True
        print("Testbed started")
        return True

    def handle_stop_testbed(self):
        """Stop all testbed agents."""
        print("Stopping testbed...")

        result = subprocess.run(
            ['supervisorctl', '-c', str(self.testbed_dir / AGENTS_CONF), 'stop', 'all'],
            capture_output=True,
            text=True,
            cwd=self.testbed_dir
        )

        self.agents_running = False
        print("Testbed stopped")
        return True

    def handle_status(self, reply_to: str = None):
        """Get status of testbed agents."""
        result = subprocess.run(
            ['supervisorctl', '-c', str(self.testbed_dir / AGENTS_CONF), 'status'],
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

    def _ensure_supervisord(self) -> bool:
        """Start supervisord if not running."""
        conf_path = self.testbed_dir / AGENTS_CONF

        if not conf_path.exists():
            print(f"Error: {AGENTS_CONF} not found in {self.testbed_dir}")
            return False

        # Check if already running
        result = subprocess.run(
            ['supervisorctl', '-c', str(conf_path), 'status'],
            capture_output=True,
            text=True,
            cwd=self.testbed_dir
        )

        if result.returncode == 4:  # Can't connect - not running
            print("Starting supervisord...")
            subprocess.run(
                ['supervisord', '-c', str(conf_path)],
                cwd=self.testbed_dir
            )
            time.sleep(1)

        return True

    def _start_program(self, program_name: str) -> bool:
        """Start a supervisord program."""
        result = subprocess.run(
            ['supervisorctl', '-c', str(self.testbed_dir / AGENTS_CONF), 'start', program_name],
            capture_output=True,
            text=True,
            cwd=self.testbed_dir
        )

        if result.returncode == 0 or 'already started' in result.stdout.lower():
            print(f"  {program_name}: started")
            return True
        else:
            print(f"  {program_name}: failed - {result.stderr.strip()}")
            return False

    def send_heartbeat(self):
        """Send heartbeat to monitor API."""
        import requests

        try:
            data = {
                'instance_name': f'agent-manager-{self.username}',
                'agent_type': 'agent_manager',
                'status': 'OK',
                'operational_state': 'READY',
                'namespace': self.username,
                'pid': os.getpid(),
                'hostname': os.uname().nodename,
                'metadata': {
                    'control_queue': self.control_queue,
                    'agents_running': self.agents_running
                }
            }

            response = requests.post(
                f"{self.monitor_url}/api/agents/heartbeat/",
                json=data,
                timeout=5
            )

            if response.ok:
                self.last_heartbeat = datetime.now()

        except Exception as e:
            # Heartbeat failure is not fatal
            pass

    def run(self):
        """Main run loop."""
        self.connect()

        last_heartbeat_time = 0

        print(f"Listening for commands on {self.control_queue}")
        print("Press Ctrl+C to stop")

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

        print("Shutting down...")
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
