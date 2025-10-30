# SWF Testbed Administration Scripts

System-level administration and deployment scripts for the testbed infrastructure.

## Scripts

### `configure-artemis-fast-processing.sh`

Configures ActiveMQ Artemis broker for fast processing workflow queue-based messaging.

**Usage:**
```bash
sudo ./configure-artemis-fast-processing.sh
```

**What it does:**
- Adds fast processing workflow queue addresses
- Configures message diverts for dual-subscription pattern
- Implements "monitor sees all" observability
- Creates automatic backup before changes
- Validates configuration and auto-rollback on failure

**See also:** [ActiveMQ Broker Configuration](../docs/activemq-broker-configuration.md)

## Requirements

All scripts require:
- Root/sudo access for system-level configuration
- ActiveMQ Artemis service installed and running
- xmllint for XML validation (usually pre-installed)

## Safety Features

All scripts include:
- Automatic backup creation with timestamps
- Configuration validation before applying
- Auto-rollback on failure
- Service health verification
- Clear success/failure reporting
