#!/usr/bin/env python3
"""
Workflow Orchestrator - Start agents and trigger workflows.

Usage:
    testbed run <name>           # Run workflows/<name>.toml
    testbed run                  # Run workflows/testbed.toml
"""

import os
import sys
import subprocess
import time
import tomllib
from pathlib import Path


# Agent name mapping: testbed.toml key -> supervisord program name
AGENT_PROGRAM_MAP = {
    'data': 'example-data-agent',
    'processing': 'example-processing-agent',
    'fastmon': 'example-fastmon-agent',
    'fast_processing': 'fast-processing-agent',
}

AGENTS_CONF = 'agents.supervisord.conf'
AGENTS_SOCK = '/tmp/swf-agents-supervisor.sock'


def load_config(config_name: str = None) -> dict:
    """
    Load workflow configuration.

    Args:
        config_name: Name of config file (without path/extension), or None for testbed.toml

    Returns:
        Merged configuration dict
    """
    workflows_dir = Path(__file__).parent

    if config_name is None:
        config_path = workflows_dir / 'testbed.toml'
    else:
        # Try exact name first, then with .toml, then _default.toml
        candidates = [
            workflows_dir / config_name,
            workflows_dir / f'{config_name}.toml',
            workflows_dir / f'{config_name}_default.toml',
        ]
        config_path = None
        for candidate in candidates:
            if candidate.exists():
                config_path = candidate
                break
        if config_path is None:
            raise FileNotFoundError(f"Config not found: {config_name} (tried {[str(c) for c in candidates]})")

    with open(config_path, 'rb') as f:
        config = tomllib.load(f)

    return config


def ensure_supervisord_running() -> bool:
    """Start agents supervisord if not already running."""
    testbed_dir = Path(__file__).parent.parent

    # Check if supervisord is running
    result = subprocess.run(
        ['supervisorctl', '-c', str(testbed_dir / AGENTS_CONF), 'status'],
        capture_output=True,
        text=True,
        cwd=testbed_dir
    )

    if result.returncode == 4:  # Can't connect
        print(f"Starting agents supervisord...")
        subprocess.run(
            ['supervisord', '-c', str(testbed_dir / AGENTS_CONF)],
            cwd=testbed_dir
        )
        time.sleep(1)
        return True

    return True


def start_agent(agent_name: str) -> bool:
    """
    Start an agent via supervisorctl.

    Args:
        agent_name: Key from testbed.toml agents section (e.g., 'processing')

    Returns:
        True if agent started or already running
    """
    program_name = AGENT_PROGRAM_MAP.get(agent_name)
    if not program_name:
        print(f"Unknown agent: {agent_name}")
        return False

    testbed_dir = Path(__file__).parent.parent

    result = subprocess.run(
        ['supervisorctl', '-c', str(testbed_dir / AGENTS_CONF), 'start', program_name],
        capture_output=True,
        text=True,
        cwd=testbed_dir
    )

    if result.returncode == 0 or 'already started' in result.stdout.lower():
        print(f"  {program_name}: started")
        return True
    else:
        print(f"  {program_name}: failed to start - {result.stderr.strip()}")
        return False


def verify_agent_pid(agent_name: str) -> bool:
    """
    Verify agent process exists by checking supervisord status.

    Args:
        agent_name: Key from testbed.toml agents section

    Returns:
        True if PID exists and process is running
    """
    program_name = AGENT_PROGRAM_MAP.get(agent_name)
    if not program_name:
        return False

    testbed_dir = Path(__file__).parent.parent

    result = subprocess.run(
        ['supervisorctl', '-c', str(testbed_dir / AGENTS_CONF), 'status', program_name],
        capture_output=True,
        text=True,
        cwd=testbed_dir
    )

    # Output like: "example-processing-agent   RUNNING   pid 12345, uptime 0:00:05"
    return 'RUNNING' in result.stdout


def start_workflow_runner() -> bool:
    """Start the workflow runner agent."""
    testbed_dir = Path(__file__).parent.parent

    result = subprocess.run(
        ['supervisorctl', '-c', str(testbed_dir / AGENTS_CONF), 'start', 'workflow-runner'],
        capture_output=True,
        text=True,
        cwd=testbed_dir
    )

    if result.returncode == 0 or 'already started' in result.stdout.lower():
        print(f"  workflow-runner: started")
        return True
    else:
        print(f"  workflow-runner: failed to start - {result.stderr.strip()}")
        return False


def send_run_workflow(config: dict) -> bool:
    """
    Send run_workflow command to WorkflowRunner via ActiveMQ.

    Args:
        config: Configuration dict with workflow and parameters

    Returns:
        True if message sent successfully
    """
    # Import here to avoid loading STOMP if not needed
    from workflows.send_workflow_command import CommandSender

    workflow_config = config.get('workflow', {})
    workflow_name = workflow_config.get('name', 'stf_datataking')
    workflow_config_name = workflow_config.get('config', 'fast_processing_default')
    realtime = workflow_config.get('realtime', True)

    # Get parameter overrides
    params = config.get('parameters', {})

    sender = CommandSender(config_path=str(Path(__file__).parent / 'testbed.toml'))
    sender.connect()

    try:
        sender.send_run_workflow(
            workflow_name,
            config=workflow_config_name,
            realtime=realtime,
            **params
        )
        return True
    finally:
        sender.disconnect()


def run(config_name: str = None) -> bool:
    """
    Start agents and trigger workflow.

    Args:
        config_name: Name of config file, or None for testbed.toml

    Returns:
        True if workflow started successfully
    """
    # Load configuration
    try:
        config = load_config(config_name)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return False

    namespace = config.get('testbed', {}).get('namespace')
    if not namespace:
        print("Error: namespace not set in [testbed] section")
        return False

    print(f"Namespace: {namespace}")

    # Ensure supervisord is running
    ensure_supervisord_running()

    # Start workflow runner first
    print("Starting workflow runner...")
    if not start_workflow_runner():
        print("Error: Failed to start workflow runner")
        return False

    # Give it a moment to connect
    time.sleep(2)

    # Start enabled agents
    agents_config = config.get('agents', {})
    enabled_agents = []

    print("Starting agents...")
    for agent_name, agent_config in agents_config.items():
        if isinstance(agent_config, dict) and agent_config.get('enabled', False):
            if start_agent(agent_name):
                enabled_agents.append(agent_name)

    if not enabled_agents:
        print("Warning: No agents enabled in configuration")

    # Brief pause for agents to initialize
    time.sleep(2)

    # Verify PIDs
    print("Verifying agents...")
    all_running = True
    for agent_name in enabled_agents:
        if verify_agent_pid(agent_name):
            print(f"  {agent_name}: running")
        else:
            print(f"  {agent_name}: NOT running")
            all_running = False

    if not all_running:
        print("Warning: Some agents failed to start")

    # Send run_workflow command
    print("Triggering workflow...")
    if send_run_workflow(config):
        workflow_name = config.get('workflow', {}).get('name', 'stf_datataking')
        print(f"Workflow '{workflow_name}' triggered. Use 'testbed status' to monitor.")
        return True
    else:
        print("Error: Failed to send workflow command")
        return False


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Start agents and run workflow')
    parser.add_argument('config', nargs='?', help='Config name (default: testbed.toml)')
    args = parser.parse_args()

    success = run(args.config)
    sys.exit(0 if success else 1)
