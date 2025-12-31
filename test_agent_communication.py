#!/usr/bin/env python3
"""
Simple test script to verify agent-monitor communication works.
This uses the same approach as the working agents.
"""

import os
import sys
import time
import requests
from pathlib import Path

def setup_environment():
    """Auto-activate venv and load environment variables."""
    script_dir = Path(__file__).resolve().parent
    
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
    
    # Load ~/.env environment variables
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
                    value = value.strip('"\'')
                    # Skip entries with unexpanded shell variables
                    if '$' in value:
                        continue
                    os.environ[key] = value

    # Unset proxy variables to prevent localhost routing through proxy
    for proxy_var in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
        if proxy_var in os.environ:
            del os.environ[proxy_var]
    
    return True

def test_monitor_connection():
    """Test basic connection to monitor using same approach as agents."""
    print("Testing monitor connection...")
    
    monitor_url = os.getenv('SWF_MONITOR_URL', 'https://localhost:8443')
    api_token = os.getenv('SWF_API_TOKEN')
    
    if not api_token:
        print("❌ No SWF_API_TOKEN found in environment")
        return False
    
    print(f"Monitor URL: {monitor_url}")
    print(f"API Token: {api_token[:10]}...")
    
    # Configure session exactly like agents do
    session = requests.Session()
    session.headers.update({'Authorization': f'Token {api_token}'})
    session.verify = False  # Allow self-signed certs
    session.proxies = {'http': None, 'https': None}
    
    # Suppress SSL warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    try:
        # Test heartbeat endpoint like agents do
        heartbeat_data = {
            'instance_name': 'test-script-agent',
            'agent_type': 'TEST',
            'status': 'OK',
            'description': 'Test script for agent-monitor communication',
            'mq_connected': False
        }
        
        print("Sending heartbeat to monitor...")
        response = session.post(
            f"{monitor_url}/api/systemagents/heartbeat/",
            json=heartbeat_data,
            timeout=10
        )
        
        print(f"Response status: {response.status_code}")
        print(f"Response text: {response.text}")
        
        if response.status_code in [200, 201]:
            print("✅ SUCCESS: Heartbeat sent successfully!")
            result = response.json()
            print(f"Agent registered as: {result.get('instance_name')}")
            return True
        else:
            print(f"❌ FAILED: Unexpected response {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError as e:
        print(f"❌ CONNECTION ERROR: {e}")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def main():
    print("=== Agent-Monitor Communication Test ===")
    
    if not setup_environment():
        sys.exit(1)
    
    if test_monitor_connection():
        print("✅ Test PASSED: Agent-monitor communication works!")
        sys.exit(0)
    else:
        print("❌ Test FAILED: Agent-monitor communication not working")
        sys.exit(1)

if __name__ == "__main__":
    main()