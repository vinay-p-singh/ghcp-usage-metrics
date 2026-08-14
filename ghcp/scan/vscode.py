"""VS Code Copilot Chat usage, from workspaceStorage.

Three sources feed this, in order of richness:

  debug-logs/<sid>/main.jsonl   full per-request tokens and credits, but rotated
  debug-logs/<sid>/runSubagent-*.jsonl  a named subagent's OWN tokens
  chatSessions/*.json|.jsonl    retained far longer, but trimmed of most request
                                bodies -- used only for sessions the debug-logs
                                no longer hold, so nothing is counted twice

Only recorded values are used. A session whose body was trimmed still lights up
its activity day with a floor of one real interaction, because the session
timestamps prove work happened -- but its token counts stay 0 rather than being
estimated.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
from collections import defaultdict

from ghcp.billing import (apply_billing, billing_or_defer, load_cache, prewarm,
                          save_cache)
from ghcp.constants import AGENT_DEFAULT, AM_SEP, NO_TOKEN, RUNSUBAGENT_PREFIX
from ghcp.diagnostics import diag_err, guarded, src
from ghcp.jsonl import _langs_from_response, _reconstruct_jsonl
from ghcp.model import _add_day, _add_flat, _metrics, name_session
from ghcp.naming import project_name, repo_slug, uri_to_path
from ghcp.normalize import (_any_date, _date_of_path, _norm_agent, _norm_model,
                            _utc_date_ms)
from ghcp.window import in_window

_SKILL_RX = re.compile(r"[\\/]skills?[\\/]([^\\/]+)[\\/]SKILL\.md", re.I)


def _connect_ro(db: str):
    return sqlite3.connect("file:" + db.replace("\\", "/") + "?mode=ro", uri=True)


def sid_repo_map(db: str) -> dict[str, str]:
    """session id -> repo slug, from the Copilot Chat session-store.db."""
    out: dict[str, str] = {}
    if not os.path.isfile(db):
        return out
    try:
        conn = _connect_ro(db)
        for sid, repo in conn.execute("SELECT id, repository FROM sessions"):
            slug = repo_slug(repo)
            if slug:
                out[sid] = slug
        conn.close()
    except Exception:
        pass
    return out


def sid_agent_map(db: str) -> dict[str, str]:
    """session id -> display agent name, from session-store.db sessions.agent_name."""
    out: dict[str, str] = {}
    if not os.path.isfile(db):
        return out
    try:
        conn = _connect_ro(db)
        cols = [c[1] for c in conn.execute("PRAGMA table_info(sessions)")]
        if "agent_name" in cols:
            for sid, agent in conn.execute("SELECT id, agent_name FROM sessions"):
                out[sid] = _norm_agent(agent)
        conn.close()
    except Exception:
        pass
    return out


def sid_summary_map(db: str) -> dict[str, str]:
    """session id -> the short summary VS Code stored for it.

    Only sessions the store still retains have one; the rest were purged, so a
    session with no entry here is shown by its id rather than given a name.
    """
    out: dict[str, str] = {}
    if not os.path.isfile(db):
        return out
    try:
        conn = _connect_ro(db)
        cols = [c[1] for c in conn.execute("PRAGMA table_info(sessions)")]
        if "summary" in cols:
            for sid, summary in conn.execute("SELECT id, summary FROM sessions"):
                if summary and str(summary).strip():
                    out[sid] = str(summary).strip()
        conn.close()
    except Exception:
        pass
    return out


def sid_skills_map(db: str) -> dict[str, dict[str, int]]:
    """session id -> {skill_name: SKILL.md read count}, from session_files.

    A SKILL.md read (a ``read_file`` on a skill's ``SKILL.md``) means that skill
    was actually pulled into the conversation -- real usage, not the always-
    injected skill catalogue. VS Code only (the CLI/Claude have no equivalent).
    Only recently-retained sessions are recorded (session-store keeps a limited
    window), so this reflects recent VS Code skill usage.
    """
    out: dict[str, dict[str, int]] = {}
    if not os.path.isfile(db):
        return out
    try:
        conn = _connect_ro(db)
        cols = [c[1] for c in conn.execute("PRAGMA table_info(session_files)")]
        if "session_id" in cols and "file_path" in cols:
            for sid, fp in conn.execute(
                    "SELECT session_id, file_path FROM session_files "
                    "WHERE file_path LIKE '%SKILL.md%'"):
                m = _SKILL_RX.search(fp or "")
                if not m:
                    continue
                d = out.setdefault(sid, {})
                nm = m.group(1)
                d[nm] = d.get(nm, 0) + 1
        conn.close()
    except Exception:
        pass
    return out


def _attribute_skills(m: dict, skills: dict | None, per_day: dict) -> None:
    """Credit a session's totals to every skill whose SKILL.md it read.

    A session that used several skills counts toward each of them, so per-skill
    totals deliberately overlap. Read counts stay exact either way.

    ``per_day`` maps date -> (requests, in, out, aiu) for this session, so the
    credits land on the day they were spent and a date filter can cut them. The
    reads themselves carry no timestamp -- ``session_files`` records that a
    SKILL.md was read, never when -- so they are counted once on the session's
    first active day. Repeating them per day would inflate the lifetime total.
    """
    if not skills or not per_day:
        return
    first = min(per_day)
    for skname, reads in skills.items():
        for date, (d_req, d_in, d_out, d_aiu) in per_day.items():
            for bucket in (m["by_skill"][skname],
                           m["by_ds"][date + AM_SEP + skname]):
                bucket["requests"] += d_req
                bucket["in"] += d_in
                bucket["out"] += d_out
                bucket["aiu"] += d_aiu
        for bucket in (m["by_skill"][skname], m["by_ds"][first + AM_SEP + skname]):
            bucket["reads"] += reads
            bucket["sessions"] += 1


def scan_chat_file(cf: str, out: dict, sid_repo: dict, sid_agent: dict,
                   sid_skills: dict, seen_sids: set, fallback: str,
                   hash_dbg: set, sid_summary: dict | None = None) -> bool:
    """Add a chatSessions file's real requests to ``out`` when the session is NOT
    already covered by a (richer) debug-log. ``copilotCredits`` == AIU. These
    retained sessions reach further back than the rotated debug-logs and carry
    tools + code-fence languages. Returns False when the file could not be read."""
    if cf.endswith(".jsonl"):
        data = _reconstruct_jsonl(cf)
    else:
        try:
            with open(cf, encoding="utf-8", errors="replace") as fh:
                data = json.load(fh)
        except Exception as e:
            diag_err("vscode_chat", cf, e)
            return False
    if not isinstance(data, dict):
        return False
    sid = data.get("sessionId") or os.path.splitext(os.path.basename(cf))[0]
    seen_sids.add(sid)
    if sid in hash_dbg:
        return True
    reqs = data.get("requests") or []
    if not isinstance(reqs, list):
        reqs = []
    name = sid_repo.get(sid, fallback)
    agent = sid_agent.get(sid, AGENT_DEFAULT)
    m = out[name]
    name_session(m, sid, (sid_summary or {}).get(sid))
    dates = []
    per_day: dict[str, list] = {}
    for r in reqs:
        if not isinstance(r, dict):
            continue
        ts = r.get("timestamp")
        if not isinstance(ts, (int, float)):
            continue
        date = _utc_date_ms(ts)
        dates.append(date)
        # Some retained sessions record the counts on the request, others only
        # under result.metadata. Both are the source's own figures.
        md = (r.get("result") or {}).get("metadata") or {}
        it = r.get("promptTokens") or md.get("promptTokens") or 0
        ot = r.get("completionTokens") or md.get("completionTokens") or 0
        cc = r.get("copilotCredits") or md.get("copilotCredits") or 0.0
        model = _norm_model(r.get("modelId"))
        _add_day(m, date, requests=1, in_=it, out=ot, aiu=cc)
        _add_flat(m["by_model"], model, requests=1, in_=it, out=ot, aiu=cc)
        _add_flat(m["by_agent"], agent, requests=1, in_=it, out=ot, aiu=cc)
        _add_flat(m["by_da"], date + AM_SEP + agent, requests=1, in_=it, out=ot, aiu=cc)
        _add_flat(m["by_am"], agent + AM_SEP + model, requests=1, in_=it, out=ot, aiu=cc)
        _add_flat(m["by_dam"], date + AM_SEP + agent + AM_SEP + model,
                  requests=1, in_=it, out=ot, aiu=cc)
        _add_flat(m["by_dm"], date + AM_SEP + model, requests=1, in_=it, out=ot, aiu=cc)
        _add_flat(m["by_sdm"], sid + AM_SEP + date + AM_SEP + model,
                  requests=1, in_=it, out=ot, aiu=cc)
        d = per_day.setdefault(date, [0, 0, 0, 0.0])
        d[0] += 1
        d[1] += it
        d[2] += ot
        d[3] += cc
        md = (r.get("result") or {}).get("metadata") or {}
        for rd in (md.get("toolCallRounds") or []):
            for tc in (rd.get("toolCalls") or []):
                nm = tc.get("name") if isinstance(tc, dict) else None
                if nm:
                    m["by_tool"][nm] += 1
                    m["by_dt"][date + AM_SEP + nm] += 1
        for lang in _langs_from_response(r.get("response")):
            m["by_lang"][lang] += 1
            m["by_dl"][date + AM_SEP + lang] += 1

    # Session-activity days: a session's creation + last-message timestamps are
    # real evidence the user worked that day, even after the request bodies were
    # trimmed from the persisted session. Light up those days with a floor of ONE
    # real interaction (never an estimate of volume) so the activity calendar
    # reflects when work actually happened — not just the few requests
    # VS Code still retains.
    seen = set(dates)
    for key in ("creationDate", "lastMessageDate", "lastMessageTime"):
        d = _any_date(data.get(key))
        if d and d not in seen:
            _add_day(m, d, requests=1)
            _add_flat(m["by_model"], NO_TOKEN, requests=1)
            _add_flat(m["by_agent"], agent, requests=1)
            _add_flat(m["by_da"], d + AM_SEP + agent, requests=1)
            _add_flat(m["by_am"], agent + AM_SEP + NO_TOKEN, requests=1)
            _add_flat(m["by_dam"], d + AM_SEP + agent + AM_SEP + NO_TOKEN, requests=1)
            _add_flat(m["by_dm"], d + AM_SEP + NO_TOKEN, requests=1)
            _add_flat(m["by_sdm"], sid + AM_SEP + d + AM_SEP + NO_TOKEN,
                      requests=1)
            seen.add(d)
            per_day.setdefault(d, [1, 0, 0, 0.0])
    if seen:
        _add_day(m, min(seen), sessions=1)
    _attribute_skills(m, sid_skills.get(sid), {k: tuple(v) for k, v in per_day.items()})
    return True


def _scan_session_dir(entry, m: dict, agent: str, cache: dict,
                      anchor: str | None = None) -> tuple[dict, dict]:
    """One debug-log session: its main log plus every child log it spawned.

    Returns the main log's record (for the session date) and the session-wide
    per-day ``date -> (requests, input, output, aiu)`` totals across main and
    children. Per-day rather than one lump because a session that runs past
    midnight has to be splittable by the day each request actually landed on.
    """
    per_day: dict[str, list] = {}

    def _roll(r: dict) -> None:
        for date, b in r.get("by_day", {}).items():
            d = per_day.setdefault(date, [0, 0, 0, 0.0])
            d[0] += b["requests"]
            d[1] += b["in"]
            d[2] += b["out"]
            d[3] += b["aiu"]

    mj = os.path.join(entry.path, "main.jsonl")
    rec = billing_or_defer(mj, cache) if os.path.isfile(mj) else {}
    childrefs = rec.get("childrefs", {})
    apply_billing(m, agent, rec, anchor)
    _roll(rec)
    for key, b in rec.get("by_dm", {}).items():
        _add_flat(m["by_sdm"], entry.name + AM_SEP + key, requests=b["requests"],
                  in_=b["in"], out=b["out"], aiu=b["aiu"],
                  cached=b.get("cached", 0), cached_req=b.get("cached_req", 0))
    # Child logs: runSubagent-<name>-<sid>.jsonl carry a named subagent's OWN
    # tokens; title/summarize logs fold into the session's agent.
    for cf in os.scandir(entry.path):
        if not cf.is_file() or cf.name == "main.jsonl" or not cf.name.endswith(".jsonl"):
            continue
        lbl = childrefs.get(cf.name, "")
        if lbl.startswith(RUNSUBAGENT_PREFIX):
            sub = _norm_agent(lbl[len(RUNSUBAGENT_PREFIX):])
        else:
            sub = agent
        child = billing_or_defer(cf.path, cache)
        apply_billing(m, sub, child, anchor)
        _roll(child)
        for key, b in child.get("by_dm", {}).items():
            _add_flat(m["by_sdm"], entry.name + AM_SEP + key,
                      requests=b["requests"], in_=b["in"], out=b["out"],
                      aiu=b["aiu"], cached=b.get("cached", 0),
                      cached_req=b.get("cached_req", 0))
    return rec, {k: tuple(v) for k, v in per_day.items()}


def _scan_workspace(vs_root: str, h: str, fallback: str, out: dict, cache: dict,
                    maps: dict, seen_sids: set) -> None:
    """Scan one workspace hash: its debug-logs, then its retained chatSessions."""
    sid_repo, sid_agent, sid_skills = maps["repo"], maps["agent"], maps["skills"]
    sid_summary = maps.get("summary", {})
    hash_dbg: set[str] = set()
    dbg = os.path.join(vs_root, h, "GitHub.copilot-chat", "debug-logs")
    if os.path.isdir(dbg):
        for e in os.scandir(dbg):
            if not e.is_dir():
                continue
            hash_dbg.add(e.name)
            seen_sids.add(e.name)
            with guarded("vscode_debug", e.path):
                m = out[sid_repo.get(e.name, fallback)]
                agent = sid_agent.get(e.name, AGENT_DEFAULT)
                name_session(m, e.name, sid_summary.get(e.name))
                rec, totals = _scan_session_dir(e, m, agent, cache,
                                                _date_of_path(e.path))
                _attribute_skills(m, sid_skills.get(e.name), totals)
                main_by_day = rec.get("by_day", {})
                sdate = min(main_by_day) if main_by_day else _date_of_path(e.path)
                _add_day(m, sdate, sessions=1)

    # chatSessions: retained (request-trimmed) sessions extend history back
    # further than the rotated debug-logs and carry real copilotCredits,
    # tools and languages. Add only sessions NOT already in debug-logs.
    chat_dir = os.path.join(vs_root, h, "chatSessions")
    if not os.path.isdir(chat_dir):
        return
    for cf in (glob.glob(os.path.join(chat_dir, "*.json"))
               + glob.glob(os.path.join(chat_dir, "*.jsonl"))):
        cs = src("vscode_chat")
        cs["files_found"] += 1
        if not in_window(cf):
            cs["files_deferred"] += 1
            continue
        with guarded("vscode_chat", cf):
            if scan_chat_file(cf, out, sid_repo, sid_agent, sid_skills,
                              seen_sids, fallback, hash_dbg, sid_summary):
                cs["files_parsed"] += 1


def scan_vscode_root(vs_root: str, vs_db: str, out: dict, cache: dict,
                     seen_sids: set) -> None:
    """Scan one VS Code variant's workspaceStorage into ``out``."""
    maps = {"repo": sid_repo_map(vs_db),
            "agent": sid_agent_map(vs_db),
            "skills": sid_skills_map(vs_db),
            "summary": sid_summary_map(vs_db)}
    for wj in glob.glob(os.path.join(vs_root, "*", "workspace.json")):
        h = os.path.basename(os.path.dirname(wj))
        src("vscode_ws")["files_found"] += 1
        try:
            with open(wj, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception as e:
            diag_err("vscode_ws", wj, e)
            continue
        src("vscode_ws")["files_parsed"] += 1
        folder = uri_to_path(d.get("folder") or d.get("workspace") or "")
        fallback = project_name(folder) if folder else "(no folder)"
        with guarded("vscode_ws", wj):
            _scan_workspace(vs_root, h, fallback, out, cache, maps, seen_sids)

    # Orphan skill reads: SKILL.md invocations logged in session_files for
    # sessions whose bodies were fully purged (no debug-log AND no chatSessions
    # file survives). Attribute the exact read counts (token-less, aiu=0) to the
    # session's repo so per-skill invocation totals stay exact; no estimation.
    for sid, sk in maps["skills"].items():
        if sid in seen_sids:
            continue
        name = maps["repo"].get(sid)
        if not name:
            continue
        m = out[name]
        for skname, reads in sk.items():
            b = m["by_skill"][skname]
            b["reads"] += reads
            b["sessions"] += 1


def scan_vscode(variants: list[tuple[str, str]], cache_path: str) -> dict[str, dict]:
    """project -> metrics across every (workspaceStorage, session-store.db) pair.

    Only recorded values are used: real input/output tokens for every request,
    and real AIU where GitHub reported ``copilotUsageNanoAiu``.
    """
    out: dict[str, dict] = defaultdict(_metrics)
    cache = load_cache(cache_path)
    for vs_root, _db in variants:
        src("vscode_debug")["roots"].append(
            {"path": vs_root, "exists": os.path.isdir(vs_root)})
    prewarm(cache, [r for r, _ in variants])
    seen_sids: set[str] = set()
    for vs_root, vs_db in variants:
        if os.path.isdir(vs_root):
            with guarded("vscode_debug", vs_root):
                scan_vscode_root(vs_root, vs_db, out, cache, seen_sids)
    save_cache(cache_path, cache)
    return out
