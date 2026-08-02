"""Shared message-to-event mapping for testbed workflow episodes.

Testbed agents stamp every bus message with sender, msg_type,
timestamp, namespace, execution_id, and run_id; the mapping here turns
that shape into episode events and participant sightings without any
workflow-specific knowledge. Workflow definitions subclass
``TestbedEpisodeDefinition`` and add their completion passes.
"""

from typing import Dict, List, Optional

from swf_common_lib.episodes import EpisodeDefinition

#: Payload keys carried into event payloads when present.
PAYLOAD_KEYS = ('filename', 'sequence', 'site', 'req_id', 'input_dataset',
                'dataset', 'state', 'substate', 'reason', 'container')


def agent_kind(sender: str) -> str:
    """Sender agent name -> participant kind (e.g. 'daq_simulator')."""
    return sender.rsplit('-agent-', 1)[0] if '-agent-' in sender else 'agent'


class TestbedEpisodeDefinition(EpisodeDefinition):
    """Message mapping shared by all testbed workflow definitions."""

    scope = 'testbed'

    def event_from_message(self, message: Dict) -> Optional[Dict]:
        sender = message.get('sender') or message.get('sender_agent')
        msg_type = message.get('msg_type')
        when = message.get('sent_at') or message.get('timestamp')
        if not (sender and msg_type and when):
            return None
        payload = {key: message[key] for key in PAYLOAD_KEYS
                   if message.get(key) is not None}
        return {'time': when, 'kind': msg_type, 'participant': sender,
                'payload': payload}

    def participants_from_message(self, message: Dict) -> List[Dict]:
        sender = message.get('sender') or message.get('sender_agent')
        when = message.get('sent_at') or message.get('timestamp')
        if not sender:
            return []
        entry = {'id': sender, 'label': sender, 'kind': agent_kind(sender)}
        if when:
            entry['born_at'] = when
        return [entry]
