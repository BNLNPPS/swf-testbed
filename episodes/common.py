"""Shared message-to-event mapping for testbed workflow episodes.

Testbed agents stamp every bus message with sender, msg_type,
timestamp, namespace, execution_id, and run_id; the mapping here turns
that shape into episode events and participant sightings without any
workflow-specific knowledge. Workflow definitions subclass
``TestbedEpisodeDefinition`` and add their completion passes.
"""

from datetime import datetime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from swf_common_lib.episodes import EpisodeDefinition, utc_now_iso

#: Payload keys carried into event payloads when present.
PAYLOAD_KEYS = ('filename', 'sequence', 'site', 'req_id', 'input_dataset',
                'dataset', 'state', 'substate', 'reason', 'container')

#: Testbed agents stamp bus messages with naive local time; the agents
#: run in this zone.
AGENT_ZONE = ZoneInfo('America/New_York')


def agent_kind(sender: str) -> str:
    """Sender agent name -> participant kind (e.g. 'daq_simulator')."""
    return sender.rsplit('-agent-', 1)[0] if '-agent-' in sender else 'agent'


def message_time(message: Dict) -> Optional[str]:
    """A message's timestamp as timezone-aware ISO, or None.

    Bus timestamps are naive local stamps from the sending agent; the
    store accepts only aware times, so the agents' zone is attached.
    """
    raw = message.get('timestamp')
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=AGENT_ZONE)
    return parsed.isoformat()


class TestbedEpisodeDefinition(EpisodeDefinition):
    """Message mapping shared by all testbed workflow definitions."""

    scope = 'testbed'

    def started_at(self, message: Dict) -> str:
        return message_time(message) or utc_now_iso()

    def ended_at(self, message: Dict) -> str:
        return message_time(message) or utc_now_iso()

    def event_from_message(self, message: Dict) -> Optional[Dict]:
        sender = message.get('sender') or message.get('sender_agent')
        msg_type = message.get('msg_type')
        when = message_time(message)
        if not (sender and msg_type and when):
            return None
        payload = {key: message[key] for key in PAYLOAD_KEYS
                   if message.get(key) is not None}
        return {'time': when, 'kind': msg_type, 'participant': sender,
                'payload': payload}

    def participants_from_message(self, message: Dict) -> List[Dict]:
        sender = message.get('sender') or message.get('sender_agent')
        when = message_time(message)
        if not sender:
            return []
        entry = {'id': sender, 'label': sender, 'kind': agent_kind(sender)}
        if when:
            entry['born_at'] = when
        return [entry]
