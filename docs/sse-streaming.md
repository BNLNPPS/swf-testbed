# Server-Sent Events (SSE) Real-Time Streaming

Real-time workflow message streaming for remote monitoring and visualization via HTTPS Server-Sent Events.

## Overview

The SWF Testbed provides real-time streaming of workflow messages to remote clients via REST Server-Sent Events (SSE). This enables distributed agents and external systems to receive live workflow updates without requiring direct ActiveMQ access or complex networking configurations.

**Important**: ActiveMQ message senders require no modifications. ALL messages sent to ActiveMQ are automatically available to SSE clients. Only receiving agents need SSE-specific configuration.

**Key Benefits:**
- **Firewall-friendly**: Uses standard HTTPS connections 
- **Real-time**: Sub-second latency for workflow messages
- **Scalable**: Supports multiple concurrent remote clients
- **Secure**: Token-based authentication with production TLS
- **Filtered**: Clients can subscribe to specific message types or workflows

## Architecture

```
Workflow Agents → ActiveMQ → Monitor → SSE Broadcaster → Remote Agents
     ↓              ↓           ↓           ↓              
  data-agent    epictopic   Database   Server-side    
processing-agent            Logging    Filtering      
  daq-simulator                                       
```

**Data Flow:**
1. **Workflow agents** send messages to ActiveMQ (normal operation)
2. **Monitor** consumes messages, stores in database, enriches with metadata  
3. **SSE Broadcaster** applies per-client filters and forwards only matching messages
4. **Remote clients** receive filtered real-time message streams over the network

## SSE Clients (Receivers)

### Remote SSE Receiver

The `remote_sse_receiver.py` script connects to the production monitor and displays workflow messages in real-time.

#### Prerequisites

```bash
export SWF_API_TOKEN="your-production-api-token"
export SWF_SSE_RECEIVER_NAME="descriptive-client-name"
```

**Important:** `SWF_SSE_RECEIVER_NAME` must be set to a descriptive, unique name that identifies your remote agent. This name will appear in the monitor's agent registry and workflow views.

#### Usage

```bash
# Basic usage (receives ALL messages)
cd /eic/u/wenauseic/github/swf-testbed
source .venv/bin/activate && source ~/.env
export SWF_SSE_RECEIVER_NAME="my-fastmon"
python example_agents/remote_sse_receiver.py

# Filter by message type
python example_agents/remote_sse_receiver.py --message sse_test

# Filter by multiple message types
python example_agents/remote_sse_receiver.py --message data_ready,processing_complete

# Filter by agent
python example_agents/remote_sse_receiver.py --agent sse_sender-agent

# Combine filters
python example_agents/remote_sse_receiver.py --message sse_test --agent sse_sender-agent
```

#### Features

- **Authentication**: Automatic token-based authentication
- **Auto-reconnection**: Handles network interruptions gracefully
- **Command-line filtering**: Filter by message types and agents via --message and --agent options
- **Agent registration**: Registers as active monitoring client
- **Real-time display**: Formatted message output with timestamps

#### Output Example

```
📡 Connecting to SSE stream: https://pandaserver02.sdcc.bnl.gov/swf-monitor/api/messages/stream/
🔌 Testing SSE endpoint...
✅ SSE stream opened - waiting for messages... (Ctrl+C to exit)
------------------------------------------------------------
[14:30:25] 🔗 Connected to SSE stream
[14:30:25] 📋 Client ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
[14:30:28] 📨 Message received:
            Type: stf_gen
            From: daq-simulator-agent
            Run:  run-2025-001
            File: stf_001.dat
------------------------------------------------------------
```

### Integration Requirements

SSE clients must:
1. **Set descriptive name**: `SWF_SSE_RECEIVER_NAME` environment variable
2. **Authenticate**: Valid `SWF_API_TOKEN` for production access
3. **Register as agent**: Inherit from `BaseAgent` to appear in monitor views and for robust connection handling

## Server-Side Filtering and Network Efficiency

### **How Filtering Works**

**ALL ActiveMQ messages** are processed by the SSE system, but **server-side filtering prevents unwanted messages from being sent over the network**.

#### Code Evidence:
1. **Every ActiveMQ message** triggers SSE processing:
   ```python
   # activemq_processor.py:158
   broadcaster.broadcast_message(enriched)
   ```

2. **Server applies filters BEFORE sending to clients**:
   ```python
   # sse_views.py:127
   if self._message_matches_filters(message_data, self.client_filters.get(client_id, {})):
       client_queue.put_nowait(message_data)  # Only filtered messages queued
   ```

3. **Filter implementation rejects unwanted messages**:
   ```python
   # sse_views.py:160-161
   if 'msg_types' in filters:
       if message.get('msg_type') not in filters['msg_types']:
           return False  # Message filtered out, NOT sent to client
   ```

### **Network Traffic Control**

- ✅ **No unnecessary network traffic**: Filtered messages never leave the server
- ✅ **Server-side filtering**: Applied before network transmission  
- ✅ **Per-client filtering**: Each client receives only matching messages

### **Filter Types and Examples**

#### Available Filters:
- `msg_types` - Filter by message type
- `agents` - Filter by sender agent (`processed_by` field)
- `run_ids` - Filter by workflow run ID

## Message Types and Content

SSE clients receive workflow messages (subject to their filters) with enriched metadata:

### Standard Workflow Messages
- `run_imminent` - New run about to start
- `start_run` - Run initialization complete
- `stf_gen` - New STF data file available  
- `data_ready` - Data processing ready
- `processing_complete` - Processing finished
- `pause_run` / `resume_run` - Run control
- `end_run` - Run completed

### Message Structure
```json
{
  "msg_type": "stf_gen",
  "processed_by": "daq-simulator-agent", 
  "run_id": "run-2025-001",
  "filename": "stf_001.dat",
  "message": "STF file generated",
  "sender_agent": "daq-simulator-agent",
  "recipient_agent": "data-agent",
  "queue_name": "epictopic",
  "sent_at": "2025-01-15T14:30:25.123Z"
}
```

### Test Messages
- `sse_test` - Connectivity and functionality testing

## Security and Authentication

### Production Authentication
SSE streaming requires valid API tokens:

```bash
# Get token from monitor admin
export SWF_API_TOKEN="your-token-here"
```

### Network Security
- **HTTPS only**: All SSE connections use TLS encryption
- **Token authentication**: No credentials in URLs or query parameters  
- **Firewall friendly**: Outbound HTTPS (port 443) only
- **No incoming connections**: Clients connect to monitor, not vice versa

## Deployment Considerations

### Monitor Requirements
- **Redis**: Required for multi-process SSE fanout in production
- **Apache configuration**: Proper headers for SSE streaming
- **Database storage**: All messages persisted for audit/replay

### Client Requirements  
- **Persistent connection**: SSE requires long-lived HTTPS connections
- **Reconnection logic**: Handle temporary network disruptions
- **Resource management**: Proper cleanup on shutdown
- **Agent registration**: Must appear in monitor's agent registry

### Scaling
- **Multiple clients**: Monitor supports concurrent SSE connections
- **Message filtering**: Clients can filter by message type, agent, or run
- **Latency**: Sub-second delivery for real-time monitoring

## Development and Testing

### Test Message Generation
Use `remote_sse_sender.py` to generate test messages:

```bash
# One-shot test batch
export SWF_SENDER_ONESHOT=1  
python example_agents/remote_sse_sender.py

# Continuous test messages (every 30s)
python example_agents/remote_sse_sender.py
```


## Troubleshooting

### Common Issues

**Connection Refused (ECONNREFUSED)**
- Check monitor URL and network connectivity
- Verify production monitor is running

**HTTP 401 Unauthorized**  
- Verify `SWF_API_TOKEN` is set and valid
- Check token hasn't expired


**Missing Agent Name Error**
```
❌ Error: SWF_SSE_RECEIVER_NAME must be set to a descriptive agent name
```
Set descriptive client identifier:
```bash
export SWF_SSE_RECEIVER_NAME="workflow-dashboard"
```

### Monitoring SSE Health
Check connected clients in monitor web interface:
- **System Agents**: View registered SSE receivers
- **Workflow Messages**: See message delivery status  
- **API Status**: `/api/messages/stream/status/` endpoint

---

For technical implementation details, see [Monitor SSE Documentation](../swf-monitor/docs/SSE_RELAY.md).