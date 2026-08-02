"""STF datataking workflow episodes.

The default testbed exercise: agent messages recorded live through the
shared testbed mapping, no workload join — the workflow's example
agents submit nothing.
"""

from .common import TestbedEpisodeDefinition


class StfDatatakingEpisodes(TestbedEpisodeDefinition):
    workflow_name = 'stf_datataking'
    completion_deadline_seconds = 60

    def summary(self, context):
        return {'run_id': (context.last_message or {}).get('run_id')}
