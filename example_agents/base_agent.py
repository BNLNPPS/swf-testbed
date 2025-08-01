"""
This module contains the base class for all example agents.
"""

import os
import sys
import time
import stomp
import requests
import json
import logging
from pathlib import Path

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

# Auto-setup environment when module is imported (unless already done)
if not os.getenv('SWF_ENV_LOADED'):
    setup_environment()
    os.environ['SWF_ENV_LOADED'] = 'true'

# Import the centralized logging from swf-common-lib
from swf_common_lib.rest_logging import setup_rest_logging

# Enable STOMP debug logging to see connection details
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

# Console handler for immediate output
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
console_handler.setFormatter(formatter)

# Enable debug logging for stomp.py
stomp_logger = logging.getLogger('stomp')
stomp_logger.setLevel(logging.DEBUG)
stomp_logger.addHandler(console_handler)

# Root logger
root_logger = logging.getLogger()
root_logger.addHandler(console_handler)


class ExampleAgent(stomp.ConnectionListener):
    """
    A base class for creating standalone STF workflow agents.

    This class handles the common tasks of:
    - Connecting to the ActiveMQ message broker (and inheriting from stomp.ConnectionListener).
    - Communicating with the swf-monitor REST API.
    - Running a persistent process with graceful shutdown.
    """

    def __init__(self, agent_type, subscription_queue):
        self.agent_type = agent_type
        self.subscription_queue = subscription_queue
        self.agent_name = f"{self.agent_type.lower()}-agent-example"

        # Configuration from environment variables
        self.monitor_url = os.getenv('SWF_MONITOR_URL', 'http://localhost:8002').rstrip('/')
        # Use HTTP URL for REST logging (no auth required)
        self.base_url = os.getenv('SWF_MONITOR_HTTP_URL', 'http://localhost:8002').rstrip('/')
        self.api_token = os.getenv('SWF_API_TOKEN')
        self.mq_host = os.getenv('ACTIVEMQ_HOST', 'localhost')
        self.mq_port = int(os.getenv('ACTIVEMQ_PORT', 61612))  # STOMP port for Artemis on this system
        self.mq_user = os.getenv('ACTIVEMQ_USER', 'admin')
        self.mq_password = os.getenv('ACTIVEMQ_PASSWORD', 'admin')
        
        # SSL configuration
        self.use_ssl = os.getenv('ACTIVEMQ_USE_SSL', 'False').lower() == 'true'
        self.ssl_ca_certs = os.getenv('ACTIVEMQ_SSL_CA_CERTS', '')
        self.ssl_cert_file = os.getenv('ACTIVEMQ_SSL_CERT_FILE', '')
        self.ssl_key_file = os.getenv('ACTIVEMQ_SSL_KEY_FILE', '')
        
        # Set up centralized REST logging
        self.logger = setup_rest_logging('example_agent', self.agent_name, self.base_url)

        # Create connection matching swf-common-lib working example
        self.conn = stomp.Connection(
            host_and_ports=[(self.mq_host, self.mq_port)],
            vhost=self.mq_host,
            try_loopback_connect=False
        )
        
        # Configure SSL if enabled - must be done before set_listener
        if self.use_ssl:
            import ssl
            logging.info(f"Configuring SSL connection with CA certs: {self.ssl_ca_certs}")
            
            if self.ssl_ca_certs:
                # Configure SSL transport
                self.conn.transport.set_ssl(
                    for_hosts=[(self.mq_host, self.mq_port)],
                    ca_certs=self.ssl_ca_certs,
                    ssl_version=ssl.PROTOCOL_TLS_CLIENT
                )
                logging.info("SSL transport configured successfully")
            else:
                logging.warning("SSL enabled but no CA certificate file specified")
        
        self.conn.set_listener('', self)
        self.api = requests.Session()
        if self.api_token:
            self.api.headers.update({'Authorization': f'Token {self.api_token}'})
        
        # For localhost development, disable SSL verification
        if 'localhost' in self.monitor_url or '127.0.0.1' in self.monitor_url:
            self.api.verify = False
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def run(self):
        """
        Connects to the message broker and runs the agent's main loop.
        """
        logging.info(f"Starting {self.agent_name}...")
        logging.info(f"Connecting to ActiveMQ at {self.mq_host}:{self.mq_port} with user '{self.mq_user}'")
        
        # Track MQ connection status
        self.mq_connected = False
        
        try:
            logging.debug("Attempting STOMP connection with version 1.2...")
            # Use STOMP version 1.2 with client-id as per working example
            self.conn.connect(
                self.mq_user, 
                self.mq_password, 
                wait=True, 
                version='1.2',
                headers={'client-id': self.agent_name}
            )
            self.mq_connected = True
            logging.info("Successfully connected to ActiveMQ")
            
            self.conn.subscribe(destination=self.subscription_queue, id=1, ack='auto')
            logging.info(f"Subscribed to queue: '{self.subscription_queue}'")
            
            # Initial registration/heartbeat
            self.send_heartbeat()

            logging.info(f"{self.agent_name} is running. Press Ctrl+C to stop.")
            while True:
                time.sleep(60) # Keep the main thread alive, heartbeats can be added here
                self.send_heartbeat()

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
            if self.conn and self.conn.is_connected():
                self.conn.disconnect()
                self.mq_connected = False
                logging.info("Disconnected from ActiveMQ.")

    def on_connected(self, frame):
        """Handle successful connection to ActiveMQ."""
        logging.info(f"Successfully connected to ActiveMQ: {frame.headers}")
        self.mq_connected = True
    
    def on_error(self, frame):
        logging.error(f'Received an error from ActiveMQ: {frame.body}')
        self.mq_connected = False
    
    def on_disconnected(self):
        """Handle disconnection from ActiveMQ."""
        logging.warning("Disconnected from ActiveMQ")
        self.mq_connected = False
        # Send heartbeat to update status
        self.send_heartbeat()

    def on_message(self, frame):
        """
        Callback for handling incoming messages.
        This method must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement on_message")

    def send_message(self, destination, message_body):
        """
        Sends a JSON message to a specific destination.
        """
        try:
            self.conn.send(body=json.dumps(message_body), destination=destination)
            logging.info(f"Sent message to '{destination}': {message_body}")
        except Exception as e:
            logging.error(f"Failed to send message to '{destination}': {e}")

    def _api_request(self, method, endpoint, json_data=None):
        """
        Helper method to make a request to the monitor API.
        """
        url = f"{self.monitor_url}/api/v1{endpoint}"
        try:
            response = self.api.request(method, url, json=json_data, timeout=10)
            response.raise_for_status()  # Raise an exception for bad status codes
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"API request failed: {method.upper()} {url} - {e}")
            return None

    def send_heartbeat(self):
        """Registers the agent and sends a heartbeat to the monitor."""
        logging.info("Sending heartbeat to monitor...")
        
        # Determine overall status based on MQ connection
        status = "OK" if getattr(self, 'mq_connected', False) else "WARNING"
        
        # Build description with connection details
        mq_status = "connected" if getattr(self, 'mq_connected', False) else "disconnected"
        description = f"Example {self.agent_type} agent. MQ: {mq_status}"
        
        payload = {
            "instance_name": self.agent_name,
            "agent_type": self.agent_type,
            "status": status,
            "description": description,
            "mq_connected": getattr(self, 'mq_connected', False)  # Include MQ status in payload
        }
        
        result = self._api_request('post', '/systemagents/heartbeat/', payload)
        if result:
            logging.info(f"Heartbeat sent successfully. Status: {status}, MQ: {mq_status}")
        else:
            logging.warning("Failed to send heartbeat to monitor")

