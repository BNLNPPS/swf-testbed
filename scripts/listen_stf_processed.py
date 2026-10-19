#!/usr/bin/env python3
"""Listen for stf_processed messages on ActiveMQ /topic/epictopic.

Used by CI to wait for PanDA task completion in prompt_processing workflow.
Exits 0 on successful completion, 1 on failure/timeout, 2 on connection error.
"""
import json
import os
import sys
import time
import threading

import stomp


class Listener(stomp.ConnectionListener):
    def __init__(self):
        self.message = None
        self.error = None
        self.connected = threading.Event()
        self.received = threading.Event()

    def on_connecting(self, host_and_port):
        pass

    def on_connected(self, frame):
        self.connected.set()

    def on_disconnected(self):
        # A silent broker-side disconnect (see heartbeats note in main)
        # must not leave the waiter blocking for the full timeout on a
        # dead connection.
        self.error = "connection lost before a message arrived"
        self.received.set()

    def on_message(self, frame):
        try:
            body = json.loads(frame.body)
            if body.get("msg_type") == "stf_processed":
                self.message = body
                self.received.set()
        except json.JSONDecodeError:
            pass

    def on_error(self, frame):
        self.error = frame.body


def main():
    host = os.getenv("ACTIVEMQ_HOST", "testbed-activemq")
    port = int(os.getenv("ACTIVEMQ_PORT", "61613"))
    username = os.getenv("ACTIVEMQ_USER", "admin")
    password = os.getenv("ACTIVEMQ_PASSWORD", "admin")
    timeout = int(os.getenv("LISTEN_TIMEOUT", "600"))

    # Artemis closes idle STOMP connections after connection-ttl-override
    # (default 60s) unless the client sends heartbeats. The workflow's
    # stf_processed messages arrive several minutes after subscribe, by
    # which time a heartbeat-less connection is gone and the messages are
    # missed. Match BaseAgent's heartbeat settings (swf-common-lib) so the
    # subscription stays live for the whole wait.
    conn = stomp.Connection([(host, port)], heartbeats=(30000, 30000))
    listener = Listener()
    conn.set_listener("", listener)

    try:
        conn.connect(username, password, wait=True, timeout=10)
    except Exception as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        return 2

    if not listener.connected.wait(10):
        print("Connection timeout", file=sys.stderr)
        return 2

    # Subscribe to /topic/epictopic
    conn.subscribe(destination="/topic/epictopic", id=1, ack="auto")

    print(f"Listening for stf_processed on {host}:{port} (timeout {timeout}s)...")

    if not listener.received.wait(timeout):
        print("Timeout waiting for stf_processed", file=sys.stderr)
        return 1

    # on_disconnected sets received without a message; fail loudly rather
    # than dereferencing None below.
    if listener.message is None:
        print(f"Connection lost: {listener.error}", file=sys.stderr)
        return 2

    msg = listener.message
    task_status = msg.get("task_status", "unknown")
    run_id = msg.get("run_id", "unknown")
    panda_task_id = msg.get("panda_task_id", "unknown")
    processed = msg.get("processed", 0)
    failed = msg.get("failed", 0)
    timed_out = msg.get("timed_out", False)

    print(f"Received stf_processed: run={run_id}, task={panda_task_id}, "
          f"status={task_status}, processed={processed}, failed={failed}, timed_out={timed_out}")

    # Success: task finished successfully (not failed/aborted/cancelled/timed_out)
    success = (
        task_status.lower() in ("finished", "done", "completed", "success")
        and not timed_out
        and failed == 0
    )

    if success:
        print("✅ PanDA task completed successfully")
        return 0
    else:
        print(f"❌ PanDA task failed: status={task_status}, timed_out={timed_out}, failed={failed}")
        return 1


if __name__ == "__main__":
    sys.exit(main())