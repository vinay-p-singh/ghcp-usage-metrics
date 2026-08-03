"""Parsing and memoising VS Code request logs.

The billing logs are the expensive part of a scan: hundreds of files, tens of
megabytes each. Every summary is cached by path + size + mtime so a re-scan
costs almost nothing, and the cold case is parallelised.

Nothing here is estimated. A request that predates AI-credit reporting
contributes its real tokens and adds zero credits.
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ProcessPoolExecutor

from ghcp.constants import AM_SEP
from ghcp.diagnostics import diag_err, src
from ghcp.model import _add_day, _add_flat, _flatbucket
from ghcp.normalize import _utc_date_ms
from ghcp.window import in_window

# Bumped whenever a summary gains a field. A record from an older version is
# re-parsed rather than trusted, so a stale cache cannot silently omit a measure.
CACHE_VERSION = 2


def load_cache(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(path: str, cache: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception:
        pass


def billing_for_file(path: str, cache: dict) -> dict:
    """Per-day llm billing from one main.jsonl, memoised by path + size + mtime.

    Counts every request that carries ``inputTokens`` (real input/output tokens)
    and sums ``copilotUsageNanoAiu`` where GitHub reported it. ``cachedTokens``
    is part of the input, not extra, and only exists on requests logged after
    cache reporting began -- ``cached_req`` counts how many said so, so a silent
    zero is never mistaken for a measured one. Nothing is estimated: requests
    logged before AIU reporting existed contribute their real tokens and simply
    add 0 AIU.

    Returns {"v", "size", "mtime",
             "by_day": {date: {requests, in, out, aiu, cached, cached_req}},
             "by_model": {model: {...}},
             "by_dm": {date+SEP+model: {...}},
             "tools": {tool_name: count},          # from tool_call events
             "childrefs": {childLogFile: label},   # subagent/title child logs
             "bad": int}                           # unparseable lines, skipped
    """
    st = os.stat(path)
    hit = cache.get(path)
    if (hit and hit.get("size") == st.st_size
            and hit.get("mtime") == int(st.st_mtime)
            and hit.get("v") == CACHE_VERSION):
        return hit
    by_day: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    by_dm: dict[str, dict] = {}
    childrefs: dict[str, str] = {}
    tools: dict[str, int] = {}
    bad = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if ("inputTokens" not in line and "child_session_ref" not in line
                    and "tool_call" not in line):
                continue
            try:
                ev = json.loads(line)
            except Exception:
                bad += 1
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
            model = a.get("model")
            if not model:
                # Never seen in practice. If it starts happening the log format
                # has changed, and that is worth being told about -- the caller
                # turns this into a diagnostics entry, not a crash.
                raise ValueError(f"billing event carries tokens but no model: {a!r}")
            nano = a.get("copilotUsageNanoAiu")
            aiu = (nano / 1e9) if nano is not None else 0.0
            ct = a.get("cachedTokens")
            cached = ct or 0
            cached_req = 1 if ct is not None else 0
            d = by_day.setdefault(_utc_date_ms(ts), _flatbucket())
            mm = by_model.setdefault(model, _flatbucket())
            dm = by_dm.setdefault(_utc_date_ms(ts) + AM_SEP + model, _flatbucket())
            for b in (d, mm, dm):
                b["requests"] += 1
                b["in"] += it
                b["out"] += ot
                b["aiu"] += aiu
                b["cached"] += cached
                b["cached_req"] += cached_req
    rec = {"v": CACHE_VERSION, "size": st.st_size, "mtime": int(st.st_mtime),
           "by_day": by_day, "by_model": by_model, "by_dm": by_dm, "tools": tools,
           "childrefs": childrefs, "bad": bad}
    cache[path] = rec
    return rec


def apply_billing(m: dict, agent: str, rec: dict) -> tuple[int, int, int, float]:
    """Fold one main/child ``billing_for_file`` record into a project's metrics,
    attributing every request's tokens to the display ``agent``. Updates by_day,
    by_tool, by_model, by_am and (once) by_agent; returns this log's
    ``(requests, input, output, aiu)`` totals so the caller can track the
    session-wide total across the parent and all its child logs.
    """
    for date, b in rec.get("by_day", {}).items():
        _add_day(m, date, requests=b["requests"], in_=b["in"],
                 out=b["out"], aiu=b["aiu"], cached=b.get("cached", 0),
                 cached_req=b.get("cached_req", 0))
    for tname, tc in rec.get("tools", {}).items():
        m["by_tool"][tname] += tc
    req = in_ = out = 0
    aiu = 0.0
    for model, b in rec.get("by_model", {}).items():
        for bucket, key in ((m["by_model"], model),
                            (m["by_am"], agent + AM_SEP + model)):
            _add_flat(bucket, key, requests=b["requests"], in_=b["in"],
                      out=b["out"], aiu=b["aiu"], cached=b.get("cached", 0),
                      cached_req=b.get("cached_req", 0))
        req += b["requests"]
        in_ += b["in"]
        out += b["out"]
        aiu += b["aiu"]
    for key, b in rec.get("by_dm", {}).items():
        _add_flat(m["by_dm"], key, requests=b["requests"], in_=b["in"],
                  out=b["out"], aiu=b["aiu"], cached=b.get("cached", 0),
                  cached_req=b.get("cached_req", 0))
    if req:
        _add_flat(m["by_agent"], agent, requests=req, in_=in_, out=out, aiu=aiu,
                  cached=sum(b.get("cached", 0)
                             for b in rec.get("by_model", {}).values()),
                  cached_req=sum(b.get("cached_req", 0)
                                 for b in rec.get("by_model", {}).values()))
    return req, in_, out, aiu


def _bill_parse(path: str):
    """Pool worker: parse one billing file fresh (no cache) for the prewarm.

    Returns ``(path, rec)`` -- ``rec`` is the small per-day/per-model summary
    ``billing_for_file`` produces, or ``None`` on any read/parse error.
    """
    try:
        return path, billing_for_file(path, {})
    except Exception:
        return path, None


def cache_hit(cache: dict, path: str) -> bool:
    """True when ``cache`` already holds a current summary for ``path``."""
    try:
        st = os.stat(path)
    except OSError:
        return True  # unreadable now; let the sequential pass handle/skip it
    hit = cache.get(path)
    return bool(hit and hit.get("size") == st.st_size
                and hit.get("mtime") == int(st.st_mtime)
                and hit.get("v") == CACHE_VERSION)


def prewarm(cache: dict, roots: list[str]) -> None:
    """Parallel-parse every debug-log ``*.jsonl`` whose cache entry is missing or
    stale, populating ``cache`` so the sequential scan below does no I/O for them.
    This is where the cold first-load time lives (hundreds of JSON logs). Output
    is identical to the sequential path -- only the cache is pre-filled. Silently
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
                            and not cache_hit(cache, cf.path)
                            and in_window(cf.path)):
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


def billing_or_defer(path: str, cache: dict) -> dict:
    """Billing record for one request log, honouring the quick window.

    Already-memoised logs are always used (re-reading the cache is free); an
    uncached log outside the window is deferred to the full pass and counted,
    so a partial report can say exactly how much it left on the table.
    """
    s = src("vscode_debug")
    s["files_found"] += 1
    if not (cache_hit(cache, path) or in_window(path)):
        s["files_deferred"] += 1
        return {}
    try:
        rec = billing_for_file(path, cache)
    except Exception as e:
        diag_err("vscode_debug", path, e)
        return {}
    s["files_parsed"] += 1
    s["bad_lines"] += rec.get("bad", 0)
    return rec
