"""
SUPERSEDED - Current simulator code is in workflows/workflow_simulator.py

Example DAQ Simulator Agent: Originates the workflow.
"""

from swf_common_lib.base_agent import BaseAgent
import json
import time
import uuid
from datetime import datetime

class DaqSimAgent(BaseAgent):
    """
    An example agent that simulates the DAQ system.
    It periodically generates 'stf_gen' messages to trigger the workflow,
    and listens on a control queue for commands.
    """

    def __init__(self, config_path=None):
        # This agent listens for control messages and produces STF messages.
        super().__init__(agent_type='daqsim', subscription_queue='/queue/daq_control',
                         config_path=config_path)
        self.running = True

    def on_message(self, frame):
        """
        Handles incoming control messages.
        """
        message_data, msg_type = self.log_received_message(frame)
        if message_data is None:
            return

        try:
            command = message_data.get('command')
            self.logger.info(f"Received command: {command}")
            
            if command == 'stop':
                self.running = False
            elif command == 'start':
                self.running = True
            else:
                self.logger.warning(f"Unknown command received: {command}")

        except Exception as e:
            self.logger.error(f"Error processing control message: {e}")

    def run(self):
        """
        The main run loop for the DAQ simulator. For this test, we will
        just use the base class's run method to test connection and heartbeat.
        """
        super().run()


    def generate_and_send_stf(self):
        """
        Generates a fake STF message and sends it to the 'epictopic'.
        """
        filename = f"stf_{uuid.uuid4().hex[:8]}.dat"
        now = datetime.utcnow()
        
        message = {
            'msg_type': 'stf_gen',
            'filename': filename,
            'start': now.strftime('%Y%m%d%H%M%S'),
            'end': now.strftime('%Y%m%d%H%M%S'),
            'state': 'physics',
            'substate': 'running',
            'comment': 'A simulated STF file.'
        }
        
        self.logger.info(f"Generated new STF: {filename}")
        self.send_message('/topic/epictopic', message)


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    script_dir = Path(__file__).parent

    parser = argparse.ArgumentParser(description="DAQ Simulator Agent - generates STF messages")
    parser.add_argument("--testbed-config", default=str(script_dir / "testbed.toml"),
                        help="Testbed config file (default: testbed.toml)")
    args = parser.parse_args()

    agent = DaqSimAgent(config_path=args.testbed_config)
    agent.run()