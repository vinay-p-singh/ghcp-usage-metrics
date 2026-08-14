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
from ghcp.model import _add_day, _add_flat, _metrics, name_session
from ghcp.naming import is_junk_cwd, project_name, repo_slug
from ghcp.normalize import _any_date


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
        scols = {c[1] for c in conn.execute("PRAGMA table_info(sessions)")}
        has_summary = "summary" in scols
        sid_project: dict[str, str] = {}
        select = ("SELECT id, repository, cwd, created_at, "
                  + ("summary" if has_summary else "NULL") + " FROM sessions")
        for sid, repo, cwd, created, summary in conn.execute(select):
            slug = repo_slug(repo)
            if slug:
                name = slug
            elif not is_junk_cwd(cwd):
                name = project_name(cwd)
            else:
                name = ""
            if name:
                sid_project[sid] = name
                name_session(out[name], sid, summary)
                created_day = _any_date(created)
                if created_day:
                    _add_day(out[name], created_day, sessions=1)

        # Cache columns arrived with a later CLI release. When they are absent we
        # record no cache figure at all rather than a zero we did not measure.
        ucols = {c[1] for c in
                 conn.execute("PRAGMA table_info(assistant_usage_events)")}
        has_cache = {"cache_read_tokens", "cache_write_tokens"} <= ucols
        cache_cols = ("cache_read_tokens, cache_write_tokens"
                      if has_cache else "NULL, NULL")

        have_usage: set[str] = set()
        cli_real_days: set[str] = set()
        for sid, inp, outp, nano, model, created, c_read, c_write in conn.execute(
                "SELECT session_id, input_tokens, output_tokens, total_nano_aiu, "
                "model, created_at, " + cache_cols + " FROM assistant_usage_events"):
            have_usage.add(sid)
            name = sid_project.get(sid)
            day = _any_date(created)
            if not name or not day:
                continue
            cli_real_days.add(day)
            aiu = (nano or 0) / 1e9
            if not model:
                raise ValueError(f"CLI usage event {sid} carries tokens but no model")
            cached = (c_read or 0) + (c_write or 0)
            cached_req = 1 if has_cache else 0
            _add_day(out[name], day, requests=1, in_=inp or 0, out=outp or 0,
                     aiu=aiu, cached=cached, cached_req=cached_req)
            for bucket, key in ((out[name]["by_model"], model),
                                (out[name]["by_agent"], AGENT_CLI),
                                (out[name]["by_da"], day + AM_SEP + AGENT_CLI),
                                (out[name]["by_am"], AGENT_CLI + AM_SEP + model),
                                (out[name]["by_dam"],
                                 day + AM_SEP + AGENT_CLI + AM_SEP + model),
                                (out[name]["by_dm"], day + AM_SEP + model),
                                (out[name]["by_sdm"],
                                 sid + AM_SEP + day + AM_SEP + model)):
                _add_flat(bucket, key, requests=1, in_=inp or 0, out=outp or 0,
                          aiu=aiu, cached=cached, cached_req=cached_req)

        # Recover pre-telemetry requests from turns as REAL request counts (each
        # turn is a call that happened). Their token/AIU magnitudes were never
        # logged, so they stay 0 — we never estimate. Skip dates that already
        # have real per-request billing to avoid double counting.
        for sid, ts in conn.execute("SELECT session_id, timestamp FROM turns"):
            if sid in have_usage:
                continue
            name = sid_project.get(sid)
            date = _any_date(ts)
            if not name or not date:
                continue
            if date in cli_real_days:
                continue
            _add_day(out[name], date, requests=1)
            _add_flat(out[name]["by_model"], NO_TOKEN, requests=1)
            _add_flat(out[name]["by_agent"], AGENT_CLI, requests=1)
            _add_flat(out[name]["by_da"], date + AM_SEP + AGENT_CLI, requests=1)
            _add_flat(out[name]["by_am"], AGENT_CLI + AM_SEP + NO_TOKEN, requests=1)
            _add_flat(out[name]["by_dam"],
                      date + AM_SEP + AGENT_CLI + AM_SEP + NO_TOKEN, requests=1)
            _add_flat(out[name]["by_dm"], date + AM_SEP + NO_TOKEN, requests=1)
            _add_flat(out[name]["by_sdm"],
                      sid + AM_SEP + date + AM_SEP + NO_TOKEN, requests=1)
        conn.close()
        s["files_parsed"] += 1
    except Exception as e:
        diag_err("cli", db, e)
    return out
