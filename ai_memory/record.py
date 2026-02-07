#!/usr/bin/env python3
"""
Record AI dialogue exchanges to the swf-testbed database.

Called by Claude Code hooks (UserPromptSubmit, Stop) to persist
dialogue for cross-session context.

Environment:
    SWF_DIALOGUE_TURNS: Must be set and > 0 to enable recording
    SWF_MONITOR_HTTP_URL: Monitor API URL (default: http://pandaserver02.sdcc.bnl.gov/swf-monitor)
"""

import json
import os
import sys
import getpass
from typing import Optional


def get_turns_setting():
    # type: () -> int
    try:
        return int(os.getenv('SWF_DIALOGUE_TURNS', '0'))
    except ValueError:
        return 0


def record_via_api(username, session_id, role, content,
                   namespace=None, project_path=None):
    # type: (str, str, str, str, str, str) -> bool
    import urllib.request
    import urllib.error

    base_url = os.getenv('SWF_MONITOR_HTTP_URL', 'http://pandaserver02.sdcc.bnl.gov/swf-monitor')
    url = "{}/api/ai-memory/record/".format(base_url.rstrip('/'))

    payload = {
        "username": username,
        "session_id": session_id,
        "role": role,
        "content": content,
        "namespace": namespace,
        "project_path": project_path,
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


def extract_assistant_response(transcript_path):
    # type: (str) -> Optional[str]
    if not transcript_path or not os.path.exists(transcript_path):
        return None

    try:
        with open(transcript_path, 'r') as f:
            lines = f.readlines()

        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get('role') == 'assistant':
                    content = entry.get('content', '')
                    if isinstance(content, list):
                        texts = [c.get('text', '') for c in content if c.get('type') == 'text']
                        return '\n'.join(texts)
                    return str(content)
            except json.JSONDecodeError:
                continue
    except Exception:
        pass

    return None


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
    turns = get_turns_setting()
    if turns <= 0:
        sys.exit(0)

    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    event = hook_input.get('hook_event_name', '')
    session_id = hook_input.get('session_id', 'unknown')
    cwd = hook_input.get('cwd', '')
    username = getpass.getuser()
    namespace = get_namespace(cwd)

    if event == 'UserPromptSubmit':
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
