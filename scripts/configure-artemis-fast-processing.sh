#!/bin/bash
################################################################################
# Configure ActiveMQ Artemis Broker for Fast Processing Workflow
# Principle: Monitor sees all
################################################################################

set -e  # Exit on error

BROKER_XML="/var/lib/swfbroker/etc/broker.xml"
BACKUP_XML="${BROKER_XML}.backup.$(date +%Y%m%d_%H%M%S)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================================================="
echo "ActiveMQ Artemis Broker Configuration for Fast Processing Workflow"
echo "=========================================================================="

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}ERROR: This script must be run as root (use sudo)${NC}"
   exit 1
fi

# Check if broker.xml exists
if [[ ! -f "$BROKER_XML" ]]; then
    echo -e "${RED}ERROR: Broker config not found: $BROKER_XML${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 1: Creating backup...${NC}"
cp "$BROKER_XML" "$BACKUP_XML"
echo -e "${GREEN}✓ Backup created: $BACKUP_XML${NC}"

# Check if already configured
if grep -q "panda.results" "$BROKER_XML"; then
    echo -e "${YELLOW}WARNING: Fast processing queues already exist in config${NC}"
    read -p "Do you want to continue and overwrite? (yes/no): " confirm
    if [[ "$confirm" != "yes" ]]; then
        echo "Aborted by user"
        exit 0
    fi
    # Remove old configuration if present
    sed -i '/<!-- Fast processing workflow queues -->/,/<!-- \/Fast processing workflow queues -->/d' "$BROKER_XML"
    sed -i '/<!-- Diverts for dual-subscription pattern/,/<\/diverts>/d' "$BROKER_XML"
fi

echo -e "${YELLOW}Step 2: Adding queue addresses...${NC}"

# Create temporary file with new addresses
cat > /tmp/new-addresses.xml << 'ADDRESSES_EOF'

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
        <!-- /Fast processing workflow queues -->
ADDRESSES_EOF

# Insert addresses before </addresses>
sed -i '/<\/addresses>/e cat /tmp/new-addresses.xml' "$BROKER_XML"
echo -e "${GREEN}✓ Queue addresses added${NC}"

echo -e "${YELLOW}Step 3: Adding diverts...${NC}"

# Create temporary file with diverts
cat > /tmp/new-diverts.xml << 'DIVERTS_EOF'

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
DIVERTS_EOF

# Insert diverts after </addresses> but before </core>
sed -i '/<\/addresses>/r /tmp/new-diverts.xml' "$BROKER_XML"
echo -e "${GREEN}✓ Diverts added${NC}"

# Cleanup temp files
rm -f /tmp/new-addresses.xml /tmp/new-diverts.xml

echo -e "${YELLOW}Step 4: Validating XML syntax...${NC}"
if xmllint --noout "$BROKER_XML" 2>/dev/null; then
    echo -e "${GREEN}✓ XML syntax valid${NC}"
else
    echo -e "${RED}ERROR: XML syntax validation failed${NC}"
    echo -e "${YELLOW}Restoring backup...${NC}"
    cp "$BACKUP_XML" "$BROKER_XML"
    echo -e "${GREEN}✓ Backup restored${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 5: Restarting Artemis service...${NC}"
systemctl restart artemis.service

# Wait for service to start
sleep 3

echo -e "${YELLOW}Step 6: Verifying service status...${NC}"
if systemctl is-active --quiet artemis.service; then
    echo -e "${GREEN}✓ Artemis service is running${NC}"
else
    echo -e "${RED}ERROR: Artemis service failed to start${NC}"
    echo -e "${YELLOW}Restoring backup...${NC}"
    cp "$BACKUP_XML" "$BROKER_XML"
    systemctl restart artemis.service
    echo -e "${GREEN}✓ Backup restored and service restarted${NC}"
    echo ""
    echo "Check logs: sudo journalctl -u artemis.service -n 50"
    exit 1
fi

echo ""
echo "=========================================================================="
echo -e "${GREEN}SUCCESS: Fast processing workflow configuration applied${NC}"
echo "=========================================================================="
echo ""
echo "Configuration Summary:"
echo "  ✓ 11 new queue addresses created"
echo "  ✓ 6 diverts configured for message duplication"
echo "  ✓ Monitor observability: ALL queues"
echo "  ✓ Artemis service restarted successfully"
echo ""
echo "Backup saved to: $BACKUP_XML"
echo ""
echo "Next steps:"
echo "  1. Test queue messaging:"
echo "     python ../swf-common-lib/code-samples/mq/queue_worker_example.py task-12345"
echo "     python ../swf-common-lib/code-samples/mq/queue_dispatcher_example.py task-12345"
echo ""
echo "  2. View Artemis logs:"
echo "     sudo journalctl -u artemis.service -f"
echo ""
echo "To rollback: sudo cp $BACKUP_XML $BROKER_XML && sudo systemctl restart artemis.service"
echo "=========================================================================="
