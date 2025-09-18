#!/usr/bin/env python3
"""
System Status Reporter for SWF Testbed
Reports actual status of required system services.
Simple service status check - no deep connectivity testing.
"""

import subprocess
import sys
import os
import requests
from pathlib import Path

# Auto-restart with project venv Python if not already using it
def ensure_venv_python():
    """Ensure we're running with the project venv Python, restart if not."""
    # Use SWF_HOME if set, otherwise derive from script location
    if 'SWF_HOME' in os.environ:
        swf_home = Path(os.environ['SWF_HOME'])
        venv_path = swf_home / 'swf-testbed' / '.venv'
    else:
        # Derive from script location
        venv_path = Path(__file__).resolve().parent / '.venv'
    
    venv_python = venv_path / 'bin' / 'python'
    
    # Check if venv exists
    if not venv_python.exists():
        print(f"❌ Error: Virtual environment not found at {venv_path}")
        sys.exit(1)
    
    # Check if we're already using the venv Python
    current_python = Path(sys.executable).resolve()
    expected_python = venv_python.resolve()
    
    try:
        # If not the same file, restart with correct Python
        if not current_python.samefile(expected_python):
            print(f"🔄 Restarting with project venv Python...")
            os.execv(str(venv_python), [str(venv_python)] + sys.argv)
    except (OSError, FileNotFoundError):
        # If we can't verify samefile, compare paths
        if current_python != expected_python:
            print(f"🔄 Restarting with project venv Python...")
            os.execv(str(venv_python), [str(venv_python)] + sys.argv)

# Ensure we're using venv Python before doing anything else
ensure_venv_python()

def setup_environment():
    """Auto-activate venv and load environment variables - same pattern as run_tests."""
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
    
    return True

def get_active_services():
    """Get list of all active systemd services."""
    try:
        result = subprocess.run(['/usr/bin/systemctl', 'list-units', '--type=service', '--state=active', '--no-legend'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            services = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    service_name = line.split()[0]
                    services.append(service_name)
            return services
        return []
    except Exception as e:
        print(f"    DEBUG: Failed to get active services: {e}")
        return []

def find_service_by_pattern(active_services, patterns):
    """Find service matching any of the given patterns."""
    for service in active_services:
        for pattern in patterns:
            if pattern in service.lower():
                return service
    return None

def check_django_status():
    """Check if Django monitor is running and responding."""
    monitor_urls = [
        'https://pandaserver02.sdcc.bnl.gov/swf-monitor',
        'http://pandaserver02.sdcc.bnl.gov/swf-monitor',
        os.getenv('SWF_MONITOR_URL', 'https://localhost:8443'),
        os.getenv('SWF_MONITOR_HTTP_URL', 'http://localhost:8002')
    ]
    
    session = requests.Session()
    session.verify = False  # Allow self-signed certs
    session.proxies = {'http': None, 'https': None}
    session.timeout = 5
    
    # Suppress SSL warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    results = []
    seen_urls = set()
    for url in monitor_urls:
        if url not in seen_urls:  # Remove duplicates while preserving order
            seen_urls.add(url)
            try:
                response = session.get(f"{url}/api/systemagents/")
                results.append((url, {
                    'status': response.status_code,
                    'reachable': True,
                    'response_time': response.elapsed.total_seconds()
                }))
            except Exception as e:
                results.append((url, {
                    'status': None,
                    'reachable': False,
                    'error': str(e)
                }))
    
    return results

def main():
    """Main status report."""
    print("=" * 60)
    print("SWF TESTBED SYSTEM STATUS REPORT")
    print("=" * 60)
    
    # Setup environment (we're already guaranteed to be using venv Python)
    if not setup_environment():
        print("❌ Failed to setup environment")
        return 1
    
    # Check system services we expect
    print("\n🔧 SYSTEM SERVICES:")
    
    # Get all active services
    all_active_services = get_active_services()
    
    # Find PostgreSQL service (any version)
    postgres_service = find_service_by_pattern(all_active_services, ['postgresql'])
    if postgres_service:
        print(f"  ✅ PostgreSQL ({postgres_service}) - ACTIVE")
    else:
        print(f"  ❌ PostgreSQL - INACTIVE")
    
    # Find ActiveMQ service (artemis, activemq, etc.)
    activemq_service = find_service_by_pattern(all_active_services, ['artemis', 'activemq'])
    if activemq_service:
        print(f"  ✅ ActiveMQ ({activemq_service}) - ACTIVE")
    else:
        print(f"  ❌ ActiveMQ - INACTIVE")
    
    # Find Redis service
    redis_service = find_service_by_pattern(all_active_services, ['redis'])
    if redis_service:
        print(f"  ✅ Redis ({redis_service}) - ACTIVE")
    else:
        print(f"  ❌ Redis - INACTIVE")
    
    # Keep track of what's running for final assessment
    active_services = []
    if postgres_service:
        active_services.append(postgres_service)
    if activemq_service:
        active_services.append(activemq_service)
    if redis_service:
        active_services.append(redis_service)
    
    # Check Django monitor status
    print("\n🌐 DJANGO MONITOR STATUS:")
    django_results = check_django_status()
    
    for url, result in django_results:
        if result['reachable']:
            print(f"  ✅ {url} - HTTP {result['status']} ({result['response_time']:.2f}s)")
        else:
            print(f"  ❌ {url} - UNREACHABLE: {result.get('error', 'Unknown error')}")
    
    # Environment check
    print("\n🌍 ENVIRONMENT VARIABLES:")
    env_vars = [
        'SWF_MONITOR_URL',
        'SWF_MONITOR_HTTP_URL',
        'SWF_API_TOKEN', 
        'ACTIVEMQ_HOST',
        'ACTIVEMQ_PORT',
        'DB_HOST',
        'DB_NAME',
        'DB_USER'
    ]
    
    for var in env_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            if 'TOKEN' in var:
                display_value = value[:10] + "..." if len(value) > 10 else "***"
            else:
                display_value = value
            print(f"  ✅ {var} = {display_value}")
        else:
            print(f"  ❌ {var} = NOT SET")
    
    print("\n" + "=" * 60)
    print("READY TO RUN daq_simulator.py?" )
    
    # Final readiness check
    has_activemq = activemq_service is not None
    has_postgres = postgres_service is not None
    has_redis = redis_service is not None
    has_env = os.getenv('SWF_API_TOKEN') and os.getenv('ACTIVEMQ_HOST')
    has_django = any(result['reachable'] and result['status'] in [200, 403] 
                    for url, result in django_results)
    
    if has_activemq and has_postgres and has_redis and has_env and has_django:
        print("✅ YES - All required services appear ready")
        return 0
    else:
        print("❌ NO - Missing required services or configuration")
        if not has_activemq:
            print("  - Missing ActiveMQ service")
        if not has_postgres:
            print("  - Missing PostgreSQL service")
        if not has_redis:
            print("  - Missing Redis service")
        if not has_env:
            print("  - Missing environment variables")  
        if not has_django:
            print("  - Django monitor not responding")
        return 1

if __name__ == "__main__":
    sys.exit(main())