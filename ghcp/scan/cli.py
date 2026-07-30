"""Copilot CLI usage, from ``~/.copilot/session-store.db``.

Per-request billing (``assistant_usage_events``) only exists from ~2026-07-09.
Older CLI sessions have no token or credit rows, but the ``turns`` table records
every conversation turn over the full history. Those turns are counted as REAL
requests -- each one is a call that happened -- while their token magnitudes stay
0, because they were never written down. Nothing is estimated to fill the gap.
"""
from __future__ import annotations

import os
import sqlite3
from collections import defaultdict

from ghcp.constants import AGENT_CLI, AM_SEP, NO_TOKEN
from ghcp.diagnostics import diag_err, src
from ghcp.model import _add_day, _add_flat, _metrics
from ghcp.naming import is_junk_cwd, project_name, repo_slug


def scan_cli(cli_home: str) -> dict[str, dict]:
    """project -> metrics for the Copilot CLI store under ``cli_home``."""
    out: dict[str, dict] = defaultdict(_metrics)
    db = os.path.join(cli_home, "session-store.db")
    s = src("cli")
    s["roots"].append({"path": db, "exists": os.path.isfile(db)})
    if not os.path.isfile(db):
        return out
    s["files_found"] += 1
    try:
        uri = "file:" + db.replace("\\", "/") + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        sid_project: dict[str, str] = {}
        for sid, repo, cwd, created in conn.execute(
                "SELECT id, repository, cwd, created_at FROM sessions"):
            slug = repo_slug(repo)
            if slug:
                name = slug
            elif not is_junk_cwd(cwd):
                name = project_name(cwd)
            else:
                name = ""
            if name:
                sid_project[sid] = name
                if created:
                    _add_day(out[name], str(created)[:10], sessions=1)

        have_usage: set[str] = set()
        cli_real_days: set[str] = set()
        for sid, inp, outp, nano, model, created in conn.execute(
                "SELECT session_id, input_tokens, output_tokens, total_nano_aiu, "
                "model, created_at FROM assistant_usage_events"):
            have_usage.add(sid)
            name = sid_project.get(sid)
            if not name or not created:
                continue
            cli_real_days.add(str(created)[:10])
            aiu = (nano or 0) / 1e9
            if not model:
                raise ValueError(f"CLI usage event {sid} carries tokens but no model")
            _add_day(out[name], str(created)[:10], requests=1,
                     in_=inp or 0, out=outp or 0, aiu=aiu)
            _add_flat(out[name]["by_model"], model, requests=1,
                      in_=inp or 0, out=outp or 0, aiu=aiu)
            _add_flat(out[name]["by_agent"], AGENT_CLI, requests=1,
                      in_=inp or 0, out=outp or 0, aiu=aiu)
            _add_flat(out[name]["by_am"], AGENT_CLI + AM_SEP + model,
                      requests=1, in_=inp or 0, out=outp or 0, aiu=aiu)
            _add_flat(out[name]["by_dm"], str(created)[:10] + AM_SEP + model,
                      requests=1, in_=inp or 0, out=outp or 0, aiu=aiu)
            out[name]["by_sdm"][sid + AM_SEP + str(created)[:10]
                                + AM_SEP + model] = 1

        # Recover pre-telemetry requests from turns as REAL request counts (each
        # turn is a call that happened). Their token/AIU magnitudes were never
        # logged, so they stay 0 — we never estimate. Skip dates that already
        # have real per-request billing to avoid double counting.
        for sid, ts in conn.execute("SELECT session_id, timestamp FROM turns"):
            if sid in have_usage:
                continue
            name = sid_project.get(sid)
            if not name or not ts:
                continue
            date = str(ts)[:10]
            if date in cli_real_days:
                continue
            _add_day(out[name], date, requests=1)
            _add_flat(out[name]["by_model"], NO_TOKEN, requests=1)
            _add_flat(out[name]["by_agent"], AGENT_CLI, requests=1)
            _add_flat(out[name]["by_am"], AGENT_CLI + AM_SEP + NO_TOKEN, requests=1)
            _add_flat(out[name]["by_dm"], date + AM_SEP + NO_TOKEN, requests=1)
            out[name]["by_sdm"][sid + AM_SEP + date + AM_SEP + NO_TOKEN] = 1
        conn.close()
        s["files_parsed"] += 1
    except Exception as e:
        diag_err("cli", db, e)
    return out
