# Fast Processing Workflow

Near real-time processing of ePIC streaming data for shifter monitoring using PanDA, Event Service, iDDS and the Processing Agent.

## Challenge and Solution

**Challenge**: STF files require 19 hours single-threaded reconstruction, but shifters need results in ~30 seconds.

**Solution**: Message-based distribution of fine-grained processing across many workers:
- FastMon samples STF files (~5% of data)
- Processing Agent creates TF slices (~15 per STF sample)
- Workers process slices in parallel via ActiveMQ dispatch (~30 sec/slice)
- PanDA Event Service provides bookkeeping and automatic retry
- iDDS manages rapid slice-to-worker assignments

Target: STF-equivalent statistics in ~30 seconds → 30-40 sec latency from beam collision.

## Data Flow

```
DAQ → STF (2GB, ~0.5Hz) → FastMon → STF samples → PA → TF slices
  → iDDS → ActiveMQ → Workers → Results → Control room
```

## Workflow Phases

### Phase 1: Run Imminent
```
PA → "run imminent" (run-id, worker count) → iDDS
  → Creates PanDA tasks + "adjust worker job count in batch slots" → Harvester
  → Submits pilots (staggered) → Start transformers (payloads) → Heartbeats and other communications
```
Harvester "fast launch" plugin provides immediate pilot deployment with staggered submission to control load during ramp-up.

### Phase 2: Run Running
```
FastMon → STF sample → PA
  → Creates TF slices (~15/sample), registers in DB
  → /queue/tf.slices → iDDS
  → Updates PanDA bookkeeping (clustered ~5sec)
  → Assigns to worker → /queue/panda.transformer.slices
Transformer → Consumes (prefetchsize=1, ack=client-individual)
  → Process with EICrecon (~30 sec)
  → /queue/panda.results (dual subscription: PA + iDDS)
```
Workers spend ~30 sec on each slice, then proceed to next slice assignment; new slices arrive ~0.5 Hz; dispatch is ActiveMQ-only (fast).

### Phase 3: Run End
```
PA → "run end" → /queue/tf.slices → iDDS
  → /topic/panda.transformer: broadcast "transformer end"
Transformers → Soft-ending mode (finish queue, then quit) → "ack worker end"
```
Soft-ending ensures no work is lost during graceful shutdown.

## Message Queue Architecture

### Queue Definitions

| Queue/Topic | Producer | Consumer | Purpose |
|-------------|----------|----------|---------|
| `/queue/tf.slices` | Processing Agent | iDDS | TF slice messages, run control ("run imminent", "run end") |
| `/queue/panda.transformer.slices` | iDDS | Transformers | Slice assignments with task-id header filtering |
| `/topic/panda.transformer` | iDDS | All Transformers | Broadcast control messages ("run end") |
| `/queue/panda.results` | Transformers | PA (sub1), iDDS (sub2) | Processing results and status updates |
| `/queue/panda.harvester` | iDDS | Harvester | Worker scaling requests ("adjust worker") |

### Consumer Configuration

**Transformers**: `prefetchsize=1, ack=client-individual, task_id_filter=True`
- Workers only receive work they can process immediately
- Unacknowledged messages return to queue on failure
- Header-based routing allows multiple tasks to share queues

**Dual Result Subscription**: `/queue/panda.results` → duplicated to `.sub1` (PA) and `.sub2` (iDDS)

## Component Responsibilities

### Processing Agent (PA)
- Receive STF sample notifications from FastMon
- Create TF slices (~15 per sample with TF offsets), register in testbed DB
- Message slice availability to iDDS via `/queue/tf.slices`
- Update slice status from `/queue/panda.results.sub1`, manage retries
- Aggregate results for control room consumers
- Run lifecycle: broadcast "run imminent" (config), track execution, "run end"

**TF Slice DB Schema**: `run_number, stf_id, stf_sample_id, tf_offset, status (queued/processing/success/fail/ignore), retries, metadata`

### iDDS
- Consume slice messages from `/queue/tf.slices`
- Update PanDA Event Service bookkeeping (clustered ~5sec batches)
- Select available workers, dispatch via `/queue/panda.transformer.slices`
- Consume results from `/queue/panda.results.sub2`, update PanDA
- Create PanDA tasks at run start, generate job specs
- Coordinate with Harvester for pilot lifecycle
- Handle automatic retry for failed/missing slices

### PanDA Event Service
TF slices map to ES "event ranges" - granular datums tracked independently:
- Continuous processing: workers consume stream without pre-assigned files
- Automatic retry on failure
- Fine-grained status tracking
- Bookkeeping can be clustered (10 slices over ~5sec) to reduce update frequency

### Pilot and Transformer
**Pilot**: Gets job spec, launches transformer, handles EICrecon data delivery, periodic status updates

**Transformer**: Message-aware payload wrapper
- Subscribes to `/queue/panda.transformer.slices` (task-id filter)
- Consumes slices, passes to EICrecon, publishes results, ACKs message
- Unacknowledged messages return to queue on failure

**EICrecon requirement**: Must process successive TF slices within same flow (slices not time-ordered between, but internally ordered)

### Harvester Fast Launch Plugin
- Immediate pilot deployment when run imminent (E1s are owned resources)
- Staggered submission over 5-10 min to control load
- Long-running workers (batch slot lifetime)
- Not essential for early testbed trials

## Performance and Scaling

**Target Metrics**: STF processing ~30 sec, control room latency 30-40 sec from beam collision

**Scaling**: At 0.5 Hz STF rate × 15 slices/sample × 30 sec/slice → ~225 workers needed for real-time processing (plus headroom)

**Tuning**: Worker count (PA), STF sampling rate (FastMon), slices/sample (PA), events/slice

**Message rates**: New slice assignments every ~30 sec per worker (ActiveMQ-based, much faster than traditional PanDA dispatch)

## Outputs

**Fast processing**: Aggregate statistics (histograms) → control room, no persistent files, no merge step

**Bulk prompt processing**: Traditional file-batch processing of complete STF files (Rucio-delivered) with relaxed latency, persistent outputs

Both workflows share batch resources and PanDA management for system coherence.

## Implementation Status

**Ready** (as of 2025-10):
- Message-based PanDA workflow, PanDA-Rucio integration
- FastMon infrastructure, DAQ simulator
- Monitoring system

**Required New Work**:
1. Harvester fast launch plugin (not essential for early trials)
2. Message-based slice dispatch (iDDS → transformer via ActiveMQ)
3. Transformer component in Pilot (message consumption, EICrecon integration, dual results)
4. PA slice management (TF slice creation, DB tracking, retry logic)
5. PanDA Event Service optimization (may use testbed DB initially)

## References

**Planning Documents**:
- [ePIC Fast Processing Workflow Plan](https://docs.google.com/document/d/16AqDgKhMezxjOmqXweEomCrGuQ4qMgbQm3gap-IPUtk/edit?tab=t.0#heading=h.f32v187jqcrd) - Narrative and requirements
- [PanDA/iDDS + Processing Agent Implementation](https://docs.google.com/document/d/1qa47kiqUlwV3_oO7bG7JPVDdy2a5FLpN/edit#heading=h.ez1a5kjg905c) - Technical design iterations

**Related**: [Architecture](architecture.md), [Workflows](workflows.md), [Operations](operations.md), [PanDA Event Service](https://panda-wms.readthedocs.io/en/latest/advanced/eventservice.html)

## Terminology

**Data**: STF files (2GB, ~0.5 Hz from DAQ) → STF samples (~5% via FastMon) → TF slices (~15/sample, ~30 sec processing)

**Components**: PA (Processing Agent), iDDS (workflow manager), ES (Event Service), Transformer (message-aware payload wrapper)

**Processing**: Fast (STF samples, ~30 sec, control room) vs Bulk Prompt (full STFs, minutes-hours, persistent outputs)
