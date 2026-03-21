# Creating Custom Skills for Qwen Code and Claude Code

This guide shows you how to create custom skills for AI coding assistants (Qwen Code, Claude Code) to automate repetitive tasks with structured workflows.

---

## Table of Contents

- [What is a Skill?](#what-is-a-skill)
- [Directory Structure](#directory-structure)
- [Creating a Skill](#creating-a-skill)
- [Example: testbed-audit](#example-testbed-audit)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

---

## What is a Skill?

A **Skill** is a reusable instruction template that tells an AI assistant how to perform a specific task consistently. Skills are useful for:

- **Standardizing workflows** (e.g., testbed audits, health checks)
- **Enforcing constraints** (e.g., "use only this tool", "hardcode this parameter")
- **Providing templates** for consistent output formatting
- **Reducing prompt repetition** (trigger with keywords like "testbed audit")

---

## Directory Structure

### Qwen Code

```
~/.qwen/skills/
├── your-skill-name/
│   └── SKILL.md          # Skill definition (required)
└── another-skill/
    └── SKILL.md
```

### Claude Code

```
.your-project/.claude/skills/
├── your-skill-name/
│   └── SKILL.md          # Skill definition (required)
└── another-skill/
    └── SKILL.md
```

> **Note**: Qwen Code uses a global skills directory (`~/.qwen/skills/`), while Claude Code uses project-local skills (`.claude/skills/`).

---

## Creating a Skill

### Step 1: Create the Directory

```bash
# For Qwen Code (global)
mkdir -p ~/.qwen/skills/testbed-audit

# For Claude Code (project-local)
mkdir -p .claude/skills/testbed-audit
```

### Step 2: Create SKILL.md

Create a file named `SKILL.md` inside your skill directory. This file contains:

1. **Frontmatter** (YAML metadata between `---` delimiters)
2. **Instruction Body** (Markdown instructions for the AI)

### Step 3: Define Frontmatter

```yaml
---
name: testbed-audit
description: >
  MANDATORY: Use this skill for a detailed diagnostic audit of the 'test-zy'
  environment. Trigger this when the user asks for a "testbed audit",
  "agent report", "testbed health summary", or "is my testbed okay?".

  This skill provides structured heartbeat analysis for zyang2 that
  the default swf_get_testbed_status tool does not provide.
---
```

**Frontmatter Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `name` | ✅ | Unique skill identifier (use hyphens, lowercase) |
| `description` | ✅ | When to use this skill; trigger keywords |

### Step 4: Write Instructions

The instruction body should include:

- **Role**: What role the AI should adopt
- **Rules**: Strict constraints the AI must follow
- **Steps**: Sequential actions to perform
- **Template**: Output format to use
- **Error Handling**: What to do on failure

---

## Example: testbed-audit

Here's the complete `testbed-audit` skill as a reference:

```markdown
---
name: testbed-audit
description: >
  MANDATORY: Use this skill for a detailed diagnostic audit of the 'test-zy'
  environment. Trigger this when the user asks for a "testbed audit",
  "agent report", "testbed health summary", or "is my testbed okay?".

  This skill provides structured heartbeat analysis for zyang2 that
  the default swf_get_testbed_status tool does not provide.
---

# zyang2 Testbed Health Audit

## Role
You are a Diagnostic Auditor. Your goal is to fetch raw agent data,
analyze it for 'zyang2' in the 'test-zy' namespace, and present a
finalized health report.

## Strict Rules
1. **Primary Tool**: Use `swf_list_agents` ONLY.
2. **Namespace**: Hardcode `namespace: "test-zy"`.
3. **Exclusion**: Do NOT call `swf_get_testbed_status`.
4. **Iteration**: Exactly ONE tool call total.
5. **Finality**: Stop immediately after printing the report.

## Steps
1. **Data Acquisition**: Call `swf_list_agents` with parameters:
   - `status`: "OK"
   - `namespace`: "test-zy"
2. **Analysis**: Check the `last_heartbeat` for every agent found.
3. **Reporting**: Render the findings using the Audit Template below.

## Audit Template
**Namespace**: test-zy | **User**: zyang2

**Agent Status Matrix**:
1. [agent-name] — [__state__] ([role])
2. ...

**Heartbeat Analysis**: [fresh / stale]

> **Auditor Note**: [Only add "Action Required" if an agent is NOT in 'READY' state]

## Error Handling
- If `swf_list_agents` fails: Print `⚠ Audit Failed: [error]` and stop.

[DONE — no further tool calls]
```

### How to Use

Once installed, trigger the skill by saying:

- "Run a testbed audit"
- "Check testbed health"
- "Is my testbed okay?"
- "Show me agent status"

The AI will automatically use the skill and produce a standardized report.

### Example Output

Here's a real example of what the `testbed-audit` skill produces:

```
# Testbed Health Audit

**Namespace**: test-zy | **User**: zyang2

## Agent Status Matrix

### Active Agents (OK status, READY state):
1. **data-agent-zyang2-1202** — READY (DATA) — Heartbeat: 2026-03-20 18:47:57 UTC
2. **agent-manager-zyang2** — READY (agent_manager) — Heartbeat: 2026-03-20 18:47:38 UTC
3. **processing-agent-zyang2-1201** — READY (PROCESSING) — Heartbeat: 2026-03-20 18:47:04 UTC
4. **daq_simulator-agent-zyang2-1199** — READY (DAQ_Simulator) — Heartbeat: 2026-03-20 18:47:04 UTC

### Inactive Agents (EXITED or WARNING):
- **382 additional agents** in EXITED status (dating from Feb 22 to Mar 17, 2026)
- **6 agents** with WARNING status (all EXITED operational state)

## Heartbeat Analysis

**Active Agents**: ✅ **FRESH** — All 4 active agents have heartbeats within the last ~45 seconds (as of 18:47:57 UTC)

**Inactive Agents**: ⚠️ **STALE** — Heartbeats range from 3 days to 26 days old

## Summary

| Status | Count |
|--------|-------|
| OK/READY | 4 |
| EXITED | 376+ |
| WARNING | 6+ |

**System Health**: ✅ **HEALTHY** — Core workflow agents (DAQ Simulator, Data Agent, Processing Agent, and Agent Manager) are all running and responsive.

---

*Note: The large number of EXITED agents is normal — these are historical agent instances from previous testbed runs. They don't impact current operations.*
```

This shows how the skill's template produces consistent, well-formatted output every time.

---

## Best Practices

### 1. Clear Trigger Keywords

In the `description`, list all the phrases that should trigger this skill:

```yaml
description: >
  Use this when the user asks for "X", "Y", or "Z".
```

### 2. Explicit Constraints

Use numbered rules with bold labels:

```markdown
## Strict Rules
1. **Primary Tool**: Use `tool_name` ONLY.
2. **Parameter**: Hardcode `param: "value"`.
3. **Exclusion**: Do NOT call `other_tool`.
```

### 3. Structured Output Templates

Provide a template for consistent output:

```markdown
## Output Template
**Field 1**: [value]
**Field 2**: [value]

**Summary**: [analysis]
```

### 4. Error Handling

Tell the AI what to do on failure:

```markdown
## Error Handling
- If `tool_call` fails: Print `⚠ Error: [message]` and stop.
```

### 5. Termination Marker

Indicate when the skill is complete:

```markdown
[DONE — no further tool calls]
```

This prevents the AI from continuing unnecessarily.

---

## More Examples

### Simple Status Check (Claude Code Style)

```markdown
# /testbed-status

Get comprehensive testbed status for username zyang2 using the MCP tool.

## MCP Call

```
{{MCP|swf-testbed|mcp__swf-testbed__swf_get_testbed_status|username=zyang2}}
```

## Parameters

- `username`: zyang2 (fixed for this skill)
```

This simpler format is useful for straightforward tool invocations.

---

## Skill Templates

### Template 1: Diagnostic Skill

```markdown
---
name: diagnostic-name
description: >
  Use this when the user asks for [trigger phrases].
  This skill provides [unique value] that default tools don't offer.
---

# [Diagnostic Name]

## Role
You are a [Role Name]. Your goal is to [objective].

## Strict Rules
1. **Primary Tool**: Use `tool_name` ONLY.
2. **Parameters**: Hardcode `param: "value"`.
3. **Exclusion**: Do NOT call `other_tool`.
4. **Iteration**: Exactly N tool call(s) total.
5. **Finality**: Stop immediately after [action].

## Steps
1. **Step Name**: Call `tool` with parameters:
   - `param1`: "value1"
   - `param2`: "value2"
2. **Analysis**: [What to analyze]
3. **Reporting**: Render findings using the template below.

## Output Template
**Header**: [format]

**Details**:
1. [item format]
2. ...

**Summary**: [analysis guidance]

## Error Handling
- If `tool` fails: Print `⚠ Error: [message]` and stop.

[DONE — no further tool calls]
```

### Template 2: Tool Invocation Skill

```markdown
# /tool-name

Brief description of what this skill does.

## MCP Call

```
{{MCP|provider|tool_function|param1=value1}}
```

## Parameters

- `param1`: description (fixed/default value)
```

---

## Troubleshooting

### Skill Not Triggering

**Problem**: The AI doesn't use your skill when expected.

**Solutions**:
1. Check that trigger keywords are in the `description` field
2. Ensure the skill name is descriptive and unique
3. Restart the AI session to reload skills

### Skill Produces Wrong Output

**Problem**: The AI doesn't follow the template.

**Solutions**:
1. Make the template more explicit with placeholders like `[value]`
2. Add "Strict Rules" section with numbered constraints
3. Include an example output in the skill

### Tool Call Fails

**Problem**: The MCP tool call fails.

**Solutions**:
1. Verify the tool name is correct (check `swf_list_available_tools`)
2. Ensure all required parameters are provided
3. Add error handling instructions to the skill

---

## Additional Resources

- **Qwen Code Skills**: `~/.qwen/skills/` directory
- **Claude Code Skills**: `.claude/skills/` in your project
- **Available MCP Tools**: Use `swf_list_available_tools` to discover tools
- **MCP Server**: https://pandaserver02.sdcc.bnl.gov/swf-monitor/mcp/

---

## Quick Reference

| Component | Purpose |
|-----------|---------|
| `SKILL.md` | Skill definition file (required) |
| Frontmatter (`---`) | Metadata: name, description |
| Role Section | Defines AI's persona/objective |
| Strict Rules | Hard constraints the AI must follow |
| Steps | Sequential actions to perform |
| Template | Output format for consistency |
| Error Handling | Failure recovery instructions |
| `[DONE]` | Termination marker |

---
