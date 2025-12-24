# Artemis Queue Configuration Guide

How to modify ActiveMQ Artemis queue configurations on pandaserver02.

## Configuration File

```
/var/lib/swfbroker/etc/broker.xml
```

## Routing Types

Artemis has two routing types:

| Type | Behavior | Use Case |
|------|----------|----------|
| **anycast** | Load-balanced (one consumer gets each message) | Work queues, worker pools |
| **multicast** | Fanout (all consumers get every message) | Broadcast topics, monitoring |

## Clean Modification Procedure

### 1. Backup Current Config

```bash
sudo cp /var/lib/swfbroker/etc/broker.xml \
    /var/lib/swfbroker/etc/broker.xml.backup.$(date +%Y%m%d_%H%M%S)
```

### 2. Edit Configuration

```bash
sudo vi /var/lib/swfbroker/etc/broker.xml
```

**Example: Anycast queue (workers compete)**
```xml
<address name="/queue/panda.transformer.slices">
  <anycast>
    <queue name="/queue/panda.transformer.slices" />
  </anycast>
</address>
```

**Example: Multicast topic (broadcast)**
```xml
<address name="epictopic">
  <multicast />
</address>
```

**Example: Divert (copy messages to another address)**
```xml
<diverts>
  <divert name="transformer-slices-monitor-divert">
    <address>/queue/panda.transformer.slices</address>
    <forwarding-address>/topic/panda.transformer.slices.monitor</forwarding-address>
    <exclusive>false</exclusive>  <!-- false = copy, true = move -->
  </divert>
</diverts>
```

### 3. Clear Old Bindings (Required When Changing Routing Types)

When changing an address from multicast to anycast (or vice versa), Artemis's persistent bindings will conflict with the new config. You must clear them:

```bash
sudo systemctl stop artemis.service
sleep 2
sudo rm -f /var/lib/swfbroker/data/bindings/*.bindings
```

**Warning:** This clears all queue bindings. Any pending messages in queues will be lost. Only do this on development systems or when queues are empty.

### 4. Restart Artemis

```bash
sudo systemctl start artemis.service
sleep 5
```

### 5. Verify Configuration

Check startup logs for errors:
```bash
sudo journalctl -u artemis.service --since "1 minute ago" | grep -E 'error|warn|ANYCAST|MULTICAST|divert'
```

Verify server is active:
```bash
sudo journalctl -u artemis.service --since "1 minute ago" | grep "AMQ221007"
# Should show: "Server is now active"
```

Check system status:
```bash
cd /eic/u/wenauseic/github/swf-testbed && source .venv/bin/activate && source ~/.env
python report_system_status.py
```

## Current Queue Layout (as of 2025-12-23)

| Address | Routing | Purpose |
|---------|---------|---------|
| `epicqueue` | anycast | General work queue |
| `epictopic` | multicast | Workflow broadcast (run_imminent, stf_gen, etc.) |
| `/queue/panda.transformer.slices` | anycast | TF slice work queue (workers compete) |
| `/topic/panda.transformer.slices.monitor` | multicast | Monitor receives copy of all slices |
| `/topic/panda.results` | multicast | Processing results |
| `/topic/panda.transformer` | multicast | Transformer events |
| `/topic/tf.slices` | multicast | TF slice events |
| `/topic/panda.harvester` | multicast | Harvester events |

## Troubleshooting

### "Queue already exists on address" Error

This means old bindings conflict with new config. Solution:
```bash
sudo systemctl stop artemis.service
sudo rm -f /var/lib/swfbroker/data/bindings/*.bindings
sudo systemctl start artemis.service
```

### Artemis Won't Start

Check for XML syntax errors:
```bash
xmllint --noout /var/lib/swfbroker/etc/broker.xml
```

Check full error logs:
```bash
sudo journalctl -u artemis.service -n 50
```

### Restore from Backup

```bash
sudo systemctl stop artemis.service
sudo cp /var/lib/swfbroker/etc/broker.xml.backup.YYYYMMDD_HHMMSS \
    /var/lib/swfbroker/etc/broker.xml
sudo rm -f /var/lib/swfbroker/data/bindings/*.bindings
sudo systemctl start artemis.service
```

## Reference

- Artemis Address Model: https://activemq.apache.org/components/artemis/documentation/latest/address-model.html
- Diverts: https://activemq.apache.org/components/artemis/documentation/latest/diverts.html
- Colleague's setup guide: https://github.com/wguanicedew/documents/blob/main/artemis/configure.md
