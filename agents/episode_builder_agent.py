#!/usr/bin/env python3
"""Episode builder agent: records workflow episodes from bus traffic.

One more listener on the epictopic, in keeping with the open-listening
messaging philosophy: it consumes every message, routes executions to
the armed episode definitions (the episodes package), and drives each
episode through open, append, completion, and close against the
monitor's episode ingest REST (docs/agentic-workflow-view.md).

Episodes are scope-wide, so unlike workflow agents this agent applies
no namespace filtering: every namespace's executions are recorded.
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swf_common_lib.base_agent import BaseAgent
from swf_common_lib.episodes import EpisodeBuilder, MonitorEpisodeIngest

from episodes import ALL_DEFINITIONS


class EpisodeBuilderAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_type='EPISODE_BUILDER',
                         subscription_queue='/topic/epictopic')
        ingest = MonitorEpisodeIngest(
            base_url=self.base_url,
            token=self.api_token,
            builder_identity=self.agent_name,
        )
        self.builder = EpisodeBuilder(
            [definition() for definition in ALL_DEFINITIONS], ingest)
        logging.info('armed definitions: %s',
                     [d.workflow_name for d in self.builder.definitions])

    def on_message(self, frame):
        try:
            message = json.loads(frame.body)
        except (ValueError, TypeError) as exc:
            logging.error('unparseable message dropped: %s', exc)
            return
        self.builder.handle_message(message)

    def send_heartbeat(self):
        result = super().send_heartbeat()
        # The heartbeat cycle is the completion-poll cadence.
        self.builder.tick()
        return result


if __name__ == '__main__':
    EpisodeBuilderAgent().run()
