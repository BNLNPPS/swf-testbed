#!/usr/bin/env python3
"""
Fast Monitoring Agent for SWF Fast Monitoring System.

This agent receives stf_ready messages from the data agent, samples Time Frames (TF) from
Super Time Frames (STF), and records TF metadata in the fast monitoring database.
The TFs are then broadcast via ActiveMQ to fast monitoring clients.

Designed to run continuously under supervisord.
"""

import sys
import json
from datetime import datetime

from swf_common_lib.base_agent import BaseAgent, setup_environment
import example_fastmon_utils as fastmon_utils


class FastMonitorAgent(BaseAgent):
    """
    Agent that receives stf_ready messages, samples TFs from STFs and records them in the database.
    Then broadcasts the TF notifications via ActiveMQ.
    """

    def __init__(self, config: dict, debug=False, config_path=None):
        """
        Initialize the fast monitoring agent.

        Args:
            config: configuration dictionary containing:
                - selection_fraction: Fraction of TFs to select (0.0-1.0)
                - tf_files_per_stf: Number of TF files to generate per STF
                - tf_size_fraction: Fraction of STF size for each TF
                - tf_sequence_start: Starting sequence number for TF files
            debug: Enable debug logging for heartbeat messages
            config_path: Path to testbed.toml config file
        """

        # Initialize base agent with fast monitoring specific parameters
        super().__init__(agent_type='fastmon', subscription_queue='/topic/epictopic', debug=debug,
                         config_path=config_path)
        self.running = True
        self.destination = '/topic/epictopic'

        self.logger.info("Fast Monitor Agent initialized successfully")

        self.config = config
        
        # Validate configuration
        fastmon_utils.validate_config(self.config)
        self.logger.info(f"Fast Monitor Agent initialized with config: {self.config}")
        
        # Fast monitoring specific state
        self.stf_messages_processed = 0
        self.last_message_time = None
        self.processing_stats = {'total_stf_messages': 0, 'total_tf_files_created': 0}

    def send_tf_file_notification(self, tf_file: dict, stf_file: dict):
        """
        Send notification to clients about a newly registered TF file via ActiveMQ.
        
        Args:
            tf_file: TF file data from the FastMonFile API
            stf_file: Parent STF file data
        """
        try:
            # Create message using utility function
            message = fastmon_utils.create_tf_message(tf_file, stf_file, self.agent_name)

            # Send message via ActiveMQ (monitor will forward to SSE clients)
            self.send_message(self.destination, message)
            
            self.logger.debug(f"Sent TF file notification via ActiveMQ: {tf_file.get('tf_filename')}")
            
        except Exception as e:
            self.logger.error(f"Failed to send TF file notification: {e}")



    def on_message(self, frame):
        """
        Handle incoming stf_ready messages for fast monitoring.
        This agent processes STF metadata and creates TF samples.
        """
        # Use base class helper for consistent logging
        message_data, msg_type = self.log_received_message(frame, {'stf_ready'})
        if message_data is None:
            return

        # Extract workflow context from message
        if 'execution_id' in message_data:
            self.current_execution_id = message_data['execution_id']
        if 'run_id' in message_data:
            self.current_run_id = message_data['run_id']

        # Update heartbeat on message activity
        self.send_heartbeat()

        try:
            # A "stf_ready" call from the data agent
            if msg_type == 'stf_ready':
                tf_files = self.sample_timeframes(message_data)
            else:
                self.logger.warning(f"Ignoring unknown message type {msg_type}",
                                   extra=self._log_extra(msg_type=msg_type))

        except Exception as e:
            self.logger.error("Error processing message",
                            extra=self._log_extra(error=str(e)))
            self.report_agent_status('ERROR', f'Message processing error: {str(e)}')


    def sample_timeframes(self, message_data):
        """
        Handle stf_ready message and sample STFs into TFs
        Registers the TFs in the swf-monitor database and notifies clients.
        """
        self.logger.info("Processing stf_ready message", extra=self._log_extra())

        # Update message tracking stats
        self.last_message_time = datetime.now()
        self.stf_messages_processed += 1
        self.processing_stats['total_stf_messages'] += 1

        tf_files_registered = []
        self.logger.debug(f"Message data received: {message_data}", extra=self._log_extra())
        if not message_data.get('filename'):
            self.logger.error("No filename provided in message", extra=self._log_extra())
            return tf_files_registered

        tf_subsamples = fastmon_utils.simulate_tf_subsamples(message_data, self.config, self.logger, self.agent_name)

        # Record each TF file in the FastMonFile table
        # TODO: register in bulk
        tf_files_created = 0
        for tf_metadata in tf_subsamples:
            self.logger.debug(f"Processing {tf_metadata}")
            tf_file = fastmon_utils.record_tf_file(tf_metadata, self.config, self, self.logger)
            if tf_file:
                tf_files_created += 1
                # Broadcast tf_file_registered to downstream consumers
                self.send_tf_file_notification(tf_file, message_data)
            tf_files_registered.append(tf_file)

        # Update TF creation stats
        self.processing_stats['total_tf_files_created'] += tf_files_created

        self.logger.info(f"Registered {tf_files_created} TF subsamples for STF file {message_data.get('filename')}",
                        extra=self._log_extra(stf_filename=message_data.get('filename'), tf_files_created=tf_files_created))
        return tf_files_registered



    



def main():
    """Main entry point for the agent."""
    import argparse
    from pathlib import Path

    script_dir = Path(__file__).parent

    parser = argparse.ArgumentParser(description='Fast Monitor Agent')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging for heartbeat messages')
    parser.add_argument('--testbed-config', default=None,
                        help='Testbed config file (default: SWF_TESTBED_CONFIG env var or workflows/testbed.toml)')
    args = parser.parse_args()

    # Configuration for message-driven agent
    config = {
        "selection_fraction": 0.1,  # 10% of files
        # TF simulation parameters
        "tf_files_per_stf": 7,  # Number of TF files to generate per STF
        "tf_size_fraction": 0.15,  # Fraction of STF size for each TF
        "tf_sequence_start": 1,  # Starting sequence number for TF files
    }

    # Create agent with config and debug flag
    agent = FastMonitorAgent(config, debug=args.debug, config_path=args.testbed_config)

    # Run in message-driven mode (reacts to stf_ready messages)
    agent.run()


if __name__ == "__main__":
    # Setup environment first
    if not setup_environment():
        sys.exit(1)

    main()
