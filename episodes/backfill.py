"""Backfill workflow episodes from recorded messages.

Replays a past execution's recorded bus messages through the same
definitions and engine the live builder runs, then drives the
completion pass to closure. The episode carries the recorded times,
not the replay time. Bounded by message-log retention.

Usage (testbed venv, SWF_MONITOR_HTTP_URL and SWF_API_TOKEN in the
environment):

    python -m episodes.backfill <execution_id> [<execution_id> ...]
"""

import os
import sys
import time

import requests

from swf_common_lib.episodes import EpisodeBuilder, MonitorEpisodeIngest

from . import ALL_DEFINITIONS

COMPLETION_ATTEMPTS = 60
COMPLETION_INTERVAL_SECONDS = 5


def backfill(execution_id: str) -> bool:
    base = (os.environ.get('SWF_MONITOR_HTTP_URL') or '').rstrip('/')
    token = os.environ.get('SWF_API_TOKEN') or ''
    if not base:
        print('SWF_MONITOR_HTTP_URL is not set')
        return False

    session = requests.Session()
    if token:
        session.headers['Authorization'] = f'Token {token}'
    response = session.get(f'{base}/api/workflow-messages/',
                           params={'execution_id': execution_id},
                           timeout=60)
    response.raise_for_status()
    rows = response.json()
    if isinstance(rows, dict):
        rows = rows.get('results') or []
    rows.sort(key=lambda row: row.get('sent_at') or '')
    messages = [row.get('message_content') or {} for row in rows]
    messages = [m for m in messages
                if m.get('execution_id') == execution_id]
    if not messages:
        print(f'{execution_id}: no recorded messages')
        return False

    ingest = MonitorEpisodeIngest(base_url=base, token=token,
                                  builder_identity='episode-backfill')
    builder = EpisodeBuilder(
        [definition() for definition in ALL_DEFINITIONS], ingest)
    handled = sum(1 for m in messages if builder.handle_message(m))
    print(f'{execution_id}: {handled}/{len(messages)} recorded messages '
          f'replayed')

    for _ in range(COMPLETION_ATTEMPTS):
        builder.tick()
        if not builder.active:
            print(f'{execution_id}: episode closed')
            return True
        time.sleep(COMPLETION_INTERVAL_SECONDS)
    print(f'{execution_id}: completion did not converge')
    return False


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    results = [backfill(execution_id) for execution_id in sys.argv[1:]]
    sys.exit(0 if all(results) else 1)
