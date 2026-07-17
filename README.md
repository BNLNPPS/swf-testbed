# swf-testbed

This is the umbrella repository for the ePIC streaming workflow testbed: the streaming workflow
application of the swf platform. Its production peer is
[swf-epicprod](https://github.com/BNLNPPS/swf-epicprod); both ride the common platform in
[swf-monitor](https://github.com/BNLNPPS/swf-monitor) and
[swf-common-lib](https://github.com/BNLNPPS/swf-common-lib).

## Documentation

- [**ePIC WFMS Documentation**](https://epic-wfms-docs.readthedocs.io) - Official system-level documentation for the ePIC Workflow Management System, of which the testbed is the streaming implementation front

### Release Notes
- [**Release Notes**](RELEASE_NOTES.md) - What's new in each version

### Getting Started
- [**Installation Guide**](docs/installation.md) - Complete setup instructions
- [**Architecture Overview**](docs/architecture.md) - System design and components

### Operations
- [**Running the Testbed**](docs/operations.md) - Starting, stopping, and monitoring services
- [**Workflow Orchestration**](docs/workflows.md) - Running and managing workflows
- [**The E0-E1 Interface**](docs/e0-e1-interface.md) - The interface as understood in 2026: architecture, definitions, open questions, development path
- [**The E0-E1 State Machine**](docs/e0-e1-state-machine.md) - The datataking state model at the E0-E1 interface
- [**Monitor Integration**](docs/monitor.md) - Web interface and API usage
- [**MCP Integration**](../swf-monitor/docs/MCP.md) - Model Context Protocol for LLM interaction
- [**PCS (Physics Configuration System)**](../swf-epicprod/docs/PCS.md) - Production configuration and campaign records, in the [swf-epicprod](https://github.com/BNLNPPS/swf-epicprod) production domain
- [**SSE Real-Time Streaming**](docs/sse-streaming.md) - Remote workflow event monitoring via HTTPS
- [**Production Deployment**](../swf-monitor/docs/PRODUCTION_DEPLOYMENT.md) - Apache production deployment guide

### MCP for Claude Code

This repository includes `.mcp.json` which automatically configures [Claude Code](https://claude.ai/code) to connect to the testbed's MCP service. When you open this project in Claude Code, the `swf-testbed` MCP server is available for natural language queries about system state, agents, workflows, and logs.

**SSL Setup (required for BNL/SDCC servers):** Add to your `~/.bashrc`:
```bash
export NODE_EXTRA_CA_CERTS=/etc/pki/tls/certs/ca-bundle.crt
```

To manually add the MCP server:
```bash
claude mcp add --transport http swf-testbed https://pandaserver02.sdcc.bnl.gov/swf-monitor/mcp/
```

### Development
- [**Development Guide**](docs/development.md) - Contributing and development workflow
- [**AI Memory**](docs/ai-memory.md) - Cross-session dialogue persistence (experimental)

