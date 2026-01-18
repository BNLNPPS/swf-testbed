"""
Fast Processing Agent: Handles STF sampling and TF slice creation for fast monitoring.

This agent:
1. Receives workflow messages from the broadcast topic (epictopic)
2. On stf_gen: samples STFs, creates TF slices, pushes to worker queue
3. Maintains RunState and TFSlice records in the monitor database
4. Workers (PanDA transformers) consume slices from /queue/panda.transformer.slices

Message format specification: https://github.com/wguanicedew/iDDS/blob/dev/main/prompt.md
"""

import logging
import stomp
import time
from datetime import datetime
from swf_common_lib.base_agent import BaseAgent


class FastProcessingResultAgent(BaseAgent):
    """
    Listens for transformer results on TRANSFORMER_RESULTS_QUEUE and logs/results handling.
    """

    TRANSFORMER_RESULTS_QUEUE = '/queue/panda.results.fastprocessing'

    def __init__(self, debug=False, config_path=None):
        super().__init__(
            agent_type='Fast_Processing_Result',
            subscription_queue=self.TRANSFORMER_RESULTS_QUEUE,
            debug=debug,
            config_path=config_path
        )

        self.stats = {
            'results_received': 0,
            'results_done': 0,
            'results_failed': 0
        }

    def on_message(self, frame):
        message_data, msg_type = self.log_received_message(frame)
        if message_data is None:
            return

        try:
            if msg_type == 'slice_result':
                self.handle_slice_result(message_data)
            else:
                self.logger.debug(f"Result agent ignoring message type: {msg_type}")
        except Exception as e:
            self.logger.error(f"Error processing result message: {e}",
                              extra=self._log_extra(error=str(e)))

    def handle_slice_result(self, message_data):
        """Process slice_result messages from transformer workers."""
        self.stats['results_received'] += 1

        content = message_data.get('content', {})
        result = content.get('result') if isinstance(content, dict) else None

        self.logger.debug(f"Processing slice_result: {message_data}")
        
        # Log an event to system-state-events for observability
        try:
            event = {
                'timestamp': datetime.now().isoformat(),
                'run_number': message_data.get('run_id'),
                'event_type': 'slice_result',
                'state': None,
                'substate': None,
                'event_data': {
                    'message': message_data,
                }
            }
            self.call_monitor_api('POST', '/system-state-events/', event)
        except Exception:
            # Non-fatal if monitor API unavailable
            self.logger.debug('Failed to log slice_result to monitor API', extra=self._log_extra())

        # Track done/failed counts if result payload present
        try:
            inner_result = None
            if result and isinstance(result, dict):
                inner_result = result.get('result') if isinstance(result.get('result'), dict) else None

            state = content.get('state') or (inner_result.get('state') if inner_result else None)
            if state == 'done' or (inner_result and inner_result.get('processed')):
                self.stats['results_done'] += 1
            else:
                self.stats['results_failed'] += 1
        except Exception:
            pass

        self.logger.info(f"Handled slice_result: run={message_data.get('run_id')}, msg={message_data.get('msg_type')}",
                         extra=self._log_extra(run_id=message_data.get('run_id')))

    def run(self):
        """
        Connects to the message broker and runs the agent's main loop.
        """
        logging.info(f"Starting {self.agent_name}...")

        # Connect if not already connected (some subclasses connect in __init__)
        if not getattr(self, 'mq_connected', False):
            max_retries = 3
            retry_delay = 5
            for attempt in range(1, max_retries + 1):
                logging.info(f"Connecting to ActiveMQ at {self.mq_host}:{self.mq_port} (attempt {attempt}/{max_retries})")
                try:
                    self.conn.connect(
                        self.mq_user,
                        self.mq_password,
                        wait=True,
                        version='1.1',
                        headers={
                            'client-id': self.agent_name,
                            'heart-beat': '30000,30000'
                        }
                    )
                    self.mq_connected = True
                    break
                except Exception as e:
                    logging.warning(f"Connection attempt {attempt} failed: {e}")
                    if attempt < max_retries:
                        logging.info(f"Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                    else:
                        logging.error(f"Failed to connect after {max_retries} attempts")
                        raise

        try:
            self.conn.subscribe(destination=self.subscription_queue, id=1, ack='auto')
            logging.info(f"Subscribed to queue: '{self.subscription_queue}'")

            # Register as subscriber in monitor
            self.register_subscriber()

            # Agent is now ready and waiting for work
            self.set_ready()

            # Initial registration/heartbeat
            # self.send_heartbeat()

            logging.info(f"{self.agent_name} is running. Press Ctrl+C to stop.")
            while True:
                time.sleep(60) # Keep the main thread alive, heartbeats can be added here
                
                # Check connection status and attempt reconnection if needed
                if not self.mq_connected:
                    self._attempt_reconnect()
                    
                #self.send_heartbeat()

        except KeyboardInterrupt:
            logging.info(f"Stopping {self.agent_name}...")
        except stomp.exception.ConnectFailedException as e:
            self.mq_connected = False
            logging.error(f"Failed to connect to ActiveMQ: {e}")
            logging.error("Please check the connection details and ensure ActiveMQ is running.")
        except Exception as e:
            self.mq_connected = False
            logging.error(f"An unexpected error occurred: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Report exit status before disconnecting
            try:
                self.operational_state = 'EXITED'
                self.report_agent_status("EXITED", "Agent shutdown")
            except Exception as e:
                logging.warning(f"Failed to report exit status: {e}")

            if self.conn and self.conn.is_connected():
                self.conn.disconnect()
                self.mq_connected = False
                logging.info("Disconnected from ActiveMQ.")


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    script_dir = Path(__file__).parent

    parser = argparse.ArgumentParser(
        description="Fast Processing Agent - samples STFs and creates TF slices"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--testbed-config", default=str(script_dir / "testbed.toml"),
                        help="Testbed config file (default: testbed.toml)")
    args = parser.parse_args()

    agent = FastProcessingResultAgent(debug=args.debug, config_path=args.testbed_config)
    agent.run()