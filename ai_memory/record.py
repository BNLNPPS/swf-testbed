#!/usr/bin/env python3
"""
Record AI dialogue exchanges to the swf-testbed database.

Called by Claude Code hooks (UserPromptSubmit, Stop) to persist
dialogue for cross-session context.

Usage:
    echo '{"hook_event_name": "UserPromptSubmit", "prompt": "...", ...}' | python record.py
    echo '{"hook_event_name": "Stop", "transcript_path": "...", ...}' | python record.py

Environment:
    SWF_DIALOGUE_TURNS: Must be set and > 0 to enable recording
    SWF_MONITOR_HTTP_URL: Monitor API URL (default: http://localhost:8000/swf-monitor)
"""

import json
import os
import sys
import getpass
from typing import Optional


def get_turns_setting() -> int:
    """Get the dialogue turns setting from environment."""
    try:
        return int(os.getenv('SWF_DIALOGUE_TURNS', '0'))
    except ValueError:
        return 0


def record_via_api(username: str, session_id: str, role: str, content: str,
                   namespace: str = None, project_path: str = None) -> bool:
    """Record dialogue via MCP REST API."""
    import urllib.request
    import urllib.error

    base_url = os.getenv('SWF_MONITOR_HTTP_URL', 'http://localhost:8000/swf-monitor')
    url = f"{base_url.rstrip('/')}/mcp/"

    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "swf_record_ai_memory",
            "arguments": {
                "username": username,
                "session_id": session_id,
                "role": role,
                "content": content,
                "namespace": namespace,
                "project_path": project_path,
            }
        },
        "id": 1
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return False


def extract_assistant_response(transcript_path: str) -> Optional[str]:
    """Extract the last assistant response from a Claude Code transcript."""
    if not transcript_path or not os.path.exists(transcript_path):
        return None

    try:
        # Read the transcript JSONL file
        with open(transcript_path, 'r') as f:
            lines = f.readlines()

        # Find the last assistant message
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                # Look for assistant message content
                if entry.get('role') == 'assistant':
                    content = entry.get('content', '')
                    if isinstance(content, list):
                        # Extract text blocks from content array
                        texts = [c.get('text', '') for c in content if c.get('type') == 'text']
                        return '\n'.join(texts)
                    return str(content)
            except json.JSONDecodeError:
                continue
    except Exception:
        pass

    return None


def main():
    # Check if recording is enabled
    turns = get_turns_setting()
    if turns <= 0:
        sys.exit(0)  # Silent exit - not enabled

    # Read hook input from stdin
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)  # Silent exit on bad input

    event = hook_input.get('hook_event_name', '')
    session_id = hook_input.get('session_id', 'unknown')
    cwd = hook_input.get('cwd', '')
    username = getpass.getuser()

    # Get namespace from testbed config if available
    namespace = None
    testbed_toml = os.path.join(cwd, 'workflows', 'testbed.toml')
    if os.path.exists(testbed_toml):
        try:
            import tomllib
            with open(testbed_toml, 'rb') as f:
                data = tomllib.load(f)
            namespace = data.get('testbed', {}).get('namespace')
        except Exception:
            pass

    if event == 'UserPromptSubmit':
        # Record user prompt
        prompt = hook_input.get('prompt', '')
        if prompt:
            record_via_api(
                username=username,
                session_id=session_id,
                role='user',
                content=prompt,
                namespace=namespace,
                project_path=cwd,
            )

    elif event == 'Stop':
        # Extract and record assistant response from transcript
        transcript_path = hook_input.get('transcript_path')
        response = extract_assistant_response(transcript_path)
        if response:
            record_via_api(
                username=username,
                session_id=session_id,
                role='assistant',
                content=response,
                namespace=namespace,
                project_path=cwd,
            )

    sys.exit(0)


if __name__ == '__main__':
    main()
