#!/usr/bin/env python3
"""
DAQ Simulator - SimPy-based ePIC DAQ state machine simulation
Generates workflow events that drive the testbed agents
"""

import simpy
import json
import os
import sys
import logging
from datetime import datetime
from pathlib import Path
import stomp
import time

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

# Import the centralized logging from swf-common-lib
from swf_common_lib.rest_logging import setup_rest_logging


class DAQSimulator:
    """ePIC DAQ state machine simulator using SimPy"""
    
    def __init__(self, env, debug=False):
        self.env = env
        self.file_counter = 0  # Serial counter for unique filenames across all runs
        self.current_run_id = None
        self.DEBUG = debug

        # Agent identity - create unique name with username and sequential ID
        import getpass
        username = getpass.getuser()
        agent_id = self.get_next_agent_id()
        self.agent_name = f'daq-simulator-{username}-{agent_id}'
        self.agent_type = 'daqsim'
        
        # Monitor API configuration
        self.monitor_url = os.getenv('SWF_MONITOR_URL', 'https://pandaserver02.sdcc.bnl.gov/swf-monitor')
        self.api_token = os.getenv('SWF_API_TOKEN')
        
        # Set up API session
        import requests
        self.api_session = requests.Session()
        if self.api_token:
            self.api_session.headers.update({'Authorization': f'Token {self.api_token}'})
        
        # For localhost development, disable SSL verification
        if 'localhost' in self.monitor_url:
            self.api_session.verify = False
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # STF generation parameters
        self.stf_interval = 2  # STFs every 2 seconds during physics (~0.5Hz)
        
        # Set up centralized logging
        self.logger = setup_rest_logging('daqsim-agent', 'daqsim-simulator-1')
        
        # Create output directories
        Path("daq_events").mkdir(exist_ok=True)
        Path("daq_data").mkdir(exist_ok=True)
        
        # Setup ActiveMQ connection
        self.setup_activemq()
        
        # Send initial registration/heartbeat
        self.send_heartbeat()
    
    def get_next_run_number(self):
        """Get the next run number from persistent state API."""
        try:
            url = f"{self.monitor_url}/api/state/next-run-number/"
            response = self.api_session.post(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data.get('status') == 'success':
                run_number = data.get('run_number')
                self.logger.info(f"Got next run number from persistent state: {run_number}")
                return str(run_number)  # Return as string for consistency
            else:
                raise RuntimeError(f"API returned error: {data.get('error', 'Unknown error')}")
                
        except Exception as e:
            self.logger.error(f"Failed to get next run number from API: {e}")
            raise RuntimeError(f"Critical failure getting run number: {e}") from e

    def get_next_agent_id(self):
        """Get the next agent ID from persistent state API."""
        try:
            url = f"{self.monitor_url}/api/state/next-agent-id/"
            response = self.api_session.post(url, timeout=10)
            response.raise_for_status()

            data = response.json()
            if data.get('status') == 'success':
                agent_id = data.get('agent_id')
                self.logger.info(f"Got next agent ID from persistent state: {agent_id}")
                return str(agent_id)  # Return as string for consistency
            else:
                raise RuntimeError(f"API returned error: {data.get('error', 'Unknown error')}")

        except Exception as e:
            self.logger.error(f"Failed to get next agent ID from API: {e}")
            raise RuntimeError(f"Critical failure getting agent ID: {e}") from e
        
    def setup_activemq(self):
        """Setup connection to ActiveMQ broker using same pattern as base_agent"""
        # Configuration from environment variables
        self.mq_host = os.getenv('ACTIVEMQ_HOST', 'pandaserver02.sdcc.bnl.gov')
        self.mq_port = int(os.getenv('ACTIVEMQ_PORT', 61612))
        self.mq_user = os.getenv('ACTIVEMQ_USER', 'wenauseic')
        self.mq_password = os.getenv('ACTIVEMQ_PASSWORD', 'swf123_wenauseic')
        self.use_ssl = os.getenv('ACTIVEMQ_USE_SSL', 'True').lower() == 'true'
        self.ssl_ca_certs = os.getenv('ACTIVEMQ_SSL_CA_CERTS', '/eic/u/wenauseic/github/swf-monitor/full-chain.pem')
        
        self.logger.info(f"Connecting to ActiveMQ at {self.mq_host}:{self.mq_port}")
        
        # Create connection matching base_agent pattern
        self.conn = stomp.Connection(
            host_and_ports=[(self.mq_host, self.mq_port)],
            vhost=self.mq_host,
            try_loopback_connect=False
        )
        
        # Configure SSL if enabled
        if self.use_ssl:
            import ssl
            self.logger.info(f"Configuring SSL connection with CA certs: {self.ssl_ca_certs}")
            self.conn.transport.set_ssl(
                for_hosts=[(self.mq_host, self.mq_port)],
                ca_certs=self.ssl_ca_certs,
                ssl_version=ssl.PROTOCOL_TLS_CLIENT
            )
        
        try:
            # Connect with STOMP version 1.1
            self.conn.connect(
                self.mq_user, 
                self.mq_password, 
                wait=True, 
                version='1.1',
                headers={
                    'client-id': 'daqsim-simulator',
                    'heart-beat': '30000,3600000'  # Send heartbeat every 30sec, timeout after 1hr
                }
            )
            self.logger.info("Successfully connected to ActiveMQ")
            
            # Set the destination topic
            self.destination = os.getenv('ACTIVEMQ_HEARTBEAT_TOPIC', 'epictopic')
            
        except Exception as e:
            self.logger.error(f"Failed to connect to ActiveMQ: {e}")
            raise
    
    def send_message(self, destination, message_body):
        """Send a JSON message to a specific destination - same as base_agent"""
        try:
            self.conn.send(body=json.dumps(message_body), destination=destination)
            self.logger.debug(f"Sent {message_body.get('msg_type')} message to '{destination}'")
        except Exception as e:
            self.logger.error(f"Failed to send message to '{destination}': {e}")
    
    def send_heartbeat(self):
        """Register/update this agent in the monitor system."""
        try:
            # Determine status based on ActiveMQ connection
            mq_connected = hasattr(self, 'conn') and self.conn and self.conn.is_connected()
            status = "OK" if mq_connected else "WARNING"
            
            payload = {
                "instance_name": self.agent_name,
                "agent_type": self.agent_type,
                "status": status,
                "description": f"DAQ Simulator - SimPy-based ePIC DAQ state machine. MQ: {'connected' if mq_connected else 'disconnected'}",
                "workflow_enabled": True  # Enable this agent for workflow tracking
            }
            
            if self.DEBUG:
                print(f"[HEARTBEAT] Sending heartbeat for {self.agent_name} to {self.monitor_url}/api/systemagents/heartbeat/")
                print(f"[HEARTBEAT] Payload: {payload}")
            
            url = f"{self.monitor_url}/api/systemagents/heartbeat/"
            response = self.api_session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            if self.DEBUG:
                print(f"[HEARTBEAT] SUCCESS: Status {response.status_code}")
                self.logger.info(f"Heartbeat sent successfully. Status: {status}")
            
        except Exception as e:
            print(f"[HEARTBEAT] FAILED: {e}")
            self.logger.warning(f"Failed to send heartbeat: {e}")
            import traceback
            print(f"[HEARTBEAT] Traceback: {traceback.format_exc()}")
        
    def run_daq_cycle(self):
        """Complete DAQ cycle following state transitions"""
        self.logger.info("Starting DAQ cycle", extra={"simulation_tick": self.env.now})
        
        # Send heartbeat at start of cycle
        self.send_heartbeat()
        
        # State 1: no_beam / not_ready (5 seconds - fast test)
        self.logger.info("DAQ State -> no_beam/not_ready (Collider not operating)", 
                        extra={"simulation_tick": self.env.now, "state": "no_beam", "substate": "not_ready"})
        yield self.env.timeout(5)  # 5 seconds
        
        # State 2: beam / not_ready (5 seconds - fast test) + broadcast run imminent
        self.logger.info("DAQ State -> beam/not_ready (Run start imminent)", 
                        extra={"simulation_tick": self.env.now, "state": "beam", "substate": "not_ready"})
        self.current_run_id = self.get_next_run_number()
        
        # Broadcast run imminent message
        yield self.env.process(self.broadcast_run_imminent())
        yield self.env.timeout(5)  # 5 seconds
        
        # State 3: beam / ready (2 seconds - fast test)
        self.logger.info("DAQ State -> beam/ready (Ready for physics)", 
                        extra={"simulation_tick": self.env.now, "state": "beam", "substate": "ready"})
        yield self.env.timeout(2)  # 2 seconds
        
        # State 4: run / physics (10 seconds = 5 STFs) + run start + STF generation
        self.logger.info("DAQ State -> run/physics (Physics datataking period 1)", 
                        extra={"simulation_tick": self.env.now, "state": "run", "substate": "physics", "physics_period": 1})
        yield self.env.process(self.broadcast_run_start())
        
        # Start STF generation for physics period 1 (10 seconds = 5 STFs)
        stf_process_1 = self.env.process(self.generate_stfs_during_physics(10))
        yield stf_process_1
        
        # State 5: run / standby (2 seconds - fast test)
        self.logger.info("DAQ State -> run/standby (Brief standby)", 
                        extra={"simulation_tick": self.env.now, "state": "run", "substate": "standby"})
        yield self.env.process(self.broadcast_pause_run())
        yield self.env.timeout(2)  # 2 seconds
        
        # State 6: run / physics (10 seconds = 5 STFs) + STF generation
        self.logger.info("DAQ State -> run/physics (Physics datataking period 2)", 
                        extra={"simulation_tick": self.env.now, "state": "run", "substate": "physics"})
        yield self.env.process(self.broadcast_resume_run())
        
        # Start STF generation for physics period 2 (10 seconds = 5 STFs)
        stf_process_2 = self.env.process(self.generate_stfs_during_physics(10))
        yield stf_process_2
        
        # State 7: beam / not_ready (5 seconds - fast test) + run end
        self.logger.info("DAQ State -> beam/not_ready (Run ended by shifters)", 
                        extra={"simulation_tick": self.env.now, "state": "beam", "substate": "not_ready"})
        yield self.env.process(self.broadcast_run_end())
        yield self.env.timeout(5)  # 5 seconds
        
        # State 8: no_beam / not_ready (final)
        self.logger.info("DAQ State -> no_beam/not_ready (Collider shutdown)", 
                        extra={"simulation_tick": self.env.now, "state": "no_beam", "substate": "not_ready"})
        
        self.logger.info("DAQ cycle complete", extra={"simulation_tick": self.env.now, "total_files": self.file_counter})
    
    def broadcast_run_imminent(self):
        """Broadcast run imminent message - triggers dataset creation"""
        message = {
            "msg_type": "run_imminent",
            "run_id": self.current_run_id,
            "timestamp": datetime.now().isoformat(),
            "simulation_tick": self.env.now,
            "run_conditions": {
                "beam_energy": "5 GeV",
                "magnetic_field": "1.5T",
                "detector_config": "physics",
                "bunch_structure": "216x216"
            }
        }
        
        event_file = Path("daq_events") / f"run_{self.current_run_id}_imminent.json"
        with open(event_file, "w") as f:
            json.dump(message, f, indent=2)
        
        # Send to ActiveMQ
        self.send_message(self.destination, message)
            
        self.logger.info("Broadcasted run_imminent message", 
                         extra={"simulation_tick": self.env.now, "run_id": self.current_run_id, "msg_type": "run_imminent"})
        yield self.env.timeout(1)  # Brief broadcast time
    
    def broadcast_run_start(self):
        """Broadcast run start message - triggers PanDA task creation"""
        message = {
            "msg_type": "start_run",
            "run_id": self.current_run_id,
            "timestamp": datetime.now().isoformat(),
            "simulation_tick": self.env.now,
            "state": "run",
            "substate": "physics"
        }
        
        event_file = Path("daq_events") / f"run_{self.current_run_id}_start.json"
        with open(event_file, "w") as f:
            json.dump(message, f, indent=2)
        
        # Send to ActiveMQ
        self.send_message(self.destination, message)
            
        self.logger.info("Broadcasted run_start message", 
                         extra={"simulation_tick": self.env.now, "run_id": self.current_run_id, "msg_type": "start_run"})
        yield self.env.timeout(1)
    
    def broadcast_pause_run(self):
        """Broadcast run pause message - entering standby"""
        message = {
            "msg_type": "pause_run",
            "run_id": self.current_run_id,
            "timestamp": datetime.now().isoformat(),
            "simulation_tick": self.env.now,
            "state": "run",
            "substate": "standby",
            "reason": "Brief standby period"
        }
        
        event_file = Path("daq_events") / f"run_{self.current_run_id}_pause.json"
        with open(event_file, "w") as f:
            json.dump(message, f, indent=2)
        
        # Send to ActiveMQ
        self.send_message(self.destination, message)
            
        self.logger.info("Broadcasted pause_run message", 
                         extra={"simulation_tick": self.env.now, "run_id": self.current_run_id, "msg_type": "pause_run"})
        yield self.env.timeout(1)
    
    def broadcast_resume_run(self):
        """Broadcast run resume message - returning to physics"""
        message = {
            "msg_type": "resume_run",
            "run_id": self.current_run_id,
            "timestamp": datetime.now().isoformat(),
            "simulation_tick": self.env.now,
            "state": "run",
            "substate": "physics",
        }
        
        event_file = Path("daq_events") / f"run_{self.current_run_id}_resume.json"
        with open(event_file, "w") as f:
            json.dump(message, f, indent=2)
        
        # Send to ActiveMQ
        self.send_message(self.destination, message)
            
        self.logger.info("Broadcasted resume_run message", 
                         extra={"simulation_tick": self.env.now, "run_id": self.current_run_id, "msg_type": "resume_run"})
        yield self.env.timeout(1)
    
    def broadcast_run_end(self):
        """Broadcast run end message"""
        message = {
            "msg_type": "end_run",
            "run_id": self.current_run_id,
            "timestamp": datetime.now().isoformat(),
            "simulation_tick": self.env.now,
            "total_files": self.file_counter
        }
        
        event_file = Path("daq_events") / f"run_{self.current_run_id}_end.json"
        with open(event_file, "w") as f:
            json.dump(message, f, indent=2)
        
        # Send to ActiveMQ
        self.send_message(self.destination, message)
            
        self.logger.info("Broadcasted run_end message", 
                         extra={"simulation_tick": self.env.now, "run_id": self.current_run_id, "msg_type": "end_run", "total_files": self.file_counter})
        yield self.env.timeout(1)
    
    def generate_stfs_during_physics(self, duration_seconds):
        """Generate STFs programmatically during physics period"""
        self.logger.info("Starting STF generation", 
                        extra={"simulation_tick": self.env.now, "duration_minutes": duration_seconds/60})
        
        start_time = self.env.now
        heartbeat_counter = 0
        
        while (self.env.now - start_time) < duration_seconds:
            # Generate STF
            yield self.env.process(self.generate_single_stf())
            
            # Send heartbeat every 10 STFs
            heartbeat_counter += 1
            if heartbeat_counter % 10 == 0:
                self.send_heartbeat()
            
            # Wait for next STF interval
            yield self.env.timeout(self.stf_interval)
        
        self.logger.info("STF generation complete", 
                        extra={"simulation_tick": self.env.now})
    
    def generate_single_stf(self):
        """Generate single STF file and broadcast stf_gen message"""
        self.file_counter += 1
        filename = f"{self.current_run_id}_{self.file_counter:06d}.dat"
        
        # Create STF data file
        run_dir = Path("daq_data") / f"run_{self.current_run_id}"
        run_dir.mkdir(exist_ok=True)
        
        stf_file = run_dir / filename
        with open(stf_file, "w") as f:
            f.write(f"STF data: run {self.current_run_id}, file {self.file_counter}\n")
            f.write(f"Generated at simulation time: {self.env.now:.1f}\n")
            f.write(f"Real time: {datetime.now().isoformat()}\n")
            f.write("Mock ePIC detector data payload...\n")
        
        # Calculate start/end times (STF covers ~0.5 second period)
        start_time = datetime.now()
        end_time = datetime.fromtimestamp(start_time.timestamp() + 0.5)
        
        # Broadcast STF generation
        message = {
            "msg_type": "stf_gen",
            "filename": filename,
            "run_id": self.current_run_id,
            "file_url": f"file://{stf_file.absolute()}",
            "size_bytes": stf_file.stat().st_size,
            "checksum": f"sha256:mock_checksum_{self.file_counter:06d}",
            "start": start_time.strftime('%Y%m%d%H%M%S'),
            "end": end_time.strftime('%Y%m%d%H%M%S'),
            "simulation_tick": self.env.now,
            "state": "run",
            "substate": "physics",
            "comment": f"STF file {self.file_counter} generated during physics datataking"
        }
        
        event_file = Path("daq_events") / f"stf_{self.current_run_id}_{self.file_counter:06d}_gen.json"
        with open(event_file, "w") as f:
            json.dump(message, f, indent=2)
        
        # Send to ActiveMQ
        self.send_message(self.destination, message)
        
        self.logger.info("Generated STF and broadcasted stf_gen message", 
                         extra={"simulation_tick": self.env.now, "run_id": self.current_run_id, "stf_filename": filename, "msg_type": "stf_gen"})
        yield self.env.timeout(0.1)  # Brief generation time


def run_simulation(duration_hours=1.0, num_cycles=1, debug=False):
    """Run DAQ simulation for specified duration and cycles"""
    # Set up main simulation logger
    main_logger = setup_rest_logging('daqsim-agent', 'simulation-main')
    
    main_logger.info("ePIC DAQ Simulation Starting", 
                    extra={"duration_hours": duration_hours, "num_cycles": num_cycles})
    
    # Create SimPy environment
    env = simpy.Environment()
    
    # Create DAQ simulator
    daq_sim = DAQSimulator(env, debug=debug)
    
    # Start DAQ cycles
    for cycle in range(num_cycles):
        main_logger.info("Starting DAQ cycle", extra={"cycle": cycle + 1, "total_cycles": num_cycles})
        env.process(daq_sim.run_daq_cycle())
        
        # Brief pause between cycles
        if cycle < num_cycles - 1:
            env.process(lambda: env.timeout(60))  # 1 minute between cycles
    
    # Run simulation
    simulation_duration = duration_hours * 3600  # Convert to seconds
    env.run(until=simulation_duration)
    
    main_logger.info("ePIC DAQ Simulation Complete", 
                    extra={"simulation_tick_seconds": env.now, "simulation_tick_hours": env.now/3600, 
                          "total_files": daq_sim.file_counter})
    
    # Disconnect from ActiveMQ
    try:
        if daq_sim.conn and daq_sim.conn.is_connected():
            daq_sim.conn.disconnect()
            main_logger.info("Disconnected from ActiveMQ")
    except Exception as e:
        main_logger.error(f"Error disconnecting from ActiveMQ: {e}")
    
    # Report generated events
    events = list(Path("daq_events").glob("*.json"))
    main_logger.info("Simulation results", extra={"total_events": len(events)})
    
    # Group events by type
    event_types = {}
    for event_file in events:
        try:
            with open(event_file) as f:
                data = json.load(f)
                msg_type = data.get("msg_type", "unknown")
                event_types[msg_type] = event_types.get(msg_type, 0) + 1
        except (json.JSONDecodeError, OSError, KeyError) as e:
            main_logger.error(f"Failed to process event file {event_file}: {e}")
            # Don't crash here since this is just summary reporting
    
    for msg_type, count in event_types.items():
        main_logger.info("Event type summary", extra={"msg_type": msg_type, "count": count})


if __name__ == "__main__":
    # Setup environment first
    if not setup_environment():
        sys.exit(1)
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Run ePIC DAQ simulation")
    parser.add_argument("--duration", type=float, default=1.0,
                       help="Simulation duration in hours (default: 1.0)")
    parser.add_argument("--cycles", type=int, default=1,
                       help="Number of DAQ cycles to run (default: 1)")
    parser.add_argument("--clean", action="store_true",
                       help="Clean up previous simulation files")
    parser.add_argument("--debug", action="store_true",
                       help="Enable debug logging")
    
    args = parser.parse_args()
    
    if args.clean:
        print("Cleaning up previous simulation files...")
        import shutil
        for dir_name in ["daq_events", "daq_data"]:
            dir_path = Path(dir_name)
            if dir_path.exists():
                shutil.rmtree(dir_path)
                print(f"  Removed {dir_name}/")
    
    # Print to console for user feedback
    print(f"Starting ePIC DAQ simulation: {args.duration} hours, {args.cycles} cycles")
    
    run_simulation(args.duration, args.cycles, debug=args.debug)
    
    print("ePIC DAQ simulation complete")