"""The in-memory metrics model: per-client buckets, accumulation, merge, build.

A *client* (vscode / cli / claude) carries several parallel breakdowns of the
same activity:

  by_day    date  -> {sessions, requests, in, out, aiu, cached, cached_req}
  by_model  model -> {requests, in, out, aiu, cached, cached_req}
  by_agent  agent -> {requests, in, out, aiu, cached, cached_req}
  by_am     f"{agent}{AM_SEP}{model}" -> {requests, in, out, aiu, cached, cached_req}
  by_dm     f"{date}{AM_SEP}{model}"  -> {requests, in, out, aiu, cached, cached_req}
  by_sdm    f"{session}{AM_SEP}{date}{AM_SEP}{model}" -> same measures
  by_skill  skill -> {reads, sessions, requests, in, out, aiu}
  by_tool   tool  -> count
  by_lang   lang  -> count
  session_names  session -> the name its source recorded, when it recorded one

Every AIU total must agree across by_day / by_model / by_agent / by_am / by_dm
-- that invariant is what the test-suite guards.

``by_dm`` exists so the dashboard can filter by model and still re-scope the
day-level figures. The logs record the date and the model on the same event;
keeping only the two separate aggregates threw that pairing away, which is what
used to make a model filter unable to move the headline numbers. ``by_sdm``
adds the session to that same pairing, so it is the finest grain recorded and
every coarser dimension is a projection of it.

A session spans days and models, so ``by_sdm`` deliberately carries no
``sessions`` count: distinctness comes from its key, never from summing a
measure.

``cached`` is a subset of ``in``, not an addition to it -- every harness reports
cache as part of the input it already counted. ``cached_req`` records how many
of those requests reported a cache figure at all, because cache reporting only
started part-way through the recorded history and "not reported" must stay
distinguishable from "nothing was cached". Tokens that missed the cache are
``in - cached`` and are derived when displayed rather than stored.
"""
from __future__ import annotations

from collections import defaultdict

from ghcp.naming import _canon

DAY_FIELDS = ("sessions", "requests", "in", "out", "aiu", "cached", "cached_req")
FLAT_FIELDS = ("requests", "in", "out", "aiu", "cached", "cached_req")
SKILL_FIELDS = ("reads", "sessions", "requests", "in", "out", "aiu")
# A name long enough to recognise the work, short enough not to dominate the file.
NAME_CAP = 120


def _daybucket() -> dict:
    return {"sessions": 0, "requests": 0, "in": 0, "out": 0, "aiu": 0.0,
            "cached": 0, "cached_req": 0}


def _flatbucket() -> dict:
    return {"requests": 0, "in": 0, "out": 0, "aiu": 0.0,
            "cached": 0, "cached_req": 0}


def _skillbucket() -> dict:
    # ``reads`` = exact SKILL.md read count (invocations); ``sessions`` = distinct
    # sessions that used the skill; requests/in/out/aiu = summed totals of those
    # sessions (a session's tokens count toward every skill it invoked).
    return {"reads": 0, "sessions": 0, "requests": 0, "in": 0, "out": 0, "aiu": 0.0}


def _metrics() -> dict:
    """Per-client metrics bucketed by day, model, agent, agent×model and skill.

    Named subagents launched via the ``runSubagent`` tool write their own
    ``runSubagent-<name>-<sid>.jsonl`` child log next to the parent session's
    ``main.jsonl``; their real tokens/AIU are read from those child logs and
    attributed to ``by_agent[<name>]``.
    """
    return {"by_day": defaultdict(_daybucket),
            "by_model": defaultdict(_flatbucket),
            "by_agent": defaultdict(_flatbucket),
            "by_am": defaultdict(_flatbucket),
            "by_dm": defaultdict(_flatbucket),
            "by_sdm": defaultdict(_flatbucket),
            "by_skill": defaultdict(_skillbucket),
            "by_tool": defaultdict(int),
            "by_lang": defaultdict(int),
            "session_names": {}}


def _add_day(m: dict, date: str, sessions: int = 0, requests: int = 0,
             in_: int = 0, out: int = 0, aiu: float = 0.0,
             cached: int = 0, cached_req: int = 0) -> None:
    b = m["by_day"][date]
    b["sessions"] += sessions
    b["requests"] += requests
    b["in"] += in_
    b["out"] += out
    b["aiu"] += aiu
    b["cached"] += cached
    b["cached_req"] += cached_req


def _add_flat(bucket: dict, key: str, requests: int = 0, in_: int = 0,
              out: int = 0, aiu: float = 0.0, cached: int = 0,
              cached_req: int = 0) -> None:
    b = bucket[key]
    b["requests"] += requests
    b["in"] += in_
    b["out"] += out
    b["aiu"] += aiu
    b["cached"] += cached
    b["cached_req"] += cached_req


def name_session(m: dict, sid: str, name: str | None) -> None:
    """Record a session's name, when its source wrote one. Absent stays absent --
    an unnamed session is shown by its id rather than given an invented name."""
    if not sid or not name:
        return
    text = str(name).strip()
    if text:
        m["session_names"][sid] = text[:NAME_CAP]


def _merge(d: dict, members: list[str]) -> dict:
    """Sum per-day, per-model, per-agent, per-am and per-skill metrics across
    members (project names that share a canonical basename)."""
    by_day: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    by_agent: dict[str, dict] = {}
    by_am: dict[str, dict] = {}
    by_dm: dict[str, dict] = {}
    by_sdm: dict[str, dict] = {}
    by_skill: dict[str, dict] = {}
    by_tool: dict[str, int] = {}
    by_lang: dict[str, int] = {}
    session_names: dict[str, str] = {}
    for m in members:
        x = d.get(m)
        if not x:
            continue
        for date, b in x["by_day"].items():
            t = by_day.setdefault(date, _daybucket())
            for f in DAY_FIELDS:
                t[f] += b[f]
        for dim_src, dim_dst in (("by_model", by_model), ("by_agent", by_agent),
                                 ("by_am", by_am), ("by_dm", by_dm),
                                 ("by_sdm", by_sdm)):
            for key, b in x.get(dim_src, {}).items():
                t = dim_dst.setdefault(key, _flatbucket())
                for f in FLAT_FIELDS:
                    t[f] += b[f]
        for key, b in x.get("by_skill", {}).items():
            t = by_skill.setdefault(key, _skillbucket())
            for f in SKILL_FIELDS:
                t[f] += b.get(f, 0)
        for dim_src, dim_dst in (("by_tool", by_tool), ("by_lang", by_lang)):
            for key, c in x.get(dim_src, {}).items():
                dim_dst[key] = dim_dst.get(key, 0) + c
        session_names.update(x.get("session_names", {}))
    for grp in (by_day, by_model, by_agent, by_am, by_dm, by_sdm, by_skill):
        for b in grp.values():
            b["aiu"] = round(b["aiu"], 4)
    return {"by_day": by_day, "by_model": by_model, "by_agent": by_agent,
            "by_am": by_am, "by_dm": by_dm, "by_sdm": by_sdm,
            "by_skill": by_skill,
            "by_tool": by_tool, "by_lang": by_lang,
            "session_names": session_names}


def _sessions(client: dict) -> int:
    return sum(b["sessions"] for b in client["by_day"].values())


def build_projects(vs: dict[str, dict], cli: dict[str, dict],
                   claude: dict[str, dict]) -> list[dict]:
    """Merge names that share a repo basename; label with the fullest slug."""
    groups: dict[str, list[str]] = defaultdict(list)
    for n in set(vs) | set(cli) | set(claude):
        groups[_canon(n)].append(n)

    def sess(m: str) -> int:
        return ((_sessions(vs[m]) if m in vs else 0)
                + (_sessions(cli[m]) if m in cli else 0)
                + (_sessions(claude[m]) if m in claude else 0))

    rows = []
    for members in groups.values():
        label = max(members, key=lambda m: ("/" in m, sess(m), m))
        rows.append({"name": label,
                     "vscode": _merge(vs, members),
                     "cli": _merge(cli, members),
                     "claude": _merge(claude, members)})
    rows.sort(key=lambda r: (-(_sessions(r["vscode"]) + _sessions(r["cli"])
                              + _sessions(r["claude"])),
                             r["name"].lower()))
    return rows
