#!/usr/bin/env python3
"""
Remote SSE Receiver: Connects to the monitor's SSE stream to receive workflow messages.

This script receives real-time workflow messages via Server-Sent Events (SSE)
from the swf-monitor running under production Apache. It connects to the SSE
endpoint and logs received messages.

Command-line filtering examples (based on remote_sse_sender.py messages):
  python remote_sse_receiver.py --message sse_test
  python remote_sse_receiver.py --message stf_ready,processing_complete  
  python remote_sse_receiver.py --agent sse_sender-agent
  python remote_sse_receiver.py --message sse_test --agent sse_sender-agent
"""

import os
import sys
import time
import json
import signal
import argparse
from pathlib import Path

import requests
from swf_common_lib.base_agent import BaseAgent

# Canonical production base URL (can be overridden by SWF_MONITOR_PROD_URL)
DEFAULT_MONITOR_BASE = "https://pandaserver02.sdcc.bnl.gov/swf-monitor"

def setup_environment() -> None:
    """Load environment variables from ~/.env file if present."""
    env_file = Path.home() / ".env"
    if env_file.exists():
        with env_file.open() as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                if line.startswith('export '):
                    line = line[7:]
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip("'\"")


class RemoteSSEReceiver(BaseAgent):
    """Production-only SSE client for swf-monitor that registers as an agent."""

    def __init__(self, msg_types=None, agents=None) -> None:
        setup_environment()

        # Production monitor base URL (env override, otherwise production default)
        env_url = os.getenv('SWF_MONITOR_PROD_URL')
        if env_url:
            monitor_base = env_url.rstrip('/')
        else:
            monitor_base = DEFAULT_MONITOR_BASE
            print(f"ℹ️  Using default production URL: {monitor_base} (override with SWF_MONITOR_PROD_URL)")

        # Override monitor URLs for production
        os.environ['SWF_MONITOR_URL'] = monitor_base
        os.environ['SWF_MONITOR_HTTP_URL'] = monitor_base

        # Initialize BaseAgent with descriptive type and name
        super().__init__(agent_type='sse_receiver', subscription_queue='/topic/epictopic')
        
        # Override agent name if user provided one
        user_agent_name = os.getenv('SWF_SSE_RECEIVER_NAME')
        if user_agent_name:
            self.agent_name = user_agent_name
        self.monitor_base = monitor_base
        self.msg_types = msg_types
        self.agents = agents

        # HTTP session: production defaults (verify=True, env proxies honored)
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Token {self.api_token}',
            'Cache-Control': 'no-cache',
            'Accept': 'text/event-stream',
            'Connection': 'keep-alive',
        })

        # Simple shutdown - just exit immediately
        signal.signal(signal.SIGINT, lambda signum, frame: sys.exit(0))
        signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))

        print("🔧 Remote SSE Receiver initialized")
        print(f"   Monitor base: {self.monitor_base}")
        print(f"   Token prefix: {self.api_token[:12]}...")
        ca_bundle = os.getenv('REQUESTS_CA_BUNDLE')
        if ca_bundle:
            print(f"   CA bundle:   {ca_bundle}")


    def connect_and_receive(self) -> None:
        """Connect to SSE stream and process messages in a loop."""
        # Build stream URL with filters
        stream_url = f"{self.monitor_base}/api/messages/stream/"
        params = []
        if self.msg_types:
            params.append(f"msg_types={','.join(self.msg_types)}")
        if self.agents:
            params.append(f"agents={','.join(self.agents)}")
        if params:
            stream_url += "?" + "&".join(params)
        status_url = f"{self.monitor_base}/api/messages/stream/status/"
        print(f"📡 Connecting to SSE stream: {stream_url}")

        while True:
            try:
                # Status precheck
                print("🔌 Testing SSE endpoint...")
                # Do not follow redirects; 302 likely indicates auth not reaching Django
                # The status endpoint is a regular DRF endpoint, not an SSE stream, so override Accept header
                status_resp = self.session.get(status_url, timeout=20, allow_redirects=False, headers={'Accept': 'application/json'})
                if status_resp.status_code != 200:
                    if status_resp.status_code in (401, 403):
                        print(f"❌ Auth failed (HTTP {status_resp.status_code}). Check SWF_API_TOKEN (token may be missing/invalid).")
                        www = status_resp.headers.get('WWW-Authenticate')
                        if www:
                            print(f"   WWW-Authenticate: {www}")
                        print("   If running via Apache, ensure 'WSGIPassAuthorization On' is enabled so the Authorization header reaches Django.")
                    elif 300 <= status_resp.status_code < 400:
                        loc = status_resp.headers.get('Location', 'unknown')
                        print(f"❌ Got redirect (HTTP {status_resp.status_code}) to {loc}. This usually means Authorization isn't being passed through.")
                        print("   Enable 'WSGIPassAuthorization On' in Apache for the /swf-monitor app and reload Apache.")
                    else:
                        print(f"❌ SSE endpoint not available: HTTP {status_resp.status_code}")
                    print("   Retrying in 15 seconds...")
                    time.sleep(15)
                    continue

                # Open the SSE stream (blocks quietly while waiting for events)
                # Do not follow redirects; treat as auth failure
                response = self.session.get(stream_url, stream=True, timeout=(10, 3600), allow_redirects=False)
                if response.status_code != 200:
                    if response.status_code in (401, 403):
                        print(f"❌ Auth failed opening stream (HTTP {response.status_code}). Check SWF_API_TOKEN.")
                        www = response.headers.get('WWW-Authenticate')
                        if www:
                            print(f"   WWW-Authenticate: {www}")
                        print("   If behind Apache, ensure 'WSGIPassAuthorization On' is configured.")
                    elif 300 <= response.status_code < 400:
                        loc = response.headers.get('Location', 'unknown')
                        print(f"❌ Redirect when opening stream (HTTP {response.status_code}) to {loc}. Authorization likely not forwarded by Apache.")
                        print("   Configure 'WSGIPassAuthorization On' and reload Apache.")
                    else:
                        print(f"❌ Failed to open stream: HTTP {response.status_code}")
                        print("   Response Headers:")
                        for key, value in response.headers.items():
                            print(f"     {key}: {value}")
                        print("   Response Body:")
                        print(f"     {response.text}")
                    print("   Retrying in 15 seconds...")
                    time.sleep(15)
                    continue

                print("✅ SSE stream opened - waiting for events... (Ctrl+C to exit)")
                
                # Register this SSE receiver as an active agent
                self.send_heartbeat()
                
                print("-" * 60)
                # streaming until broken or stopped
                self._process_sse_stream(response)

            except requests.exceptions.ReadTimeout as e:
                print(f"⏱️  Read timeout while waiting for messages: {e}")
                print("   Reconnecting in 15 seconds...")
                time.sleep(15)
            except requests.exceptions.RequestException as e:
                print(f"❌ Connection error: {e}")
                print("   Retrying in 15 seconds...")
                time.sleep(15)
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
                time.sleep(15)


    def _process_sse_stream(self, response) -> None:
        event_buffer = []
        try:
            for line in response.iter_lines(decode_unicode=True, chunk_size=1):
                if line is None:
                    continue
                line = line.strip()
                if not line:
                    if event_buffer:
                        self._handle_sse_event(event_buffer)
                        event_buffer = []
                else:
                    event_buffer.append(line)
        except KeyboardInterrupt:
            print("\n📡 Received interrupt - closing connection...")
        except Exception as e:
            print(f"❌ Error processing stream: {e}")
        finally:
            try:
                response.close()
            except Exception:
                pass

    def _handle_sse_event(self, event_lines) -> None:
        event_type = "message"
        event_data = ""
        for line in event_lines:
            if line.startswith('event: '):
                event_type = line[7:]
            elif line.startswith('data: '):
                event_data = line[6:]

        timestamp = time.strftime("%H:%M:%S")
        if event_type == "connected":
            print(f"[{timestamp}] 🔗 Connected to SSE stream")
            try:
                data = json.loads(event_data)
                client_id = data.get('client_id', 'unknown')
                print(f"[{timestamp}] 📋 Client ID: {client_id}")
            except Exception:
                pass
        elif event_type == "heartbeat":
            # Stay quiet on heartbeats to avoid log spam
            return
        else:
            try:
                data = json.loads(event_data)
                msg_type = data.get('msg_type', 'unknown')
                processed_by = data.get('processed_by', 'unknown')
                run_id = data.get('run_id', 'N/A')
                print(f"[{timestamp}] 📨 Message received:")
                print(f"         Message: {msg_type}")
                print(f"           Agent: {processed_by}")
                print(f"            Run:  {run_id}")
                if 'message' in data:
                    print(f"            Text: {data['message']}")
                if 'filename' in data:
                    print(f"            File: {data['filename']}")
                print("-" * 60)
            except json.JSONDecodeError:
                print(f"[{timestamp}] 📨 Non-JSON message: {event_data}")
            except Exception as e:
                print(f"[{timestamp}] ❌ Error parsing message: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remote SSE Receiver: Connect to workflow monitor SSE stream",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python remote_sse_receiver.py                           # Receive all messages
  python remote_sse_receiver.py --message stf_gen         # Only STF generation messages
  python remote_sse_receiver.py --agent daq-simulator     # Only messages from daq-simulator
  python remote_sse_receiver.py --message stf_gen,stf_ready --agent daq-simulator

Environment variables:
  SWF_SSE_RECEIVER_NAME - Required: descriptive agent name
  SWF_API_TOKEN         - Required: monitor API token
  SWF_MONITOR_PROD_URL  - Optional: override monitor URL
        """)
    
    parser.add_argument('--message', '--msg-type', dest='msg_types',
                        help='Filter by message type(s), comma-separated (e.g., stf_gen,stf_ready)')
    parser.add_argument('--agent', dest='agents', 
                        help='Filter by agent name(s), comma-separated (e.g., daq-simulator,data-agent)')
    
    args = parser.parse_args()
    
    # Parse comma-separated values
    msg_types = None
    if args.msg_types:
        msg_types = [t.strip() for t in args.msg_types.split(',')]
    
    agents = None
    if args.agents:
        agents = [a.strip() for a in args.agents.split(',')]
    
    try:
        receiver = RemoteSSEReceiver(msg_types=msg_types, agents=agents)
        if msg_types or agents:
            filters = []
            if msg_types:
                filters.append(f"messages: {', '.join(msg_types)}")
            if agents:
                filters.append(f"agents: {', '.join(agents)}")
            print(f"🔍 Filtering enabled - {' | '.join(filters)}")
        else:
            print("📬 Receiving all messages (no filtering)")
        
        receiver.connect_and_receive()
    except KeyboardInterrupt:
        print("\n📡 Received interrupt signal - exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()