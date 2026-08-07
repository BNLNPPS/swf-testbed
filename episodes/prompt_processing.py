"""Prompt-processing workflow episodes.

Agent messages are recorded live through the shared testbed mapping;
the completion pass joins the PanDA side — the tasks named by the run
number and the jobs born within them, which are the workflow's worker
lanes (docs/agentic-workflow-view.md).
"""

import logging

from .common import TestbedEpisodeDefinition

logger = logging.getLogger(__name__)

TERMINAL_TASK_STATUSES = {'done', 'finished', 'failed', 'broken',
                          'aborted', 'exhausted'}


def _aware(value):
    """PanDA REST timestamps are naive UTC; stamp the offset."""
    if not value:
        return None
    value = str(value)
    if value.endswith('Z') or '+' in value[10:]:
        return value
    return value + '+00:00'


class PromptProcessingEpisodes(TestbedEpisodeDefinition):
    workflow_name = 'prompt_processing'
    completion_deadline_seconds = 1800

    def completion_poll(self, context, ingest):
        run_id = ((context.last_message or {}).get('run_id')
                  or (context.first_message or {}).get('run_id'))
        if not run_id:
            logger.warning('episode %s has no run id; closing without '
                           'a PanDA join', context.episode_id)
            return True

        session = ingest.session
        base = ingest.base_url
        response = session.get(
            f'{base}/api/panda/tasks/',
            params={'taskname': f'swf.{run_id}.processed', 'days': 2},
            timeout=30)
        response.raise_for_status()
        tasks = response.json().get('items') or []
        if not tasks:
            # Tasks appear seconds after submission; none yet means the
            # join is early, not empty. The deadline bounds the wait.
            return False
        if any((t.get('status') or '') not in TERMINAL_TASK_STATUSES
               for t in tasks):
            return False

        events, participants = [], []
        for task in tasks:
            taskid = task['jeditaskid']
            task_pid = f'task-{taskid}'
            participants.append({
                'id': task_pid,
                'label': task.get('taskname') or task_pid,
                'kind': 'panda_task',
                'born_at': _aware(task.get('creationdate')),
                'died_at': _aware(task.get('endtime')),
            })
            events.append({
                'time': _aware(task.get('creationdate')),
                'kind': 'task_created',
                'participant': task_pid,
                'payload': {'jeditaskid': taskid,
                            'site': task.get('site'),
                            'status': task.get('status')},
            })
            jobs_response = session.get(
                f'{base}/api/panda/jobs/',
                params={'taskid': taskid, 'days': 2}, timeout=60)
            jobs_response.raise_for_status()
            for job in jobs_response.json().get('items') or []:
                job_pid = f"job-{job['pandaid']}"
                participants.append({
                    'id': job_pid,
                    'label': f"job {job['pandaid']}",
                    'kind': 'panda_job',
                    'born_at': _aware(job.get('creationtime')),
                    'died_at': _aware(job.get('endtime')),
                })
                for field, kind in (('creationtime', 'job_created'),
                                    ('starttime', 'job_started'),
                                    ('endtime', 'job_ended')):
                    if job.get(field):
                        events.append({
                            'time': _aware(job[field]),
                            'kind': kind,
                            'participant': job_pid,
                            'payload': {'site': job.get('computingsite'),
                                        'status': job.get('jobstatus'),
                                        'jeditaskid': taskid},
                        })

        ingest.append(scope=self.scope, episode_id=context.episode_id,
                      events=events, participants=participants)
        context.notes['panda_tasks'] = [t['jeditaskid'] for t in tasks]
        return True

    def summary(self, context):
        return {'run_id': ((context.last_message or {}).get('run_id')),
                'panda_tasks': context.notes.get('panda_tasks', [])}
