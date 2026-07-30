"""What one extraction run actually saw, skipped and failed on.

Without this record the failure modes are indistinguishable: a rotated log, an
unreadable file, and a source that never stored token counts all look exactly
like "this project had no usage". Every scanner reports into ``DIAG``, and the
dashboard's Diagnostics tab renders it.

``DIAG`` is mutated in place, never rebound, so a module that imported it keeps
seeing the live record.
"""
from __future__ import annotations

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
    })


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


diag_reset()
