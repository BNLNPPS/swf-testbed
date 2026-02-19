#!/usr/bin/env python3
"""
Load AI dialogue history at Claude Code session start.

Called by Claude Code SessionStart hook to inject recent conversation
context into the new session.

Environment:
    SWF_DIALOGUE_TURNS: Number of turns to load (default: 0 = disabled)
    SWF_MONITOR_HTTP_URL: Monitor API URL (default: http://pandaserver02.sdcc.bnl.gov/swf-monitor)

Output:
    Prints formatted dialogue history to stdout (injected into Claude's context)
"""

import json
import os
import sys
import getpass
from pathlib import Path
from typing import Optional


def get_turns_setting():
    # type: () -> int
    try:
        return int(os.getenv('SWF_DIALOGUE_TURNS', '0'))
    except ValueError:
        return 0


def load_sysprompt(cwd):
    # type: (str) -> Optional[str]
    sysprompt_path = Path(cwd) / 'SYSPROMPT.md'
    if sysprompt_path.exists():
        try:
            return sysprompt_path.read_text()
        except Exception:
            pass
    return None


def load_dialogue_via_api(username, turns, namespace=None):
    # type: (str, int, str) -> list
    import urllib.request
    import urllib.error

    base_url = os.getenv('SWF_MONITOR_HTTP_URL', 'http://pandaserver02.sdcc.bnl.gov/swf-monitor')
    params = "username={}&turns={}".format(username, turns)
    if namespace:
        params += "&namespace={}".format(namespace)
    url = "{}/api/ai-memory/?{}".format(base_url.rstrip('/'), params)

    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                return data.get('items', [])
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        pass

    return []


def format_dialogue(messages):
    # type: (list) -> str
    if not messages:
        return ""

    lines = ["## Recent Conversation History", ""]
    for msg in messages:
        role = msg.get('role', 'unknown').upper()
        content = msg.get('content', '')
        if len(content) > 2000:
            content = content[:2000] + "... [truncated]"
        lines.append("**{}:** {}".format(role, content))
        lines.append("")

    return "\n".join(lines)


def get_namespace(cwd):
    # type: (str) -> Optional[str]
    testbed_toml = os.path.join(cwd, 'workflows', 'testbed.toml')
    if not os.path.exists(testbed_toml):
        return None
    try:
        try:
            import tomllib
            with open(testbed_toml, 'rb') as f:
                data = tomllib.load(f)
            return data.get('testbed', {}).get('namespace')
        except ImportError:
            with open(testbed_toml, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('namespace'):
                        parts = line.split('=', 1)
                        if len(parts) == 2:
                            return parts[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None


def main():
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    source = hook_input.get('source', '')
    if source not in ('startup', 'resume'):
        sys.exit(0)

    cwd = hook_input.get('cwd', os.getcwd())
    username = getpass.getuser()
    namespace = get_namespace(cwd)

    output_parts = []

    sysprompt = load_sysprompt(cwd)
    if sysprompt:
        output_parts.append(sysprompt)

    turns = get_turns_setting()
    if turns > 0:
        messages = load_dialogue_via_api(username, turns, namespace)
        if messages:
            dialogue = format_dialogue(messages)
            if dialogue:
                output_parts.append(dialogue)

    if output_parts:
        print("\n\n".join(output_parts))

    sys.exit(0)


if __name__ == '__main__':
    main()
