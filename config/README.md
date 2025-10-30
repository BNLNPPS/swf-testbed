# Configuration Reference Files

System-level configuration files for the SWF testbed infrastructure.

## Files

### `broker.xml`

ActiveMQ Artemis broker configuration with fast processing workflow queues and diverts.

**Source**: `/var/lib/swfbroker/etc/broker.xml`

**Key Features**:
- 11 queue addresses for fast processing workflow
- 6 diverts for message duplication (dual-subscription pattern)
- Monitor observability: "Monitor sees all" principle
- Queues: panda.results, panda.transformer.slices, tf.slices, panda.harvester (with .sub1, .sub2, .monitor copies)

**Deployment**: Use `scripts/configure-artemis-fast-processing.sh` to apply configuration

**Last Updated**: 2025-10-30 (Artemis 2.41.0 configuration)

**Note**: This is a reference copy for version control and documentation. The live configuration is at `/var/lib/swfbroker/etc/broker.xml`.

## Usage

These files serve as:
- Reference documentation for system configuration
- Version control for infrastructure changes
- Disaster recovery baseline
- Template for other deployments
