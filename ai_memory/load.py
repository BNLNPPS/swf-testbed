#!/usr/bin/env python3
"""
Load AI dialogue history at Claude Code session start.

Called by Claude Code SessionStart hook to inject recent conversation
context into the new session.

Usage:
    echo '{"hook_event_name": "SessionStart", "source": "startup", ...}' | python load.py

Environment:
    SWF_DIALOGUE_TURNS: Number of turns to load (default: 0 = disabled)
    SWF_MONITOR_HTTP_URL: Monitor API URL (default: http://localhost:8000/swf-monitor)

Output:
    Prints formatted dialogue history to stdout (injected into Claude's context)
"""

import json
import os
import sys
import getpass
from pathlib import Path
from typing import Optional


def get_turns_setting() -> int:
    """Get the dialogue turns setting from environment."""
    try:
        return int(os.getenv('SWF_DIALOGUE_TURNS', '0'))
    except ValueError:
        return 0


def load_sysprompt(cwd: str) -> Optional[str]:
    """Load SYSPROMPT.md from project root if it exists."""
    sysprompt_path = Path(cwd) / 'SYSPROMPT.md'
    if sysprompt_path.exists():
        try:
            return sysprompt_path.read_text()
        except Exception:
            pass
    return None


def load_dialogue_via_api(username: str, turns: int, namespace: str = None) -> list:
    """Load recent dialogue via MCP REST API."""
    import urllib.request
    import urllib.error

    base_url = os.getenv('SWF_MONITOR_HTTP_URL', 'http://localhost:8000/swf-monitor')
    url = f"{base_url.rstrip('/')}/mcp/"

    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "swf_get_ai_memory",
            "arguments": {
                "username": username,
                "turns": turns,
                "namespace": namespace,
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
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                result = data.get('result', {})
                if isinstance(result, dict):
                    # Handle MCP tool response format
                    content = result.get('content', [])
                    if content and isinstance(content, list):
                        text = content[0].get('text', '{}')
                        parsed = json.loads(text)
                        return parsed.get('items', [])
                return result.get('items', [])
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        pass

    return []


def format_dialogue(messages: list) -> str:
    """Format dialogue messages for context injection."""
    if not messages:
        return ""

    lines = ["## Recent Conversation History", ""]
    for msg in messages:
        role = msg.get('role', 'unknown').upper()
        content = msg.get('content', '')
        # Truncate very long messages
        if len(content) > 2000:
            content = content[:2000] + "... [truncated]"
        lines.append(f"**{role}:** {content}")
        lines.append("")

    return "\n".join(lines)


def main():
    # Read hook input from stdin
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    # Only load on startup or resume
    source = hook_input.get('source', '')
    if source not in ('startup', 'resume'):
        sys.exit(0)

    cwd = hook_input.get('cwd', os.getcwd())
    username = getpass.getuser()

    # Get namespace from testbed config if available
    namespace = None
    testbed_toml = Path(cwd) / 'workflows' / 'testbed.toml'
    if testbed_toml.exists():
        try:
            import tomllib
            with open(testbed_toml, 'rb') as f:
                data = tomllib.load(f)
            namespace = data.get('testbed', {}).get('namespace')
        except Exception:
            pass

    output_parts = []

    # 1. Load SYSPROMPT.md if it exists
    sysprompt = load_sysprompt(cwd)
    if sysprompt:
        output_parts.append(sysprompt)

    # 2. Load dialogue history if enabled
    turns = get_turns_setting()
    if turns > 0:
        messages = load_dialogue_via_api(username, turns, namespace)
        if messages:
            dialogue = format_dialogue(messages)
            if dialogue:
                output_parts.append(dialogue)

    # Output to stdout (will be injected into Claude's context)
    if output_parts:
        print("\n\n".join(output_parts))

    sys.exit(0)


if __name__ == '__main__':
    main()
