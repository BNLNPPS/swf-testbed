# AI Memory - Cross-Session Dialogue Persistence

**Status: Experimental**

AI memory enables Claude Code to recall recent conversations across sessions.
When enabled, user prompts and assistant responses are recorded via hooks and
loaded into new sessions for continuity.

## How It Works

Claude Code [hooks](https://docs.anthropic.com/en/docs/claude-code/hooks) run
at session boundaries:

- **SessionStart**: Loads recent dialogue turns into the new session context
- **UserPromptSubmit**: Records each user prompt
- **Stop**: Records the assistant's last response

The hooks call the [tjai](https://etaverse.com/tjai/) REST API (`/api/dialog`)
to store and retrieve dialogue.

## Setup

### 1. Environment variables

Add to `~/.env` (or `~/.bashrc`):

```bash
export TJAI_API_KEY="your-api-key"
export TJAI_API_URL="https://etaverse.com/tjai"   # default if omitted
export TJAI_DIALOG_TURNS=20                        # number of turns to load; 0 = disabled
```

### 2. Install hook scripts

Copy the hooks from `tjrepo/computers/common/claude-hooks/` to `~/.claude/hooks/`:

```bash
mkdir -p ~/.claude/hooks
cp /data/wenauseic/github/tjrepo/computers/common/claude-hooks/*.py ~/.claude/hooks/
```

### 3. Configure Claude Code settings

Add hooks to your **global** `~/.claude/settings.json` (not project-level, so
they apply across all projects):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/load.py",
            "timeout": 10
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/record.py",
            "timeout": 10,
            "async": true
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/record.py",
            "timeout": 10,
            "async": true
          }
        ]
      }
    ]
  }
}
```

A complete reference settings file is at
`tjrepo/computers/common/claude-settings.json`.

## Disabling

Set `TJAI_DIALOG_TURNS=0` or unset it. The hooks exit immediately when
the variable is absent or zero.

## Files

| Location | Purpose |
|----------|---------|
| `~/.claude/hooks/load.py` | SessionStart hook - loads SYSPROMPT.md + recent dialogue |
| `~/.claude/hooks/record.py` | UserPromptSubmit/Stop hook - records exchanges |
| `~/.claude/hooks/SYSPROMPT.md` | Optional system prompt injected at session start |
| `tjrepo/computers/common/claude-hooks/` | Canonical source for hook scripts |
| `tjrepo/computers/common/claude-settings.json` | Reference settings with hooks configured |

## Troubleshooting

- **No dialogue loading?** Check `TJAI_DIALOG_TURNS` is set and > 0,
  and `TJAI_API_KEY` is set. Restart the session after changing env vars.
- **Hook errors?** Hooks print to stderr. Run manually to test:
  `echo '{"hook_event_name":"UserPromptSubmit","prompt":"test"}' | python3 ~/.claude/hooks/record.py`
