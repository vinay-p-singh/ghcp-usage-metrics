"""Value normalisation: dates, agent names and model names."""
from __future__ import annotations

import datetime
import os

from ghcp.constants import AGENT_DEFAULT


def _utc_date_ms(ts: float) -> str:
    return datetime.datetime.fromtimestamp(
        ts / 1000, datetime.timezone.utc).strftime("%Y-%m-%d")


def _any_date(v) -> str | None:
    """UTC date from an epoch-ms number or an ISO-8601 string; else None.

    An offset-bearing string is converted rather than sliced: 2026-05-02T02:30+05:30
    is the UTC day 2026-05-01, and slicing would file it a day late. A string
    carrying no offset is sliced as written -- guessing a zone would be estimation.
    """
    if isinstance(v, (int, float)):
        try:
            return _utc_date_ms(v)
        except Exception:
            return None
    if isinstance(v, str) and len(v) >= 10 and v[:4].isdigit():
        try:
            dt = datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return v[:10]
        if dt.tzinfo is None:
            return v[:10]
        return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d")
    return None


def _date_of_path(path: str) -> str:
    try:
        return datetime.datetime.fromtimestamp(
            os.stat(path).st_mtime, datetime.timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return "1970-01-01"


_INTERNAL_AGENTS = {"panel/editagent", "summarizeconversationhistory",
                    "summarizevirtualtools", "searchsubagenttool", "copilotcli",
                    "default"}


def _norm_agent(name) -> str:
    """session-store agent_name -> display agent. Internal surfaces collapse to
    the base chat agent; genuine (sub)agents keep their name."""
    if not name:
        return AGENT_DEFAULT
    low = str(name).lower()
    if low in _INTERNAL_AGENTS or low.startswith("panel/") or low.startswith("retry-") or "summarize" in low:
        return AGENT_DEFAULT
    return str(name)


def _norm_model(model: str) -> str:
    """Normalise a chatSessions modelId ('copilot/claude-opus-4.8') to the bare
    name debug-logs use ('claude-opus-4.8').

    Raises on a missing name rather than inventing one: a request attributed to
    a model nobody chose is worse than a request we are told we could not read.
    """
    if not model:
        raise ValueError("request carries no model name")
    m = str(model)
    return m.split("/", 1)[1] if m.startswith("copilot/") else m
