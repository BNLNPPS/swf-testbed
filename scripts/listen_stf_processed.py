#!/usr/bin/env python3
"""Listen for stf_processed messages on ActiveMQ /topic/epictopic.

Used by CI to wait for PanDA task completion in prompt_processing workflow.
With SWF_DECISION_BOX_ENABLED=true the workflow submits one PanDA task per
site (SWF_DECISION_BOX_SITES) and publishes one stf_processed message per
site, so the listener waits for every site's message and requires all of
them to report success. With the decision box disabled it returns on the
first message, as before.

Exits 0 on successful completion, 1 on failure/timeout, 2 on connection
error.
"""
import json
import os
import sys
import time
import threading

import stomp


def _parse_bool(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_sites(value):
    return [s.strip() for s in str(value).replace(",", " ").split() if s.strip()]


class Listener(stomp.ConnectionListener):
    def __init__(self, expected_sites):
        self.expected_sites = expected_sites
        self.messages = []
        self.error = None
        self.connected = threading.Event()
        self.received = threading.Event()

    def _complete(self):
        if not self.expected_sites:
            return bool(self.messages)
        seen = {m.get("site") for m in self.messages}
        return all(site in seen for site in self.expected_sites)

    def on_connecting(self, host_and_port):
        pass

    def on_connected(self, frame):
        self.connected.set()

    def on_disconnected(self):
        # A silent broker-side disconnect (see heartbeats note in main)
        # must not leave the waiter blocking for the full timeout on a
        # dead connection.
        self.error = "connection lost before all expected messages arrived"
        self.received.set()

    def on_message(self, frame):
        try:
            body = json.loads(frame.body)
            if body.get("msg_type") == "stf_processed":
                self.messages.append(body)
                if self._complete():
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
    decision_box = _parse_bool(os.getenv("SWF_DECISION_BOX_ENABLED", "false"))
    expected_sites = _parse_sites(os.getenv("SWF_DECISION_BOX_SITES", "")) if decision_box else []

    # Artemis closes idle STOMP connections after connection-ttl-override
    # (default 60s) unless the client sends heartbeats. The workflow's
    # stf_processed messages arrive several minutes after subscribe, by
    # which time a heartbeat-less connection is gone and the messages are
    # missed. Match BaseAgent's heartbeat settings (swf-common-lib) so the
    # subscription stays live for the whole wait.
    conn = stomp.Connection([(host, port)], heartbeats=(30000, 30000))
    listener = Listener(expected_sites)
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

    if expected_sites:
        print(f"Listening for stf_processed per site {expected_sites} on {host}:{port} "
              f"(timeout {timeout}s)...")
    else:
        print(f"Listening for stf_processed on {host}:{port} (timeout {timeout}s)...")

    if not listener.received.wait(timeout):
        seen = [m.get("site", "?") for m in listener.messages]
        print(f"Timeout waiting for stf_processed; sites seen: {seen}, "
              f"expected: {expected_sites or 'any'}", file=sys.stderr)
        return 1

    # on_disconnected sets received without enough messages; fail loudly
    # rather than asserting below.
    if not listener.messages or (expected_sites and not listener._complete()):
        print(f"Connection lost: {listener.error}", file=sys.stderr)
        return 2

    conn.disconnect()

    exit_code = 0
    for msg in listener.messages:
        task_status = msg.get("task_status", "unknown")
        run_id = msg.get("run_id", "unknown")
        panda_task_id = msg.get("panda_task_id", "unknown")
        site = msg.get("site", "unknown")
        processed = msg.get("processed", 0)
        failed = msg.get("failed", 0)
        timed_out = msg.get("timed_out", False)

        print(f"Received stf_processed: run={run_id}, task={panda_task_id}, site={site}, "
              f"status={task_status}, processed={processed}, failed={failed}, timed_out={timed_out}")

        # Success: task finished successfully (not failed/aborted/cancelled/timed_out)
        success = (
            task_status.lower() in ("finished", "done", "completed", "success")
            and not timed_out
            and failed == 0
        )
        if not success:
            print(f"❌ PanDA task failed: site={site}, status={task_status}, "
                  f"timed_out={timed_out}, failed={failed}")
            exit_code = 1

    if exit_code == 0:
        n = len(listener.messages)
        print(f"✅ PanDA task{'s' if n > 1 else ''} completed successfully ({n} message{n > 1 and 's' or ''})")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
