# swf-testbed

This is the umbrella repository for the ePIC streaming workflow testbed.

## 🤖 For AI Assistants

**⚠️ CRITICAL: Read [AI Assistant Guidance](docs/AI-ASSISTANT-GUIDANCE.md) before making any changes to this repository.**

This document contains mandatory critical thinking requirements, coding rules, and architecture understanding that must be followed to avoid common failure patterns.

## Documentation Structure

### Release Notes
- [**Release Notes**](RELEASE_NOTES.md) - What's new in each version

### Getting Started
- [**Installation Guide**](docs/installation.md) - Complete setup instructions
- [**Architecture Overview**](docs/architecture.md) - System design and components

### Operations
- [**Running the Testbed**](docs/operations.md) - Starting, stopping, and monitoring services
- [**Workflow Orchestration**](docs/workflows.md) - Running and managing workflows
- [**Monitor Integration**](docs/monitor.md) - Web interface and API usage
- [**MCP Integration**](../swf-monitor/docs/MCP.md) - Model Context Protocol for LLM interaction
- [**SSE Real-Time Streaming**](docs/sse-streaming.md) - Remote workflow event monitoring via HTTPS
- [**Production Deployment**](../swf-monitor/docs/PRODUCTION_DEPLOYMENT.md) - Complete Apache production deployment guide

### MCP for Claude Code

This repository includes `.mcp.json` which automatically configures [Claude Code](https://claude.ai/code) to connect to the testbed's MCP service. When you open this project in Claude Code, the `swf-testbed` MCP server is available for natural language queries about system state, agents, workflows, and logs.

To manually add the MCP server:
```
/mcp add swf-testbed --transport http --url https://pandaserver02.sdcc.bnl.gov/swf-monitor/mcp/
```

### Development
- [**Development Guide**](docs/development.md) - Contributing and development workflow

## AI Assistant Usage

This modular structure is designed to help AI assistants:
- **Find specific information quickly** without parsing large documents
- **Understand focused topics** without information overload  
- **Provide accurate guidance** based on targeted documentation sections
- **Update documentation incrementally** without affecting unrelated sections

Each document focuses on a single concern and cross-references related topics.