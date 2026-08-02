# Agentic workflow view

A temporal view of one workflow execution: the agents that ran it, the
workers it provisioned, the messages that passed between them, and the
data that flowed through them — rendered as a live display while the
workflow runs and as a replay of any past execution. The view is a
Snapper surface; the engine mechanisms it requires are specified in
snapper-ai `docs/EPISODES.md`.

## Display

The plot is a stack of horizontal lanes over a time axis, in the
established Snapper Time history vocabulary (lanes, tiles, cut,
floater, step arrows).

- One lane per participant. The workflow runner and the agents open
  the stack; worker lanes appear below as workers come into
  existence. A prompt-processing execution opens with a handful of
  lanes and fans out to tens of worker lanes, then converges as jobs
  finish and the run tears down.
- Lanes are dynamic: a lane begins when its participant registers and
  ends when it exits. A finished participant's lane keeps its
  vertical slot, dimmed, to the end of the episode, so the fanout and
  convergence render as a stable shape and the vertical layout never
  reshuffles during a replay.
- Messages render as marks at their send time on the sender's lane,
  with connectors to recorded consumers where consumption records
  exist (see Data contract below).
- Activity on a lane renders as tiles: an agent's processing spans, a
  worker's created / started / finished phases.
- A click on any element opens its detail card: message payload,
  agent record, PanDA job record, file record.
- The cut and step arrows carry their Time history meanings: a click
  is a time slice, the arrows step the window. An execution-stepping
  mode — arrows move between executions rather than time windows —
  is a candidate addition.
- Live mode: while the execution runs, the view follows it, either
  pseudo-realtime as events land or promptly after completion. Both
  are feasible with current record latencies (seconds for messages
  and file records, minutes for PanDA job state).

## Evidence audit

Audited 2026-08-02 against prompt-processing execution
`prompt_processing-zyang2-0845` (run 102827, 15 STFs, decision-box
broadcast to E1_BNL and E1_JLAB) and the stf_datataking executions of
the same day. The full event sequence is reconstructable from
existing records, all in the system database with sub-second
timestamps:

| time (UTC) | event | record |
|---|---|---|
| 20:00:13 | execution starts | WorkflowExecution |
| 20:00:18 | run_imminent | message log |
| 20:00:26 | start_run | message log |
| 20:00:27–20:01:02 | stf_gen ×15, pause/resume around standby | message log |
| 20:00:29.6/.7 | stf_ready per site: the decision-box fanout | message log |
| 20:00:34.6 | PanDA tasks created, one per site | PanDA tasks |
| 20:05:55 | 15+15 jobs created | PanDA jobs |
| 20:11:22–43 | jobs start | PanDA jobs |
| 20:13–20:14:43 | jobs finish, tasks done | PanDA jobs, tasks |

## Data contract

Sources, all local database reads (no remote calls in the render
path):

- **WorkflowExecution** — episode identity, start and end, full
  parameter set including agent roster and workflow configuration.
- **WorkflowMessage** — sender agent, type, namespace, execution id,
  run id, payload, sent-at to the microsecond.
- **SystemAgent** — lane birth (`created_at` at registration), lane
  death (`operational_state` EXITED, stamped by `updated_at`),
  heartbeats, pid, hostname.
- **STF files / TF slices** — file-level flow; TF slice records name
  their `assigned_worker`.
- **PanDA tasks** — the run number is embedded in the task name
  (`user.<user>.swf.<run>.processed.<site>/`), giving a direct join
  from execution to tasks; creation, start, and end times per task.
- **PanDA jobs** — one record per worker with creation, start, and
  end times, site, and output metadata; jobs join to tasks by
  `jeditaskid`. For these workflows the worker lanes are the PanDA
  jobs born within the execution's tasks.

## Gaps to fill

Verified in code at the executing commits, 2026-08-02:

1. **Consumption records.** Messages record their sender only. The
   messaging philosophy is open listening — any agent may subscribe —
   so an addressee list recorded at send time would misstate the
   model. Instead, consumers record consumption: an agent that receives a
   message and acts on it records that fact with message id and
   timestamp. This yields the message connectors for the view and,
   independently, a workflow-integrity tool: a message no agent
   consumed, or a message consumed by an unexpected agent, becomes a
   detectable condition. Requires team discussion before
   implementation.
2. **Processing agent announcements.** The prompt-processing agent
   emits only heartbeats; its PanDA task submissions are visible only
   through the task records appearing. It should announce submission
   events on the bus like its peers announce theirs.
3. **Explicit agent exit stamp.** Lane death is currently inferred
   from the EXITED transition's `updated_at`; an explicit exit
   timestamp would remove the approximation.
4. **Durable episode capture.** Messages and file records are
   operational logs with retention policies. An episode is captured
   into a durable Snapper record at (or promptly after) execution
   end, so replay never depends on raw log retention.

## Delivery phases

1. **Episode capture** — a builder that joins the sources above into
   a durable episode record for each execution, live or promptly
   after completion.
2. **Replay view** — the lane display for any captured episode.
3. **Live mode** — the view follows a running execution.
4. **Production scale** — the same mechanism applied to epicprod
   workflows: campaign tasks fanning out across grid sites, with
   PanDA jobs as worker lanes. The mechanism is generic; only the
   provider data differs.

Related documentation: `fast-processing-workflow.md`,
`e0-e1-state-machine.md`, snapper-ai `docs/EPISODES.md`.
