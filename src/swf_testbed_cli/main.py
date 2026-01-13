import typer
import shutil
from pathlib import Path
import subprocess
import os
import sys
import psutil

app = typer.Typer(help="ePIC Streaming Workflow Testbed CLI")

SUPERVISORD_CONF_TEMPLATE = Path(__file__).parent.parent.parent / "supervisord.conf"

@app.command()
def init():
    """
    Initializes the testbed environment by creating a supervisord.conf file
    and a logs directory.
    """
    print("Initializing testbed environment...")

    # Create logs directory
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    print(f"Created directory: {logs_dir.resolve()}")

    # Copy supervisord.conf
    dest_conf = Path("supervisord.conf")
    if dest_conf.exists():
        print(f"{dest_conf} already exists. Skipping.")
    else:
        shutil.copy(SUPERVISORD_CONF_TEMPLATE, dest_conf)
        print(f"Created {dest_conf}")

def _setup_environment():
    """Set up the SWF_HOME environment variable for the current process and children."""
    script_dir = Path(__file__).parent.parent.parent.absolute()
    swf_home = script_dir.parent
    os.environ["SWF_HOME"] = str(swf_home)
    print(f"SWF_HOME set to: {swf_home}")
    return swf_home

@app.command()
def start():
    """
    Starts the testbed services using supervisord and docker compose.
    """
    # Set up environment
    _setup_environment()
    
    # Check for required files
    if not Path("docker-compose.yml").is_file():
        print("Error: docker-compose.yml not found in the current directory. "
              "Please ensure you are in the project root and the file exists.")
        raise typer.Exit(code=1)
    if not Path("supervisord.conf").is_file():
        print("Error: supervisord.conf not found in the current directory. "
              "Please ensure you have the correct configuration file present.")
        raise typer.Exit(code=1)
    print("Starting testbed services...")
    print("--- Starting Docker services ---")
    subprocess.run(["docker", "compose", "up", "-d"])
    print("--- Starting supervisord services ---")
    # Check if supervisord is running, start it if needed
    if not _check_supervisord_running():
        print("supervisord is not running, starting it now...")
        subprocess.run(["supervisord", "-c", "supervisord.conf"])
    else:
        print("supervisord is already running.")
    subprocess.run(["supervisorctl", "-c", "supervisord.conf", "start", "all"])

@app.command()
def stop():
    """
    Stops the testbed services.
    """
    print("Stopping testbed services...")
    print("--- Stopping supervisord services ---")
    subprocess.run(["supervisorctl", "-c", "supervisord.conf", "stop", "all"])
    print("--- Stopping Docker services ---")
    subprocess.run(["docker", "compose", "down"])

@app.command()
def status():
    """
    Checks the status of the testbed services.
    """
    print("--- Docker services status ---")
    subprocess.run(["docker", "compose", "ps"])
    print("\n--- supervisord services status ---")
    subprocess.run(["supervisorctl", "-c", "supervisord.conf", "status"])
    _print_workflow_status()

def _check_supervisord_running() -> bool:
    """Checks if supervisord is running by trying to connect to it."""
    try:
        result = subprocess.run(
            ["supervisorctl", "-c", "supervisord.conf", "status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        # supervisorctl returns 0 if all processes OK, 3 if some failed, 4 if can't connect
        # Return True if we can connect (codes 0 or 3), False if can't connect (code 4+)
        return result.returncode in [0, 3]
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False

def _check_postgres_connection():
    """Checks the connection to the PostgreSQL database."""
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_user = os.getenv("DB_USER", "admin")
    db_name = os.getenv("DB_NAME", "swfdb")

    print(f"--- Checking PostgreSQL connection at {db_host}:{db_port} ---")
    try:
        result = subprocess.run(
            ["pg_isready", "-h", db_host, "-p", db_port, "-U", db_user, "-d", db_name],
            capture_output=True,
            text=True,
            check=True,
        )
        print(result.stdout.strip())
        if "accepting connections" not in result.stdout:
            print("Warning: PostgreSQL is not ready.")
            return False
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Error checking PostgreSQL status: {e}")
        print("Please ensure PostgreSQL is running and `pg_isready` is in your PATH.")
        return False

def _check_activemq_connection():
    """Checks if ActiveMQ is listening on its port."""
    amq_port = os.getenv("ACTIVEMQ_PORT", "61616")
    print(f"--- Checking ActiveMQ connection on port {amq_port} ---")
    result = subprocess.run(f"lsof -i -P -n | grep LISTEN | grep ':{amq_port}'", shell=True, capture_output=True)
    if result.returncode == 0:
        print(f"ActiveMQ appears to be running and listening on port {amq_port}.")
        return True
    else:
        print(f"Warning: Could not detect a service listening on port {amq_port}.")
        print("Please ensure ActiveMQ is running.")
        return False


def _get_workflow_status():
    """Query monitor API for running workflows and agent states."""
    import requests

    monitor_url = os.getenv("SWF_MONITOR_HTTP_URL", "http://localhost:8002")
    api_token = os.getenv("SWF_API_TOKEN", "")

    headers = {}
    if api_token:
        headers["Authorization"] = f"Token {api_token}"

    results = {"executions": [], "agents": [], "error": None}

    try:
        # Get running executions
        resp = requests.get(
            f"{monitor_url}/api/workflow-executions/",
            params={"status": "running"},
            headers=headers,
            timeout=5,
            verify=False
        )
        if resp.status_code == 200:
            data = resp.json()
            # Handle both paginated (dict with "results") and direct list response
            results["executions"] = data.get("results", data) if isinstance(data, dict) else data

        # Get active agents (exclude EXITED)
        resp = requests.get(
            f"{monitor_url}/api/systemagents/",
            headers=headers,
            timeout=5,
            verify=False
        )
        if resp.status_code == 200:
            data = resp.json()
            all_agents = data.get("results", data) if isinstance(data, dict) else data
            # Filter to non-EXITED agents with recent heartbeat
            from datetime import datetime, timedelta, timezone
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
            results["agents"] = [
                a for a in all_agents
                if a.get("operational_state") != "EXITED"
            ]

    except requests.exceptions.RequestException as e:
        results["error"] = str(e)

    return results


def _print_workflow_status():
    """Print workflow and agent status from monitor."""
    print("\n--- Workflow Status ---")

    status = _get_workflow_status()

    if status["error"]:
        print(f"Could not query monitor API: {status['error']}")
        return

    # Running executions
    executions = status["executions"]
    if executions:
        print(f"Running workflows: {len(executions)}")
        for ex in executions:
            exec_id = ex.get("execution_id", "unknown")
            namespace = ex.get("namespace", "")
            start_time = ex.get("start_time", "")[:19] if ex.get("start_time") else ""
            print(f"  {exec_id} (namespace: {namespace}, started: {start_time})")
    else:
        print("Running workflows: 0")

    # Active agents
    agents = status["agents"]
    if agents:
        print(f"\nActive agents: {len(agents)}")
        for a in agents[:10]:  # Limit output
            name = a.get("instance_name", "unknown")
            state = a.get("operational_state", "?")
            agent_type = a.get("agent_type", "?")
            print(f"  {name}: {state} ({agent_type})")
        if len(agents) > 10:
            print(f"  ... and {len(agents) - 10} more")
    else:
        print("\nActive agents: 0")

@app.command("start-local")
def start_local():
    """
    Starts the local testbed services using supervisord.
    """
    # Set up environment
    _setup_environment()
    
    print("Starting local testbed services...")

    db_ok = _check_postgres_connection()
    amq_ok = _check_activemq_connection()

    if not db_ok or not amq_ok:
        print("\nError: One or more background services are not available. Aborting.")
        raise typer.Abort()

    print("\n--- Starting supervisord services ---")
    if not _check_supervisord_running():
        print("supervisord is not running, starting it now...")
        subprocess.run(["supervisord", "-c", "supervisord.conf"])
    else:
        print("supervisord is already running.")
    
    subprocess.run(["supervisorctl", "-c", "supervisord.conf", "start", "all"])

@app.command("stop-local")
def stop_local():
    """
    Stops the local testbed services.
    """
    print("--- Stopping local supervisord services ---")
    subprocess.run(["supervisorctl", "-c", "supervisord.conf", "stop", "all"])
    # Optionally, shutdown supervisord itself
    # subprocess.run(["supervisorctl", "-c", "supervisord.conf", "shutdown"])

@app.command("status-local")
def status_local():
    """
    Checks the status of the locally running testbed services.
    """
    # Set up environment (needed for supervisord)
    _setup_environment()

    print("--- Local services status ---")
    _check_postgres_connection()
    _check_activemq_connection()
    print("\n--- supervisord services status ---")
    # Check if supervisord is running
    if _check_supervisord_running():
        print("supervisord is running.")
        subprocess.run(["supervisorctl", "-c", "supervisord.conf", "status"])
    else:
        print("supervisord is not running.")
    _print_workflow_status()


@app.command("agent-manager")
def agent_manager():
    """
    Start the user agent manager daemon.

    This lightweight daemon listens for MCP commands to control your testbed.
    It manages agent processes via supervisord and sends heartbeats to the monitor.

    Run this once and leave it running. MCP can then start/stop your testbed remotely.

    Example:
        testbed agent-manager          # Start in foreground
        testbed agent-manager &        # Start in background
        nohup testbed agent-manager &  # Start and persist after logout
    """
    _setup_environment()

    from .user_agent_manager import UserAgentManager

    manager = UserAgentManager()
    manager.run()


@app.command()
def run(
    config_name: str = typer.Argument(
        None,
        help="Config name (e.g., 'fast_processing' loads workflows/fast_processing.toml). "
             "If not specified, uses workflows/testbed.toml"
    )
):
    """
    Start agents and run a workflow.

    Examples:
        testbed run                    # Run using workflows/testbed.toml
        testbed run fast_processing    # Run using workflows/fast_processing.toml
    """
    _setup_environment()

    # Add swf-testbed to Python path
    testbed_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(testbed_root))

    from workflows.orchestrator import run as orchestrator_run

    success = orchestrator_run(config_name)
    if not success:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
