"""What one extraction run actually saw, skipped and failed on.

Without this record the failure modes are indistinguishable: a rotated log, an
unreadable file, and a source that never stored token counts all look exactly
like "this project had no usage". Every scanner reports into ``DIAG``, and the
dashboard's Diagnostics tab renders it.

``DIAG`` is mutated in place, never rebound, so a module that imported it keeps
seeing the live record.
"""
from __future__ import annotations

import contextlib
import datetime
import sys

from ghcp.constants import NO_TOKEN

DIAG: dict = {}
ERR_CAP = 40

SOURCE_LABELS = {
    "vscode_ws": "VS Code workspaces (workspace.json)",
    "vscode_debug": "VS Code request logs (debug-logs/main.jsonl)",
    "vscode_chat": "VS Code saved sessions (chatSessions)",
    "cli": "Copilot CLI session store (~/.copilot/session-store.db)",
    "claude": "Claude Code sessions (~/.claude/projects)",
}

SOURCES = ("auto", "debug", "sessions")

NO_TOKEN_REASON = {
    "cli": "Copilot CLI stored no per-request tokens before its billing telemetry "
           "began. These requests were recovered from the session store's `turns` "
           "table \u2014 the call really happened, its size was never written down.",
    "vscode": "VS Code trimmed the request bodies out of these saved sessions. Only "
              "the session's activity day survived, so the request is real but "
              "carries no token payload.",
    "claude": "Claude Code records tokens but never GitHub AI credits.",
}


def diag_reset() -> None:
    """Start a fresh diagnostics record for one extraction run."""
    DIAG.clear()
    DIAG.update({
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "mode": "full",
        "quick_days": 0,
        "partial": False,
        "elapsed": {},
        "sources": {},
        "errors": [],
        "coverage": {},
        "no_token_rows": [],
        "source": _blank_source(),
    })


def _blank_source() -> dict:
    return {"requested": "auto", "effective": "auto",
            "debug_sessions": 0, "chat_credit_first": None,
            "sessions_from_saved": 0}


def source_rec() -> dict:
    """Which VS Code store this run read, and what that costs the reader."""
    return DIAG.setdefault("source", _blank_source())


def note_source(requested: str) -> None:
    rec = source_rec()
    rec["requested"] = requested if requested in SOURCES else "auto"
    rec["effective"] = rec["requested"]


def note_debug_session() -> None:
    source_rec()["debug_sessions"] += 1


def note_store_swap() -> None:
    """A session whose saved copy had kept more than its request log.

    Worth counting rather than doing silently: it is the measure of how much
    the request logs have rotated away.
    """
    source_rec()["sessions_from_saved"] += 1


def note_chat_credit(date: str) -> None:
    """Earliest day a saved session carried a credit figure of its own.

    VS Code only started writing one part-way through the tool's history, so a
    sessions-only report is complete on tokens and truncated on credits. The
    boundary is evidence in the logs, so it is measured here rather than being
    written down as a constant that quietly goes stale.
    """
    rec = source_rec()
    if not rec["chat_credit_first"] or date < rec["chat_credit_first"]:
        rec["chat_credit_first"] = date


def resolve_source() -> str:
    """Settle ``auto`` once the scan knows whether any request log existed.

    An explicit choice is never overridden -- someone comparing the two stores
    has to be able to trust that they got the one they asked for.
    """
    rec = source_rec()
    if rec["requested"] == "auto" and not rec["debug_sessions"]:
        rec["effective"] = "sessions"
    return rec["effective"]


def src(key: str) -> dict:
    """Per-source counter block, created on first use."""
    return DIAG.setdefault("sources", {}).setdefault(key, {
        "label": SOURCE_LABELS.get(key, key),
        "roots": [],
        "files_found": 0,
        "files_parsed": 0,
        "files_deferred": 0,
        "files_failed": 0,
        "bad_lines": 0,
    })


def diag_err(source: str, path: str, exc: object) -> None:
    """Record one read/parse failure (capped) so it is never silently dropped."""
    src(source)["files_failed"] += 1
    errs = DIAG.setdefault("errors", [])
    if len(errs) < ERR_CAP:
        errs.append({"source": source, "path": path,
                     "error": f"{type(exc).__name__}: {exc}"[:300]})


@contextlib.contextmanager
def guarded(source: str, path: str):
    """Contain one unit of the scan: a session, a file, a workspace, a scanner.

    These logs are written by software we do not control, on machines we cannot
    inspect. One of them being unreadable or shaped unexpectedly must cost that
    one unit, not the whole report -- so the failure is recorded where the
    Diagnostics tab will show it, and the scan moves on.
    """
    try:
        yield
    except Exception as exc:  # noqa: BLE001 - deliberate: contain, record, continue
        diag_err(source, path, exc)


def coverage(projects: list[dict]) -> None:
    """Explain every request that carries no token payload.

    Without this the dashboard silently mixes requests that were fully recorded
    with requests whose source never stored tokens, which reads as "this project
    used no credits". Here each one is attributed to a project, a client and the
    concrete reason its tokens are missing.
    """
    by_client = {k: {"requests": 0, "no_tokens": 0} for k in ("vscode", "cli", "claude")}
    rows: list[dict] = []
    for p in projects:
        for k in ("vscode", "cli", "claude"):
            models = p[k].get("by_model", {})
            req = sum(b["requests"] for b in models.values())
            if not req:
                continue
            nt = models.get(NO_TOKEN, {}).get("requests", 0)
            by_client[k]["requests"] += req
            by_client[k]["no_tokens"] += nt
            if nt:
                rows.append({"project": p["name"], "client": k, "requests": req,
                             "no_tokens": nt, "reason": NO_TOKEN_REASON[k]})
    total = sum(v["requests"] for v in by_client.values())
    missing = sum(v["no_tokens"] for v in by_client.values())
    rows.sort(key=lambda r: -r["no_tokens"])
    DIAG["coverage"] = {
        "requests": total,
        "requests_no_tokens": missing,
        "pct_no_tokens": round(missing * 100.0 / total, 2) if total else 0.0,
        "by_client": by_client,
    }
    DIAG["no_token_rows"] = rows


def credit_floor(projects: list[dict]) -> dict:
    """The earliest date from which every credit-reporting harness was reporting.

    Credit telemetry did not arrive everywhere at once: VS Code began months
    before the CLI did. Below the last of those start dates a total is
    arithmetically correct and materially incomplete, because at least one
    harness was contributing requests and no credits at all.

    A harness that never reports credits (Claude Code publishes none) is not
    "yet to start" -- excluding it is the difference between a usable floor and
    one that hides everything.

    Returns the floor, each harness's onset, the ones that never report, and how
    many active days fall below the floor, so the dashboard can say why the
    earlier period looks empty rather than leaving a reader to guess.
    """
    onsets: dict[str, str] = {}
    never: list[str] = []
    days: set[str] = set()
    for client in ("vscode", "cli", "claude"):
        first = None
        seen = False
        for p in projects:
            for date, b in p.get(client, {}).get("by_day", {}).items():
                days.add(date)
                seen = True
                if b.get("aiu", 0) > 0 and (first is None or date < first):
                    first = date
        if first:
            onsets[client] = first
        elif seen:
            never.append(client)
    floor = max(onsets.values()) if onsets else None
    return {
        "floor": floor,
        "onsets": onsets,
        "never_reports": never,
        "first_day": min(days) if days else None,
        "days_before": len([d for d in days if floor and d < floor]),
    }


diag_reset()
