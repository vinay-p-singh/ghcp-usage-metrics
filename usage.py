"""ghcp-usage — extraction + dashboard writer.

Lists all PROJECTS across both coding surfaces (clients):
  - vscode : GitHub Copilot Chat in VS Code
  - cli    : GitHub Copilot CLI (~/.copilot)

Project identity prefers the git repo slug (owner/repo), falling back to the
folder / cwd basename:
  - vscode: each debug-logs/<sid> session is attributed to the repo slug from
            session-store.db (sessions.repository); if none, the workspace folder.
  - cli   : ~/.copilot/session-store.db `sessions` -> repo slug, else cwd basename.
            Non-project cwds (Copilot chat scratch dirs, the CLI install folder,
            the bare home directory) are dropped.

This file is DATA ONLY. All markup lives in dashboard_template.py; here we build
the project list, inject it as JSON, and write out/dashboard.html. Stdlib only.
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

from dashboard_template import DASHBOARD_TEMPLATE
from ghcp.constants import (AGENT_CLAUDE, AGENT_CLI, AGENT_DEFAULT, AM_SEP,
                            NO_TOKEN, RUNSUBAGENT_PREFIX)
from ghcp.jsonl import _langs_from_response, _reconstruct_jsonl
from ghcp.model import _add_day, _add_flat, _flatbucket, _metrics, build_projects
from ghcp.naming import is_junk_cwd, project_name, repo_slug, uri_to_path
from ghcp.normalize import (_any_date, _date_of_path, _norm_agent, _norm_model,
                            _utc_date_ms)

# Re-exported so ``usage.<name>`` stays importable: these are the module's public
# helpers, exercised directly by the test-suite. Imported for re-export only.
from ghcp.jsonl import _append_at_path, _set_at_path  # noqa: F401  # pylint: disable=unused-import
from ghcp.model import _daybucket, _merge, _sessions, _skillbucket  # noqa: F401  # pylint: disable=unused-import
from ghcp.naming import _canon  # noqa: F401  # pylint: disable=unused-import

# Backwards-compatible private alias kept for the test-suite contract.
_AM_SEP = AM_SEP

APPDATA = os.environ.get("APPDATA", "")
HOME = os.path.expanduser("~")
VS_ROOT = os.path.join(APPDATA, "Code", "User", "workspaceStorage")
VS_DB = os.path.join(APPDATA, "Code", "User", "globalStorage",
                     "github.copilot-chat", "session-store.db")
CLI_HOME = os.path.join(HOME, ".copilot")
CLAUDE_ROOT = os.path.join(HOME, ".claude", "projects")
_ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(_ROOT, "out")
CACHE = os.path.join(_ROOT, ".cache", "vscode_billing.json")


def _load_cache() -> dict:
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    try:
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception:
        pass


def _billing_for_file(path: str, cache: dict) -> dict:
    """Per-day llm billing from one main.jsonl, memoised by path + size + mtime.

    Counts every request that carries ``inputTokens`` (real input/output tokens)
    and sums ``copilotUsageNanoAiu`` where GitHub reported it. Nothing is
    estimated: requests logged before AIU reporting existed contribute their
    real tokens and simply add 0 AIU.

    Returns {"size", "mtime",
             "by_day": {date: {requests, in, out, aiu}},
             "by_model": {model: {requests, in, out, aiu}},
             "tools": {tool_name: count},          # from tool_call events
             "childrefs": {childLogFile: label}}  # subagent/title child logs
    """
    st = os.stat(path)
    hit = cache.get(path)
    if (hit and hit.get("size") == st.st_size
            and hit.get("mtime") == int(st.st_mtime)
            and "by_day" in hit and "by_model" in hit
            and "childrefs" in hit and "tools" in hit and "cal" not in hit):
        return hit
    by_day: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    childrefs: dict[str, str] = {}
    tools: dict[str, int] = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if ("inputTokens" not in line and "child_session_ref" not in line
                    and "tool_call" not in line):
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            et = ev.get("type") or ev.get("kind")
            if et == "child_session_ref":
                ca = ev.get("attrs") or {}
                clf = ca.get("childLogFile")
                if clf:
                    childrefs[clf] = ca.get("label") or ""
                continue
            if et == "tool_call":
                ta = ev.get("attrs") or {}
                nm = ta.get("name") or ev.get("name")
                if nm:
                    tools[nm] = tools.get(nm, 0) + 1
                continue
            a = ev.get("attrs") or {}
            ts = ev.get("ts")
            if "inputTokens" not in a or not isinstance(ts, (int, float)):
                continue
            it = a.get("inputTokens") or 0
            ot = a.get("outputTokens") or 0
            model = a.get("model") or "?"
            nano = a.get("copilotUsageNanoAiu")
            aiu = (nano / 1e9) if nano is not None else 0.0
            d = by_day.setdefault(_utc_date_ms(ts), _flatbucket())
            mm = by_model.setdefault(model, _flatbucket())
            d["requests"] += 1
            d["in"] += it
            d["out"] += ot
            d["aiu"] += aiu
            mm["requests"] += 1
            mm["in"] += it
            mm["out"] += ot
            mm["aiu"] += aiu
    rec = {"size": st.st_size, "mtime": int(st.st_mtime),
           "by_day": by_day, "by_model": by_model, "tools": tools,
           "childrefs": childrefs}
    cache[path] = rec
    return rec


def _apply_billing(m: dict, agent: str, rec: dict) -> tuple[int, int, int, float]:
    """Fold one main/child ``_billing_for_file`` record into a project's metrics,
    attributing every request's tokens to the display ``agent``. Updates by_day,
    by_tool, by_model, by_am and (once) by_agent; returns this log's
    ``(requests, input, output, aiu)`` totals so the caller can track the
    session-wide total across the parent and all its child logs.
    """
    for date, b in rec.get("by_day", {}).items():
        _add_day(m, date, requests=b["requests"], in_=b["in"],
                 out=b["out"], aiu=b["aiu"])
    for tname, tc in rec.get("tools", {}).items():
        m["by_tool"][tname] += tc
    req = in_ = out = 0
    aiu = 0.0
    for model, b in rec.get("by_model", {}).items():
        _add_flat(m["by_model"], model, requests=b["requests"],
                  in_=b["in"], out=b["out"], aiu=b["aiu"])
        _add_flat(m["by_am"], agent + AM_SEP + model, requests=b["requests"],
                  in_=b["in"], out=b["out"], aiu=b["aiu"])
        req += b["requests"]
        in_ += b["in"]
        out += b["out"]
        aiu += b["aiu"]
    if req:
        _add_flat(m["by_agent"], agent, requests=req, in_=in_, out=out, aiu=aiu)
    return req, in_, out, aiu


def _bill_parse(path: str):
    """Pool worker: parse one billing file fresh (no cache) for the prewarm.
    Returns ``(path, rec)`` — ``rec`` is the small per-day/per-model summary that
    ``_billing_for_file`` produces, or ``None`` on any read/parse error."""
    try:
        return path, _billing_for_file(path, {})
    except Exception:
        return path, None


def _billing_cache_hit(cache: dict, path: str) -> bool:
    """True when ``cache`` already holds a current summary for ``path``."""
    try:
        st = os.stat(path)
    except OSError:
        return True  # unreadable now; let the sequential pass handle/skip it
    hit = cache.get(path)
    return bool(hit and hit.get("size") == st.st_size
                and hit.get("mtime") == int(st.st_mtime)
                and "by_day" in hit and "by_model" in hit
                and "childrefs" in hit and "tools" in hit and "cal" not in hit)


def _prewarm_billing(cache: dict, roots: list[str]) -> None:
    """Parallel-parse every debug-log ``*.jsonl`` whose cache entry is missing or
    stale, populating ``cache`` so the sequential scan below does no I/O for them.
    This is where the cold first-load time lives (hundreds of JSON logs). Output
    is identical to the sequential path — only the cache is pre-filled. Silently
    no-ops when there's little to do or a process pool can't be created."""
    stale: list[str] = []
    for vs_root in roots:
        if not os.path.isdir(vs_root):
            continue
        for h in os.scandir(vs_root):
            if not h.is_dir():
                continue
            dbg = os.path.join(h.path, "GitHub.copilot-chat", "debug-logs")
            if not os.path.isdir(dbg):
                continue
            for e in os.scandir(dbg):
                if not e.is_dir():
                    continue
                for cf in os.scandir(e.path):
                    if (cf.is_file() and cf.name.endswith(".jsonl")
                            and not _billing_cache_hit(cache, cf.path)):
                        stale.append(cf.path)
    if len(stale) < 8:
        return  # a pool isn't worth it; the sequential scan will parse these
    try:
        with ProcessPoolExecutor() as ex:
            for path, rec in ex.map(_bill_parse, stale, chunksize=8):
                if rec is not None:
                    cache[path] = rec
    except Exception:
        pass  # fall back to the sequential parse below


# --------------------------------------------------------------------------- #
# VS Code
# --------------------------------------------------------------------------- #
def _vs_sid_repo(db: str = "") -> dict[str, str]:
    """session id -> repo slug, from the Copilot Chat session-store.db."""
    db = db or VS_DB
    out: dict[str, str] = {}
    if not os.path.isfile(db):
        return out
    try:
        uri = "file:" + db.replace("\\", "/") + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        for sid, repo in conn.execute("SELECT id, repository FROM sessions"):
            slug = repo_slug(repo)
            if slug:
                out[sid] = slug
        conn.close()
    except Exception:
        pass
    return out


def _vs_sid_agent(db: str = "") -> dict[str, str]:
    """session id -> display agent name, from session-store.db sessions.agent_name."""
    db = db or VS_DB
    out: dict[str, str] = {}
    if not os.path.isfile(db):
        return out
    try:
        uri = "file:" + db.replace("\\", "/") + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        cols = [c[1] for c in conn.execute("PRAGMA table_info(sessions)")]
        if "agent_name" in cols:
            for sid, agent in conn.execute("SELECT id, agent_name FROM sessions"):
                out[sid] = _norm_agent(agent)
        conn.close()
    except Exception:
        pass
    return out


_SKILL_RX = re.compile(r"[\\/]skills?[\\/]([^\\/]+)[\\/]SKILL\.md", re.I)


def _vs_sid_skills(db: str = "") -> dict[str, dict[str, int]]:
    """session id -> {skill_name: SKILL.md read count}, from session_files.

    A SKILL.md read (a ``read_file`` on a skill's ``SKILL.md``) means that skill
    was actually pulled into the conversation — real usage, not the always-
    injected skill catalogue. VS Code only (the CLI/Claude have no equivalent).
    Only recently-retained sessions are recorded (session-store keeps a limited
    window), so this reflects recent VS Code skill usage.
    """
    db = db or VS_DB
    out: dict[str, dict[str, int]] = {}
    if not os.path.isfile(db):
        return out
    try:
        uri = "file:" + db.replace("\\", "/") + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
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


def _scan_chat_file(cf: str, out: dict, sid_repo: dict, sid_agent: dict,
                    sid_skills: dict, seen_sids: set, fallback: str,
                    hash_dbg: set) -> None:
    """Add a chatSessions file's real requests to ``out`` when the session is NOT
    already covered by a (richer) debug-log. ``copilotCredits`` == AIU. These
    retained sessions reach further back than the rotated debug-logs and carry
    tools + code-fence languages."""
    if cf.endswith(".jsonl"):
        data = _reconstruct_jsonl(cf)
    else:
        try:
            with open(cf, encoding="utf-8", errors="replace") as fh:
                data = json.load(fh)
        except Exception:
            return
    if not isinstance(data, dict):
        return
    sid = data.get("sessionId") or os.path.splitext(os.path.basename(cf))[0]
    seen_sids.add(sid)
    if sid in hash_dbg:
        return
    reqs = data.get("requests") or []
    if not isinstance(reqs, list):
        reqs = []
    name = sid_repo.get(sid, fallback)
    agent = sid_agent.get(sid, AGENT_DEFAULT)
    m = out[name]
    dates = []
    s_req = s_in = s_out = 0
    s_aiu = 0.0
    for r in reqs:
        if not isinstance(r, dict):
            continue
        ts = r.get("timestamp")
        if not isinstance(ts, (int, float)):
            continue
        date = _utc_date_ms(ts)
        dates.append(date)
        it = r.get("promptTokens") or 0
        ot = r.get("completionTokens") or 0
        cc = r.get("copilotCredits") or 0.0
        model = _norm_model(r.get("modelId") or "?")
        _add_day(m, date, requests=1, in_=it, out=ot, aiu=cc)
        _add_flat(m["by_model"], model, requests=1, in_=it, out=ot, aiu=cc)
        _add_flat(m["by_agent"], agent, requests=1, in_=it, out=ot, aiu=cc)
        _add_flat(m["by_am"], agent + AM_SEP + model, requests=1, in_=it, out=ot, aiu=cc)
        s_req += 1
        s_in += it
        s_out += ot
        s_aiu += cc
        md = (r.get("result") or {}).get("metadata") or {}
        for rd in (md.get("toolCallRounds") or []):
            for tc in (rd.get("toolCalls") or []):
                nm = tc.get("name") if isinstance(tc, dict) else None
                if nm:
                    m["by_tool"][nm] += 1
        for lang in _langs_from_response(r.get("response")):
            m["by_lang"][lang] += 1

    # Session-activity days: a session's creation + last-message timestamps are
    # real evidence the user worked that day, even after the request bodies were
    # trimmed from the persisted session. Light up those days with a floor of ONE
    # real interaction (never an estimate of volume) so the activity calendar and
    # timeline reflect when work actually happened — not just the few requests
    # VS Code still retains.
    seen = set(dates)
    for key in ("creationDate", "lastMessageDate", "lastMessageTime"):
        d = _any_date(data.get(key))
        if d and d not in seen:
            _add_day(m, d, requests=1)
            _add_flat(m["by_model"], NO_TOKEN, requests=1)
            _add_flat(m["by_agent"], agent, requests=1)
            _add_flat(m["by_am"], agent + AM_SEP + NO_TOKEN, requests=1)
            seen.add(d)
    if seen:
        _add_day(m, min(seen), sessions=1)
    # Skills for chatSessions-only sessions (not in debug-logs): attribute the
    # retained session totals to each skill it read. Widens coverage beyond the
    # rotated debug-logs; reads stay exact even when token bodies were trimmed.
    sk = sid_skills.get(sid)
    if sk:
        for skname, reads in sk.items():
            b = m["by_skill"][skname]
            b["reads"] += reads
            b["sessions"] += 1
            b["requests"] += s_req
            b["in"] += s_in
            b["out"] += s_out
            b["aiu"] += s_aiu




def _vs_variants() -> list[tuple[str, str]]:
    """(workspaceStorage, session-store.db) pairs to scan. Always the current
    VS_ROOT/VS_DB (tests/users may point these elsewhere); plus sibling installs
    (Insiders / VSCodium / Exploration), but only when scanning the real default
    Code install \u2014 so an overridden VS_ROOT stays the single source scanned."""
    pairs = [(VS_ROOT, VS_DB)]
    default_root = os.path.join(APPDATA, "Code", "User", "workspaceStorage") if APPDATA else ""
    if APPDATA and VS_ROOT == default_root:
        for variant in ("Code - Insiders", "VSCodium", "Code - Exploration"):
            r = os.path.join(APPDATA, variant, "User", "workspaceStorage")
            if not os.path.isdir(r):
                continue
            db = os.path.join(APPDATA, variant, "User", "globalStorage",
                              "github.copilot-chat", "session-store.db")
            pairs.append((r, db))
    return pairs


def scan_vscode() -> dict[str, dict]:
    """project -> metrics (sessions + real llm billing) across every installed
    VS Code variant's workspaces.

    Only recorded values are used: real input/output tokens for every request,
    and real AIU where GitHub reported ``copilotUsageNanoAiu``. Nothing is
    estimated.
    """
    out: dict[str, dict] = defaultdict(_metrics)
    variants = _vs_variants()
    cache = _load_cache()
    _prewarm_billing(cache, [r for r, _ in variants])
    seen_sids: set[str] = set()
    for vs_root, vs_db in variants:
        if os.path.isdir(vs_root):
            _scan_vscode_root(vs_root, vs_db, out, cache, seen_sids)
    _save_cache(cache)
    return out


def _scan_vscode_root(vs_root: str, vs_db: str, out: dict, cache: dict,
                      seen_sids: set) -> None:
    """Scan one VS Code variant's workspaceStorage into ``out`` (see scan_vscode)."""
    sid_repo = _vs_sid_repo(vs_db)
    sid_agent = _vs_sid_agent(vs_db)
    sid_skills = _vs_sid_skills(vs_db)
    for wj in glob.glob(os.path.join(vs_root, "*", "workspace.json")):
        h = os.path.basename(os.path.dirname(wj))
        try:
            with open(wj, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            continue
        folder = uri_to_path(d.get("folder") or d.get("workspace") or "")
        fallback = project_name(folder) if folder else "(no folder)"
        hash_dbg: set[str] = set()
        dbg = os.path.join(vs_root, h, "GitHub.copilot-chat", "debug-logs")
        if os.path.isdir(dbg):
            for e in os.scandir(dbg):
                if not e.is_dir():
                    continue
                hash_dbg.add(e.name)
                seen_sids.add(e.name)
                name = sid_repo.get(e.name, fallback)
                agent = sid_agent.get(e.name, AGENT_DEFAULT)
                m = out[name]
                mj = os.path.join(e.path, "main.jsonl")
                rec = _billing_for_file(mj, cache) if os.path.isfile(mj) else {}
                childrefs = rec.get("childrefs", {})
                main_by_day = rec.get("by_day", {})
                a_req, a_in, a_out, a_aiu = _apply_billing(m, agent, rec)
                # Running session total across main + all child logs (skills).
                s_req, s_in, s_out, s_aiu = a_req, a_in, a_out, a_aiu
                # Child logs: runSubagent-<name>-<sid>.jsonl carry a named
                # subagent's OWN tokens; title/summarize fold into the agent.
                for cf in os.scandir(e.path):
                    if not cf.is_file() or cf.name == "main.jsonl" \
                            or not cf.name.endswith(".jsonl"):
                        continue
                    lbl = childrefs.get(cf.name, "")
                    if lbl.startswith(RUNSUBAGENT_PREFIX):
                        sub = _norm_agent(lbl[len(RUNSUBAGENT_PREFIX):])
                    else:
                        sub = agent
                    crec = _billing_for_file(cf.path, cache)
                    c_req, c_in, c_out, c_aiu = _apply_billing(m, sub, crec)
                    s_req += c_req
                    s_in += c_in
                    s_out += c_out
                    s_aiu += c_aiu
                # Skills: attribute this session's totals to every skill whose
                # SKILL.md it read (real invocation; a session's tokens count
                # toward each skill it used). VS Code only.
                sk = sid_skills.get(e.name)
                if sk:
                    for skname, reads in sk.items():
                        b = m["by_skill"][skname]
                        b["reads"] += reads
                        b["sessions"] += 1
                        b["requests"] += s_req
                        b["in"] += s_in
                        b["out"] += s_out
                        b["aiu"] += s_aiu
                sdate = min(main_by_day) if main_by_day else _date_of_path(e.path)
                _add_day(m, sdate, sessions=1)
        # chatSessions: retained (request-trimmed) sessions extend history back
        # further than the rotated debug-logs and carry real copilotCredits,
        # tools and languages. Add only sessions NOT already in debug-logs.
        chat_dir = os.path.join(vs_root, h, "chatSessions")
        if os.path.isdir(chat_dir):
            for cf in (glob.glob(os.path.join(chat_dir, "*.json"))
                       + glob.glob(os.path.join(chat_dir, "*.jsonl"))):
                _scan_chat_file(cf, out, sid_repo, sid_agent, sid_skills, seen_sids, fallback, hash_dbg)
    # Orphan skill reads: SKILL.md invocations logged in session_files for
    # sessions whose bodies were fully purged (no debug-log AND no chatSessions
    # file survives). Attribute the exact read counts (token-less, aiu=0) to the
    # session's repo so per-skill invocation totals stay exact; no estimation.
    for sid, sk in sid_skills.items():
        if sid in seen_sids:
            continue
        name = sid_repo.get(sid)
        if not name:
            continue
        m = out[name]
        for skname, reads in sk.items():
            b = m["by_skill"][skname]
            b["reads"] += reads
            b["sessions"] += 1


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def scan_cli() -> dict[str, dict]:
    """project -> metrics (sessions + llm billing) from ~/.copilot/session-store.db.

    Per-request billing (``assistant_usage_events``) only exists from ~2026-07-09.
    Older CLI sessions have no token/AIU rows, but the ``turns`` table records
    every conversation turn (with a timestamp) over the full history. For those
    pre-telemetry sessions we recover the request count from ``turns`` as REAL
    requests (each turn is a call that happened); their token/AIU magnitudes were
    never logged, so they stay 0 and are bucketed under the ``NO_TOKEN`` model.
    Nothing is estimated.
    """
    out: dict[str, dict] = defaultdict(_metrics)
    db = os.path.join(CLI_HOME, "session-store.db")
    if not os.path.isfile(db):
        return out
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
            _add_day(out[name], str(created)[:10], requests=1,
                     in_=inp or 0, out=outp or 0, aiu=aiu)
            _add_flat(out[name]["by_model"], model or "?", requests=1,
                      in_=inp or 0, out=outp or 0, aiu=aiu)
            _add_flat(out[name]["by_agent"], AGENT_CLI, requests=1,
                      in_=inp or 0, out=outp or 0, aiu=aiu)
            _add_flat(out[name]["by_am"], AGENT_CLI + AM_SEP + (model or "?"),
                      requests=1, in_=inp or 0, out=outp or 0, aiu=aiu)

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
        conn.close()
    except Exception:
        pass
    return out


def scan_claude() -> dict[str, dict]:
    """project -> metrics from ~/.claude/projects/<dir>/<session>.jsonl (Claude Code).

    Each .jsonl is one Claude Code session; ``assistant`` events carry the real
    model + token usage. Claude does not emit GitHub's AI-credit (AIU) metric,
    so aiu stays 0 — requests, input/output tokens, model and active days are
    all real recorded values (never estimated).
    """
    out: dict[str, dict] = defaultdict(_metrics)
    if not os.path.isdir(CLAUDE_ROOT):
        return out
    for path in glob.glob(os.path.join(CLAUDE_ROOT, "*", "*.jsonl")):
        name = ""
        rows: list[tuple[str, str, int, int]] = []
        first_date: str | None = None
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if '"assistant"' not in line:
                        continue
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    if ev.get("type") != "assistant":
                        continue
                    msg = ev.get("message") or {}
                    model = msg.get("model") or ""
                    if not model or model == "<synthetic>":
                        continue
                    if not name:
                        cwd = ev.get("cwd") or ""
                        if cwd and not is_junk_cwd(cwd):
                            name = project_name(cwd)
                    date = str(ev.get("timestamp") or "")[:10]
                    if not date:
                        continue
                    u = msg.get("usage") or {}
                    in_ = ((u.get("input_tokens") or 0)
                           + (u.get("cache_creation_input_tokens") or 0)
                           + (u.get("cache_read_input_tokens") or 0))
                    out_ = u.get("output_tokens") or 0
                    rows.append((date, model, in_, out_))
                    if first_date is None or date < first_date:
                        first_date = date
        except Exception:
            continue
        if not name or not rows:
            continue
        m = out[name]
        for date, model, in_, out_ in rows:
            _add_day(m, date, requests=1, in_=in_, out=out_)
            _add_flat(m["by_model"], model, requests=1, in_=in_, out=out_)
            _add_flat(m["by_agent"], AGENT_CLAUDE, requests=1, in_=in_, out=out_)
            _add_flat(m["by_am"], AGENT_CLAUDE + AM_SEP + model, requests=1, in_=in_, out=out_)
        if first_date:
            _add_day(m, first_date, sessions=1)
    return out


# --------------------------------------------------------------------------- #
# Build + write
# --------------------------------------------------------------------------- #
def diagnostics() -> dict:
    """What the extractor can actually see locally. Used by the *GHCP Usage:
    Diagnostics* command to explain why token/AIU data may be missing on a
    machine: it reports which VS Code roots were scanned and, critically, how
    many logs still carry the token/credit fields the dashboard needs
    (``inputTokens`` in debug-logs; ``promptTokens``/``copilotCredits`` in
    chatSessions). Log level is irrelevant \u2014 this is about what was retained.
    """
    info: dict = {
        "appdata": APPDATA,
        "vscode_variants": [],
        "roots": [],
        "workspaces": 0,
        "debug_log_sessions": 0,
        "main_jsonl_with_tokens": 0,
        "chat_files": 0,
        "chat_files_with_tokens": 0,
    }
    if APPDATA and os.path.isdir(APPDATA):
        for d in os.scandir(APPDATA):
            if d.is_dir() and d.name.lower().startswith("code"):
                info["vscode_variants"].append(d.name)
    for vs_root, _db in _vs_variants():
        info["roots"].append({"path": vs_root, "exists": os.path.isdir(vs_root)})
        if not os.path.isdir(vs_root):
            continue
        info["workspaces"] += len(glob.glob(os.path.join(vs_root, "*", "workspace.json")))
        for mj in glob.glob(os.path.join(
                vs_root, "*", "GitHub.copilot-chat", "debug-logs", "*", "main.jsonl")):
            info["debug_log_sessions"] += 1
            try:
                with open(mj, encoding="utf-8", errors="replace") as fh:
                    if any("inputTokens" in ln for ln in fh):
                        info["main_jsonl_with_tokens"] += 1
            except Exception:
                pass
        for cf in (glob.glob(os.path.join(vs_root, "*", "chatSessions", "*.json"))
                   + glob.glob(os.path.join(vs_root, "*", "chatSessions", "*.jsonl"))):
            info["chat_files"] += 1
            try:
                with open(cf, encoding="utf-8", errors="replace") as fh:
                    head = fh.read(300_000)
                if "promptTokens" in head or "copilotCredits" in head:
                    info["chat_files_with_tokens"] += 1
            except Exception:
                pass
    info["has_token_data"] = (info["main_jsonl_with_tokens"] > 0
                              or info["chat_files_with_tokens"] > 0)
    return info


def _generated_stamp() -> str:
    """Local build time like '24/7/2026, 4:10:13 pm'."""
    now = datetime.datetime.now()
    h12 = now.hour % 12 or 12
    ampm = "am" if now.hour < 12 else "pm"
    return f"{now.day}/{now.month}/{now.year}, {h12}:{now.minute:02d}:{now.second:02d} {ampm}"


def write_dashboard(projects: list[dict]) -> None:
    os.makedirs(OUT, exist_ok=True)
    html = (DASHBOARD_TEMPLATE
            .replace("__DATA__", json.dumps(projects))
            .replace("__GENERATED__", _generated_stamp()))
    with open(os.path.join(OUT, "dashboard.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(OUT, "projects.json"), "w", encoding="utf-8") as f:
        json.dump(projects, f, indent=2)


def main() -> None:
    if "--diagnostics" in sys.argv:
        print(json.dumps(diagnostics(), indent=2))
        return
    vs = scan_vscode()
    cli = scan_cli()
    claude = scan_claude()
    projects = build_projects(vs, cli, claude)
    write_dashboard(projects)

    days: set[str] = set()
    sess = req = 0
    aiu = 0.0
    for p in projects:
        for client in (p["vscode"], p["cli"], p["claude"]):
            for date, b in client["by_day"].items():
                days.add(date)
                sess += b["sessions"]
                req += b["requests"]
                aiu += b["aiu"]
    print(f"projects: {len(projects)}  | sessions: {sess}  | requests: {req}  | "
          f"aiu: {round(aiu, 2)}  | active days: {len(days)}")
    print("dashboard -> out/dashboard.html   data -> out/projects.json")


if __name__ == "__main__":
    main()
