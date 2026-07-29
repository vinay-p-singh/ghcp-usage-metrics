"""Shared constant strings used across the extractor.

Centralising these removes the scattered magic-string literals that previously
appeared in every scanner.
"""
from __future__ import annotations

# Composite-key separator for the per-agent×model dimension (``by_am``): the key
# is ``f"{agent}{AM_SEP}{model}"`` so one flat bucket can carry the 2-D split.
AM_SEP = "\x1f"

# Display agents.
AGENT_DEFAULT = "GitHub Copilot Chat"   # base VS Code chat + internal surfaces
AGENT_CLI = "Copilot CLI"               # all GitHub Copilot CLI activity
AGENT_CLAUDE = "Claude Code"            # all Claude Code activity

# Placeholder model for requests that were recorded without token data
# (CLI pre-telemetry turns, chatSessions activity-only days).
NO_TOKEN = "(no token data)"

# Label prefix a parent session uses for a runSubagent child log.
RUNSUBAGENT_PREFIX = "runSubagent-"
