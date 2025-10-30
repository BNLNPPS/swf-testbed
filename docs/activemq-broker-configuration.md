# ActiveMQ Artemis Broker Configuration

System-level broker configuration for the SWF testbed fast processing workflow.

## Overview

The fast processing workflow requires point-to-point queue messaging with message duplication for multiple consumers. This is implemented using ActiveMQ Artemis **queues** and **diverts**.

**Principle**: Monitor sees all - The monitor observes all fast processing workflow queues for complete visibility.

## Architecture

### Message Flow Patterns

**Queue (Point-to-Point)**: Each message consumed by exactly one worker
- Worker slice assignments
- Results with dual consumption (PA + iDDS)
- Coordinator communications

**Topic (Broadcast)**: All subscribers receive all messages
- Control messages (run end)
- Workflow events

**Diverts (Message Duplication)**: Automatically copy messages to multiple queues
- Results → sub1 (PA), sub2 (iDDS), monitor
- All queues → monitor copies for observability

## Configuration

### Automated Setup

**Script**: `swf-testbed/scripts/configure-artemis-fast-processing.sh`

```bash
sudo /path/to/swf-testbed/scripts/configure-artemis-fast-processing.sh
```

**What it does:**
- Creates timestamped backup of broker.xml
- Adds 11 queue addresses for fast processing workflow
- Adds 6 diverts for message duplication
- Validates XML syntax
- Restarts Artemis service
- Auto-rollback on failure

**Reference Configuration**: A complete broker.xml with all fast processing configuration is maintained at `swf-testbed/config/broker.xml` for version control and documentation.

### Queue Addresses

Added to `/var/lib/swfbroker/etc/broker.xml` in `<addresses>` section:

```xml
<!-- Fast processing workflow queues -->
<address name="panda.results">
  <anycast>
    <queue name="panda.results" />
  </anycast>
</address>

<address name="panda.results.sub1">
  <anycast>
    <queue name="panda.results.sub1" />
  </anycast>
</address>

<address name="panda.results.sub2">
  <anycast>
    <queue name="panda.results.sub2" />
  </anycast>
</address>

<address name="panda.results.monitor">
  <anycast>
    <queue name="panda.results.monitor" />
  </anycast>
</address>

<address name="panda.transformer.slices">
  <anycast>
    <queue name="panda.transformer.slices" />
  </anycast>
</address>

<address name="panda.transformer.slices.monitor">
  <anycast>
    <queue name="panda.transformer.slices.monitor" />
  </anycast>
</address>

<address name="panda.transformer">
  <multicast />
</address>

<address name="tf.slices">
  <anycast>
    <queue name="tf.slices" />
  </anycast>
</address>

<address name="tf.slices.monitor">
  <anycast>
    <queue name="tf.slices.monitor" />
  </anycast>
</address>

<address name="panda.harvester">
  <anycast>
    <queue name="panda.harvester" />
  </anycast>
</address>

<address name="panda.harvester.monitor">
  <anycast>
    <queue name="panda.harvester.monitor" />
  </anycast>
</address>
```

### Diverts (Message Duplication)

Added after `</addresses>` but before `</core>`:

```xml
<!-- Diverts for dual-subscription pattern + monitor observability -->
<!-- Principle: Monitor sees all -->
<diverts>
  <!-- Results queue: PA, iDDS, and Monitor -->
  <divert name="results-to-sub1">
    <address>panda.results</address>
    <forwarding-address>panda.results.sub1</forwarding-address>
    <exclusive>false</exclusive>
  </divert>

  <divert name="results-to-sub2">
    <address>panda.results</address>
    <forwarding-address>panda.results.sub2</forwarding-address>
    <exclusive>false</exclusive>
  </divert>

  <divert name="results-to-monitor">
    <address>panda.results</address>
    <forwarding-address>panda.results.monitor</forwarding-address>
    <exclusive>false</exclusive>
  </divert>

  <!-- TF slices queue: iDDS and Monitor -->
  <divert name="tf-slices-to-monitor">
    <address>tf.slices</address>
    <forwarding-address>tf.slices.monitor</forwarding-address>
    <exclusive>false</exclusive>
  </divert>

  <!-- Transformer slices queue: Workers and Monitor -->
  <divert name="transformer-slices-to-monitor">
    <address>panda.transformer.slices</address>
    <forwarding-address>panda.transformer.slices.monitor</forwarding-address>
    <exclusive>false</exclusive>
  </divert>

  <!-- Harvester queue: Harvester and Monitor -->
  <divert name="harvester-to-monitor">
    <address>panda.harvester</address>
    <forwarding-address>panda.harvester.monitor</forwarding-address>
    <exclusive>false</exclusive>
  </divert>
</diverts>
```

## Queue Purpose Reference

### Primary Queues

| Queue | Type | Purpose | Producers | Consumers |
|-------|------|---------|-----------|-----------|
| `panda.results` | anycast | Worker results (duplicated) | Workers | (diverted to sub1, sub2, monitor) |
| `panda.results.sub1` | anycast | PA results consumer | (divert) | Processing Agent |
| `panda.results.sub2` | anycast | iDDS results consumer | (divert) | iDDS |
| `panda.results.monitor` | anycast | Monitor observer | (divert) | Monitor |
| `tf.slices` | anycast | TF slice notifications | PA | iDDS, Monitor |
| `panda.transformer.slices` | anycast | Worker slice assignments | iDDS | Workers, Monitor |
| `panda.harvester` | anycast | Worker scaling commands | iDDS | Harvester, Monitor |

### Topics

| Topic | Type | Purpose | Producers | Consumers |
|-------|------|---------|-----------|-----------|
| `panda.transformer` | multicast | Control messages (broadcast) | iDDS | All workers |

### Monitor Queues

All monitor queues receive **copies** via diverts for observability:

- `panda.results.monitor` - Sees all worker results
- `tf.slices.monitor` - Sees all TF slice creation
- `panda.transformer.slices.monitor` - Sees all worker assignments
- `panda.harvester.monitor` - Sees all harvester commands

**Complete workflow visibility** for monitoring, debugging, and metrics.

## Divert Behavior

**`exclusive=false`**: Message is **copied**, not moved
- Original message stays in source queue
- Copy sent to forwarding address
- Multiple diverts can copy the same message

**Example: Results Message Flow**
```
Worker → /queue/panda.results
  ↓ (diverts duplicate)
  ├→ /queue/panda.results.sub1 (PA consumes)
  ├→ /queue/panda.results.sub2 (iDDS consumes)
  └→ /queue/panda.results.monitor (Monitor observes)
```

## Verification

### Check Artemis Status

```bash
sudo systemctl status artemis.service
sudo journalctl -u artemis.service -n 50
```

### Check Configuration Applied

```bash
grep "panda.results" /var/lib/swfbroker/etc/broker.xml
grep "diverts" /var/lib/swfbroker/etc/broker.xml
```

### Test Queue Messaging

```bash
# Terminal 1: Worker
cd swf-testbed
source .venv/bin/activate && source ~/.env
python ../swf-common-lib/code-samples/mq/queue_worker_example.py task-12345

# Terminal 2: Dispatcher
python ../swf-common-lib/code-samples/mq/queue_dispatcher_example.py task-12345
```

**Expected**: Worker processes 5 slices, dispatcher receives 5 results via sub2.

## Rollback

If issues occur, restore backup:

```bash
# List available backups
ls -lt /var/lib/swfbroker/etc/broker.xml.backup.*

# Restore specific backup
sudo cp /var/lib/swfbroker/etc/broker.xml.backup.YYYYMMDD_HHMMSS /var/lib/swfbroker/etc/broker.xml
sudo systemctl restart artemis.service
```

## Troubleshooting

### Artemis Won't Start

Check logs for XML syntax errors:
```bash
sudo journalctl -u artemis.service -n 100
```

Validate XML manually:
```bash
xmllint --noout /var/lib/swfbroker/etc/broker.xml
```

### Messages Not Being Diverted

Check divert names match address names exactly (case-sensitive).

Verify diverts are active:
```bash
# Check Artemis web console or use artemis CLI
/opt/artemis/bin/artemis address show --url tcp://localhost:61616
```

### Queue Not Found Errors

Queues are auto-created by Artemis when first used if `auto-create-queues=true` in address settings (default). Manual creation not required.

## References

- [ActiveMQ Artemis Diverts Documentation](https://activemq.apache.org/components/artemis/documentation/latest/diverts.html)
- [Fast Processing Workflow](fast-processing.md)
- [Queue Messaging Examples](../swf-common-lib/code-samples/mq/README-queue-messaging.md)

## Change History

- **2025-10-30**: Initial configuration for fast processing workflow
  - Added 11 queue addresses
  - Added 6 diverts for dual-subscription + monitor observability
  - Established "monitor sees all" principle
