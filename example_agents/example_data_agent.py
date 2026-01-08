"""
Example Data Agent: Handles STF generation messages.
"""

from swf_common_lib.base_agent import BaseAgent
import json
import requests
from datetime import datetime

class DataAgent(BaseAgent):
    """
    An example agent that simulates the role of the Data Agent.
    It listens for 'stf_gen' messages and sends 'data_ready' messages.
    """

    def __init__(self, debug=False, config_path=None):
        super().__init__(agent_type='DATA', subscription_queue='epictopic', debug=debug,
                         config_path=config_path)
        self.active_runs = {}  # Track active runs and their monitor IDs
        self.active_files = {}  # Track STF files being processed

    def on_message(self, frame):
        """
        Handles incoming DAQ messages (stf_gen, run_imminent, start_run, end_run).
        """
        # Use base class helper for consistent logging
        message_data, msg_type = self.log_received_message(frame)
        if message_data is None:
            return

        try:
            if msg_type == 'stf_gen':
                self.handle_stf_gen(message_data)
            elif msg_type == 'run_imminent':
                self.handle_run_imminent(message_data)
            elif msg_type == 'start_run':
                self.handle_start_run(message_data)
            elif msg_type == 'end_run':
                self.handle_end_run(message_data)
        except Exception as e:
            self.logger.error(f"CRITICAL: Message processing failed - {str(e)}", extra={"error": str(e)})
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            raise RuntimeError(f"Critical message processing failure: {e}") from e
    
    # Data agent specific monitor integration methods
    def create_run_record(self, run_id, run_conditions):
        """Create a run record in the monitor."""
        self.logger.info(f"Creating run record {run_id} in monitor...")
        
        run_data = {
            'run_number': int(run_id),  # Convert string run_id to integer
            'start_time': datetime.now().isoformat(),
            'run_conditions': run_conditions
        }
        
        try:
            result = self.call_monitor_api('POST', '/runs/', run_data)
            if result:
                monitor_run_id = result.get('run_id')
                self.active_runs[run_id] = {
                    'monitor_run_id': monitor_run_id,
                    'files_created': 0,
                    'total_files': 0
                }
                self.logger.info(f"Run {run_id} registered in monitor with ID {monitor_run_id}")
                return monitor_run_id
            else:
                self.logger.error(f"Failed to register run {run_id} in monitor - API returned no data")
                return None
        except RuntimeError as e:
            if "400 Client Error" in str(e):
                # Report the actual error details so we can see what it is
                error_msg = str(e)
                self.logger.error(f"Run {run_id} registration failed with 400 error: {error_msg}")
                # Crash so we can examine the actual error and implement proper handling
                raise
            else:
                # Re-raise other API errors
                raise
    
    def update_run_status(self, run_id, status='completed'):
        """Update run status in the monitor."""
        if run_id not in self.active_runs:
            self.logger.warning(f"Run {run_id} not found in active runs")
            return False
            
        monitor_run_id = self.active_runs[run_id]['monitor_run_id']
        self.logger.info(f"Updating run {run_id} status to {status} in monitor...")
        
        update_data = {
            'end_time': datetime.now().isoformat()
        }
        
        result = self.call_monitor_api('PATCH', f'/runs/{monitor_run_id}/', update_data)
        if result:
            self.logger.info(f"Run {run_id} status updated successfully")
            return True
        else:
            self.logger.warning(f"Failed to update run {run_id} status")
            return False
    
    def register_stf_file(self, run_id, filename, file_size=None, start=None, end=None, state=None, substate=None, sequence=None):
        """Register an STF file in the monitor."""
        if run_id not in self.active_runs:
            self.logger.warning(f"Cannot register file {filename} - run {run_id} not active")
            return None
            
        monitor_run_id = self.active_runs[run_id]['monitor_run_id']
        
        # Skip registration if run registration failed
        if monitor_run_id is None:
            self.logger.warning(f"Skipping STF file registration for {filename} - run {run_id} was not registered in monitor")
            return None
            
        self.logger.info(f"Registering STF file {filename} in monitor...")
        
        file_data = {
            'run': monitor_run_id,
            'stf_filename': filename,
            'file_size_bytes': file_size,
            'machine_state': state or 'unknown',
            'status': 'registered',
            'metadata': {
                'created_by': self.agent_name,
                'substate': substate,
                'start': start,
                'end': end,
                'sequence': sequence
            }
        }
        
        try:
            result = self.call_monitor_api('POST', '/stf-files/', file_data)
            if result:
                file_id = result.get('file_id')
                self.active_files[filename] = {
                    'file_id': file_id,
                    'run_id': run_id,
                    'status': 'registered'
                }
                self.active_runs[run_id]['files_created'] += 1
                self.logger.info(f"STF file {filename} registered with ID {file_id}")
                return file_id
            else:
                self.logger.warning(f"Failed to register STF file {filename} - API returned no data")
                return None
        except RuntimeError as e:
            if "400 Client Error" in str(e):
                # Parse the actual error response to understand what went wrong
                error_msg = str(e)
                self.logger.error(f"STF file {filename} registration failed with 400 error: {error_msg}")
                return None
            else:
                # Re-raise other API errors
                raise
    
    def update_stf_file_status(self, filename, status):
        """Update STF file status in the monitor."""
        if filename not in self.active_files:
            self.logger.warning(f"File {filename} not found in active files")
            return False
            
        file_info = self.active_files[filename]
        file_id = file_info['file_id']
        self.logger.info(f"Updating STF file {filename} status to {status}...")
        
        update_data = {
            'status': status,
            'metadata': {'processed_by': self.agent_name, 'updated_at': datetime.now().isoformat()}
        }
        
        result = self.call_monitor_api('PATCH', f'/stf-files/{file_id}/', update_data)
        if result:
            self.active_files[filename]['status'] = status
            self.logger.info(f"STF file {filename} status updated to {status}")
            return True
        else:
            self.logger.warning(f"Failed to update STF file {filename} status")
            return False
    
    def send_data_agent_heartbeat(self):
        """Send enhanced heartbeat with data agent context."""
        workflow_metadata = {
            'active_runs': len(self.active_runs),
            'active_files': len(self.active_files),
            'completed_tasks': sum(run['files_created'] for run in self.active_runs.values())
        }
        
        return self.send_enhanced_heartbeat(workflow_metadata)

    def handle_run_imminent(self, message_data):
        """Handle run_imminent message - create dataset in Rucio"""
        run_id = message_data.get('run_id')
        run_conditions = message_data.get('run_conditions', {})
        self.logger.info("Processing run_imminent message", 
                        extra={"run_id": run_id, "simulation_tick": message_data.get('simulation_tick')})
        
        # Create run record in monitor
        monitor_run_id = self.create_run_record(run_id, run_conditions)
        
        # TODO: Call Rucio to create dataset for this run
        
        # Simulate dataset creation
        if monitor_run_id:
            self.logger.info("Created dataset for run", extra={"run_id": run_id, "monitor_run_id": monitor_run_id})
        else:
            self.logger.warning("Dataset created but monitor registration failed", extra={"run_id": run_id})

    def handle_start_run(self, message_data):
        """Handle start_run message - run is starting physics"""
        run_id = message_data.get('run_id')
        self.logger.info("Processing start_run message", 
                        extra={"run_id": run_id, "simulation_tick": message_data.get('simulation_tick')})
        
        # Send enhanced heartbeat with run context
        self.send_data_agent_heartbeat()
        
        self.logger.info("Run started", extra={"run_id": run_id})

    def handle_end_run(self, message_data):
        """Handle end_run message - run has ended"""
        run_id = message_data.get('run_id')
        total_files = message_data.get('total_files', 0)
        self.logger.info("Processing end_run message", 
                        extra={"run_id": run_id, "total_files": total_files, "simulation_tick": message_data.get('simulation_tick')})
        
        # Update run status in monitor API
        if run_id in self.active_runs:
            self.active_runs[run_id]['total_files'] = total_files
            self.update_run_status(run_id, 'completed')
        
        # TODO: Finalize dataset in Rucio
        
        # Send final heartbeat and clean up
        self.send_data_agent_heartbeat()
        if run_id in self.active_runs:
            del self.active_runs[run_id]
        
        self.logger.info("Run ended", extra={"run_id": run_id, "total_files": total_files})

    def handle_stf_gen(self, message_data):
        """Handle stf_gen message - new STF file available"""
        filename = message_data.get('filename')
        run_id = message_data.get('run_id')
        file_url = message_data.get('file_url')
        checksum = message_data.get('checksum')
        size_bytes = message_data.get('size_bytes')
        # Capture timing, state, and sequence fields
        start = message_data.get('start')
        end = message_data.get('end')
        state = message_data.get('state')
        substate = message_data.get('substate')
        sequence = message_data.get('sequence')

        self.logger.info("Processing STF file",
                        extra={"stf_filename": filename, "run_id": run_id, "size_bytes": size_bytes,
                              "simulation_tick": message_data.get('simulation_tick')})

        # Register STF file and workflow with monitor
        self.register_stf_file(run_id, filename, size_bytes, start, end, state, substate, sequence)
        
        # TODO: Register STF file with Rucio
        # TODO: Initiate transfer to E1 facilities  
        
        # Simulate processing time
        import time
        time.sleep(0.1)
        
        # Send stf_ready message to processing agent
        # namespace is also auto-injected by BaseAgent.send_message()
        stf_ready_message = {
            "msg_type": "stf_ready",
            "namespace": self.namespace,
            "filename": filename,
            "run_id": run_id,
            "file_url": file_url,
            "checksum": checksum,
            "size_bytes": size_bytes,
            "start": start,
            "end": end,
            "state": state,
            "substate": substate,
            "sequence": sequence,
            "simulation_tick": message_data.get('simulation_tick'),
            "processed_by": self.agent_name
        }
        
        self.send_message('processing_agent', stf_ready_message)

        # Update STF file status to processed
        self.update_stf_file_status(filename, 'processed')

        self.logger.info("Sent stf_ready message",
                        extra={"stf_filename": filename, "run_id": run_id, "destination": "processing_agent"})


    
    
    
    def _parse_time_string(self, time_str):
        """Parse time string from DAQ simulator format to ISO format"""
        if not time_str:
            return datetime.now().isoformat()
        try:
            # Convert from format like '20250801143000' to ISO format
            dt = datetime.strptime(time_str, '%Y%m%d%H%M%S')
            return dt.isoformat()
        except ValueError as e:
            self.logger.error(f"Failed to parse time string '{time_str}': {e}")
            raise RuntimeError(f"Critical time parsing failure: {e}") from e


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    script_dir = Path(__file__).parent

    parser = argparse.ArgumentParser(description="Data Agent - handles STF files and run management")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--testbed-config", default=str(script_dir / "testbed.toml"),
                        help="Testbed config file (default: testbed.toml)")
    args = parser.parse_args()

    agent = DataAgent(debug=args.debug, config_path=args.testbed_config)
    agent.run()
