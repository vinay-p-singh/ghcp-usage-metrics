"""The quick-scan window: how a cold first open avoids a full log parse.

A complete scan reads hundreds of megabytes of request logs, so the first open
of the dashboard used to block on it. In quick mode only logs touched inside the
window are parsed; anything already memoised in the billing cache is free and
still included, and the rest is deferred to the full pass that follows in the
background.

The result is a deliberately PARTIAL report, flagged as such end to end so it is
never mistaken for the whole picture.
"""
from __future__ import annotations

import os
import time

from ghcp.diagnostics import DIAG

_STATE = {"cutoff": 0.0}   # epoch seconds; 0 = parse everything


def set_quick_window(days: int) -> None:
    """Restrict this run to logs modified within the last ``days`` (0 = full)."""
    _STATE["cutoff"] = time.time() - days * 86400 if days > 0 else 0.0
    DIAG["mode"] = "quick" if days > 0 else "full"
    DIAG["quick_days"] = max(days, 0)
    DIAG["partial"] = days > 0


def cutoff() -> float:
    """Epoch second before which uncached logs are deferred (0 = no window)."""
    return _STATE["cutoff"]


def in_window(path: str) -> bool:
    """True when ``path`` should be parsed in this pass."""
    limit = _STATE["cutoff"]
    if not limit:
        return True
    try:
        return os.stat(path).st_mtime >= limit
    except OSError:
        return False
