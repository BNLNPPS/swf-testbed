"""
AI Memory - Cross-session dialogue persistence for Claude Code.

This module provides hooks integration for recording and loading
AI dialogue history, enabling context continuity across sessions.

Opt-in: Set SWF_DIALOGUE_TURNS environment variable to enable.
- SWF_DIALOGUE_TURNS=20 (load last 20 conversation turns at session start)
- SWF_DIALOGUE_TURNS=0 or unset (disabled)

Components:
- record.py: Called by Claude Code hooks to record exchanges
- load.py: Called at session start to load recent dialogue
"""
