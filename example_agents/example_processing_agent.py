"""
Example Processing Agent: Handles data ready messages.
"""

from swf_common_lib.base_agent import BaseAgent
import json
import time
from datetime import datetime

class ProcessingAgent(BaseAgent):
    """
    An example agent that simulates the role of the Processing Agent.
    It listens for 'stf_ready' messages.
    """

    def __init__(self, debug=False, config_path=None):
        super().__init__(agent_type='STF_Processing', subscription_queue='/queue/processing_agent', debug=debug,
                         config_path=config_path)
        self.active_processing = {}  # Track files being processed
        self.processing_stats = {'total_processed': 0, 'failed_count': 0}

    def on_message(self, frame):
        """
        Handles incoming workflow messages (stf_ready, run_imminent, start_run, end_run).
        """
        # Use base class helper for consistent logging
        message_data, msg_type = self.log_received_message(frame)
        if message_data is None:
            return

        # Extract workflow context from message
        if 'execution_id' in message_data:
            self.current_execution_id = message_data['execution_id']
        if 'run_id' in message_data:
            self.current_run_id = message_data['run_id']

        # Update heartbeat on message activity
        self.send_processing_agent_heartbeat()
        try:
            if msg_type == 'stf_ready':
                self.handle_stf_ready(message_data)
            elif msg_type == 'run_imminent':
                self.handle_run_imminent(message_data)
            elif msg_type == 'start_run':
                self.handle_start_run(message_data)
            elif msg_type == 'end_run':
                self.handle_end_run(message_data)
        except Exception as e:
            self.logger.error(
                f"CRITICAL: Message processing failed - {str(e)}",
                extra=self._log_extra(error=str(e))
            )
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            raise RuntimeError(f"Critical message processing failure: {e}") from e
    
    # Processing agent specific monitor integration methods
    def update_file_processing_status(self, filename, status, monitor_file_id=None):
        """Update STF file processing status in monitor."""
        if not monitor_file_id:
            self.logger.warning(f"No monitor file ID provided for {filename}", extra=self._log_extra())
            return False

        self.logger.info(f"Updating file {filename} processing status to {status}...", extra=self._log_extra())

        update_data = {
            'status': status,
            'metadata': {
                'processed_by': self.agent_name,
                'processing_stage': 'reconstruction',
                'updated_at': datetime.now().isoformat()
            }
        }

        result = self.call_monitor_api('PATCH', f'/stf-files/{monitor_file_id}/', update_data)
        if result:
            self.logger.info(f"File {filename} processing status updated to {status}", extra=self._log_extra())
            return True
        else:
            self.logger.warning(f"Failed to update file {filename} processing status", extra=self._log_extra())
            return False

    def register_processing_task(self, filename, input_data):
        """Register a processing task in the monitor."""
        self.logger.info(f"Registering processing task for {filename}...", extra=self._log_extra())

        task_data = {
            'agent_name': self.agent_name,
            'agent_type': 'processing',
            'task_type': 'reconstruction',
            'input_filename': filename,
            'run_id': input_data.get('run_id'),
            'status': 'started',
            'started_at': datetime.now().isoformat(),
            'task_metadata': {
                'input_size_bytes': input_data.get('size_bytes'),
                'input_checksum': input_data.get('checksum'),
                'processing_algorithm': 'eic_reconstruction_v1.0'
            }
        }

        result = self.call_monitor_api('POST', '/workflow-stages/', task_data)
        if result:
            task_id = result.get('stage_id')
            self.active_processing[filename] = {
                'task_id': task_id,
                'started_at': datetime.now(),
                'input_data': input_data
            }
            self.logger.info(f"Processing task registered for {filename} with ID {task_id}", extra=self._log_extra())
            return task_id
        else:
            self.logger.warning(f"Failed to register processing task for {filename}", extra=self._log_extra())
            return None

    def complete_processing_task(self, filename, output_files):
        """Mark processing task as completed in monitor."""
        if filename not in self.active_processing:
            self.logger.warning(f"No active processing task found for {filename}", extra=self._log_extra())
            return False

        task_info = self.active_processing[filename]
        task_id = task_info['task_id']

        processing_time = (datetime.now() - task_info['started_at']).total_seconds()

        self.logger.info(f"Completing processing task for {filename}...", extra=self._log_extra())

        completion_data = {
            'status': 'completed',
            'completed_at': datetime.now().isoformat(),
            'processing_time_seconds': processing_time,
            'output_metadata': {
                'output_files': output_files,
                'success': True,
                'algorithm_version': 'eic_reconstruction_v1.0'
            }
        }

        result = self.call_monitor_api('PATCH', f'/workflow-stages/{task_id}/', completion_data)
        if result:
            self.processing_stats['total_processed'] += 1
            del self.active_processing[filename]
            self.logger.info(f"Processing task completed for {filename}", extra=self._log_extra())
            return True
        else:
            self.logger.warning(f"Failed to complete processing task for {filename}", extra=self._log_extra())
            return False
    
    def send_processing_agent_heartbeat(self):
        """Send enhanced heartbeat with processing agent context."""
        workflow_metadata = {
            'active_tasks': len(self.active_processing),
            'completed_tasks': self.processing_stats['total_processed'],
            'failed_tasks': self.processing_stats['failed_count']
        }
        
        return self.send_enhanced_heartbeat(workflow_metadata)

    def handle_run_imminent(self, message_data):
        """Handle run_imminent message - prepare for processing tasks"""
        run_id = message_data.get('run_id')
        self.logger.info(
            "Processing run_imminent message",
            extra=self._log_extra(simulation_tick=message_data.get('simulation_tick'))
        )

        # Report agent status for run preparation
        self.report_agent_status('OK', f'Preparing for run {run_id}')

        # TODO: Initialize processing resources for this run

        # Simulate preparation
        self.logger.info("Prepared processing resources for run", extra=self._log_extra())

    def handle_start_run(self, message_data):
        """Handle start_run message - run is starting physics"""
        self.logger.info(
            "Processing start_run message",
            extra=self._log_extra(simulation_tick=message_data.get('simulation_tick'))
        )

        # Agent is now actively processing this run
        self.set_processing()

        # Send enhanced heartbeat with run context
        self.send_processing_agent_heartbeat()

        # TODO: Start monitoring for stf_ready messages
        self.logger.info("Ready to process data for run", extra=self._log_extra())

    def handle_end_run(self, message_data):
        """Handle end_run message - run has ended"""
        run_id = message_data.get('run_id')
        total_files = message_data.get('total_files', 0)
        self.logger.info(
            "Processing end_run message",
            extra=self._log_extra(total_files=total_files, simulation_tick=message_data.get('simulation_tick'))
        )

        # Report final statistics via heartbeat
        self.send_processing_agent_heartbeat()

        # Report completion status
        active_tasks = len(self.active_processing)
        if active_tasks > 0:
            self.report_agent_status('WARNING', f'Run {run_id} ended with {active_tasks} tasks still processing')
        else:
            self.report_agent_status('OK', f'Run {run_id} processing completed successfully')

        # TODO: Finalize processing tasks for this run

        self.logger.info("Processing complete for run", extra=self._log_extra(total_files=total_files))

        # Agent is now idle, waiting for next run
        self.set_ready()
        self.current_execution_id = None  # Clear context for next run
        self.current_run_id = None
        self.logger.info("Waiting for next run...")

    def handle_stf_ready(self, message_data):
        """Handle stf_ready message - process STF file"""
        filename = message_data.get('filename')
        file_url = message_data.get('file_url')
        checksum = message_data.get('checksum')
        size_bytes = message_data.get('size_bytes')
        processed_by = message_data.get('processed_by')

        self.logger.info(
            "Processing STF data",
            extra=self._log_extra(
                stf_filename=filename, size_bytes=size_bytes,
                processed_by=processed_by, simulation_tick=message_data.get('simulation_tick')
            )
        )
        
        # Simulate processing time 
        import time
        time.sleep(0.5)  # Simulate compute-intensive processing
        
        # Define output files
        output_files = [
            f"{filename.replace('.dat', '.dst')}",
            f"{filename.replace('.dat', '.hist.root')}"
        ]
        
        # Update processing stats
        self.processing_stats['total_processed'] += 1
        
        # Send processing_complete message
        # namespace is also auto-injected by BaseAgent.send_message()
        processing_complete_message = {
            "msg_type": "processing_complete",
            "namespace": self.namespace,
            "filename": filename,
            "run_id": self.current_run_id,
            "input_file_url": file_url,
            "input_checksum": checksum,
            "input_size_bytes": size_bytes,
            "output_files": output_files,
            "processing_time_ms": 500,
            "simulation_tick": message_data.get('simulation_tick'),
            "processed_by": self.agent_name
        }

        # Register processing results with monitor (legacy method - keep for compatibility)
        self.register_processing_results(processing_complete_message)

        # Send to monitoring/analysis agents
        self.send_message('/queue/monitoring_agent', processing_complete_message)
        self.logger.info(
            "Sent processing_complete message",
            extra=self._log_extra(stf_filename=filename, destination="monitoring_agent")
        )


    
    def register_processing_results(self, processing_data):
        """Register processing results with monitor API (legacy method for compatibility)"""
        filename = processing_data.get('filename')

        try:
            # This is now handled by the new processing agent specific methods above
            # Keeping this method for backward compatibility and logging
            self.logger.info(
                "Processing results registered via new processing agent specific methods",
                extra=self._log_extra(
                    stf_filename=filename,
                    output_files=len(processing_data.get('output_files', []))
                )
            )

        except Exception as e:
            self.logger.error(
                "Error in legacy processing results registration",
                extra=self._log_extra(stf_filename=filename, error=str(e))
            )


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    script_dir = Path(__file__).parent

    parser = argparse.ArgumentParser(description="Processing Agent - handles workflow data processing")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--testbed-config", default=None,
                        help="Testbed config file (default: SWF_TESTBED_CONFIG env var or workflows/testbed.toml)")
    args = parser.parse_args()

    agent = ProcessingAgent(debug=args.debug, config_path=args.testbed_config)
    agent.run()
