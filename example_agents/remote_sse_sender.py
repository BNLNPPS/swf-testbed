#!/usr/bin/env python3
"""
Remote SSE Sender: Sends test messages through ActiveMQ that will be relayed to SSE clients.

This script demonstrates sending workflow messages that the monitor will broadcast
to connected SSE clients. It inherits from BaseAgent to use standard logging and
ActiveMQ connectivity.
"""

from swf_common_lib.base_agent import BaseAgent
import os
import json
import time
import sys

class RemoteSSESender(BaseAgent):
    """
    Example agent that sends test messages to demonstrate SSE functionality.
    Sends a few test messages and exits.
    """

    def __init__(self):
        # Force production monitor for this example agent
        prod_base = os.getenv('SWF_MONITOR_PROD_URL', 'https://pandaserver02.sdcc.bnl.gov/swf-monitor').rstrip('/')
        # Override any localhost defaults to avoid misdirected heartbeats/logging
        os.environ['SWF_MONITOR_URL'] = prod_base
        os.environ['SWF_MONITOR_HTTP_URL'] = prod_base

        super().__init__(agent_type='sse_sender', subscription_queue='/topic/epictopic')
        self.logger.info(f"Monitor base set to: {prod_base}")
        self.messages_to_send = [
            {
                'msg_type': 'sse_test',
                'processed_by': self.agent_name,
                'run_id': 'test-run-001',
                'message': 'Hello from SSE sender!',
                'data': 'This is a test message for SSE demonstration'
            },
            {
                'msg_type': 'data_ready',
                'processed_by': self.agent_name, 
                'run_id': 'test-run-001',
                'filename': 'test_file_001.dat',
                'message': 'Simulated data ready event'
            },
            {
                'msg_type': 'processing_complete',
                'processed_by': self.agent_name,
                'run_id': 'test-run-001', 
                'filename': 'test_file_001.dat',
                'message': 'Simulated processing complete event'
            }
        ]

    def run_sender(self):
        """Send test messages; loop by default, one-shot if enabled via env."""
        # Loop by default. Set SWF_SENDER_ONESHOT=1 (or true/yes/on) to send a single batch.
        oneshot = os.getenv('SWF_SENDER_ONESHOT', '0').lower() in ('1', 'true', 'yes', 'on')
        batch_interval = int(os.getenv('SWF_SENDER_BATCH_INTERVAL', '30'))
        mode = 'one-shot' if oneshot else f'loop every {batch_interval}s'
        self.logger.info(f"Starting Remote SSE Sender ({mode})")

        try:
            while True:
                # Ensure connection (fixed 2s delay on failure)
                if not self.conn or not self.conn.is_connected():
                    try:
                        self.logger.info("Connecting to ActiveMQ ...")
                        self.conn.connect(
                            self.mq_user,
                            self.mq_password,
                            wait=True,
                            version='1.1',
                            headers={
                                'client-id': self.agent_name,
                                'heart-beat': '10000,30000'
                            }
                        )
                        self.logger.info("Connected to ActiveMQ")
                        self.mq_connected = True
                        
                        # Register agent with monitor via heartbeat
                        self.send_heartbeat()
                    except Exception as e:
                        self.logger.error(f"Failed to connect to ActiveMQ: {e}")
                        self.mq_connected = False
                        time.sleep(2)
                        continue

                # Send one batch
                self.logger.info(f"Sending batch of {len(self.messages_to_send)} messages")
                for i, message in enumerate(self.messages_to_send, 1):
                    try:
                        self.logger.debug(f"Sending message {i}/{len(self.messages_to_send)}: {message['msg_type']}")
                        self.send_message('/topic/epictopic', message)
                        self.logger.debug(
                            f"Sent message: {message['msg_type']} run={message.get('run_id','N/A')}"
                        )
                    except Exception as e:
                        self.logger.error(f"Failed to send message {i}: {e}")
                        # If a message fails to send, the connection might be dead.
                        # Break the inner loop and let the outer loop try to reconnect.
                        break
                    
                    # Sleep between messages (only if not the last message)
                    if i < len(self.messages_to_send):
                        time.sleep(1)

                # Exit in one-shot mode; otherwise sleep and repeat
                if oneshot:
                    self.logger.info("Completed one-shot batch; exiting.")
                    break

                self.logger.info(f"Batch sent. Waiting {batch_interval} seconds.")
                time.sleep(batch_interval)
        finally:
            # Disconnect when the loop is exited (e.g., one-shot mode, Ctrl-C)
            if self.conn and self.conn.is_connected():
                try:
                    self.conn.disconnect()
                    self.logger.info("Disconnected from ActiveMQ")
                except Exception as e:
                    self.logger.error(f"Error during disconnect: {e}")

def main():
    """Main entry point."""
    try:
        sender = RemoteSSESender()
        sender.run_sender()
        
    except KeyboardInterrupt:
        print("\nReceived interrupt signal - exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()