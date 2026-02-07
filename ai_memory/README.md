# AI Memory - Cross-Session Context for Claude Code

This component enables AI dialogue persistence across Claude Code sessions.
When enabled, your conversations with Claude are recorded and loaded into
new sessions, providing continuity without manual re-explanation.

## How It Works

1. **Recording**: Claude Code hooks capture each exchange (user prompt + assistant response)
2. **Storage**: Exchanges are stored in the swf-testbed PostgreSQL database
3. **Loading**: At session start, recent dialogue is loaded into Claude's context

## Opt-In

Set the `SWF_DIALOGUE_TURNS` environment variable:

```bash
# Enable with 20 conversation turns (40 messages)
export SWF_DIALOGUE_TURNS=20

# Disable (default)
export SWF_DIALOGUE_TURNS=0
# or unset
```

Add to your shell profile (`.bashrc`, `.zshrc`) to persist.

## Setup

The hooks are configured in `.claude/settings.json`. They call the Python
scripts in this directory:

- `load.py` - Called at SessionStart, loads SYSPROMPT.md + recent dialogue
- `record.py` - Called at UserPromptSubmit and Stop, records exchanges

## Requirements

- swf-monitor must be running (provides the REST API)
- `SWF_MONITOR_HTTP_URL` environment variable (default: http://pandaserver02.sdcc.bnl.gov/swf-monitor)

## Privacy Notes

- Dialogue is stored in the shared swf-testbed database
- Only your username's dialogue is loaded into your sessions
- This is for swf-testbed project development only
- Don't enable for sensitive/private conversations

## Files

```
ai_memory/
├── __init__.py     # Package init
├── load.py         # SessionStart hook - loads context
├── record.py       # UserPromptSubmit/Stop hook - records exchanges
└── README.md       # This file
```

## Troubleshooting

**No dialogue loading?**
- Check `SWF_DIALOGUE_TURNS` is set and > 0
- Check swf-monitor is running
- Check hooks are configured in `.claude/settings.json`

**Errors in hooks?**
- Hooks run silently - check swf-monitor logs for API errors
- Test manually: `echo '{}' | python ai_memory/load.py`
