"""Compact queries over the GHCP usage extract (``out/projects.json``).

The report is ~130 KB of nested JSON; reading it wholesale into a chat context
is wasteful. Each subcommand here prints one small table instead.

Only values the extractor recorded are printed — nothing is estimated.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

CLIENTS = ("vscode", "cli", "claude")
HARNESS_LABEL = {"vscode": "VS Code", "cli": "Copilot CLI", "claude": "Claude Code"}
NO_TOKEN = "(no token data)"


def find_repo() -> str | None:
    """Env override, else walk up from cwd looking for usage.py."""
    env = os.environ.get("GHCP_USAGE_REPO")
    if env:
        return env
    cur = os.path.abspath(os.getcwd())
    while True:
        if os.path.isfile(os.path.join(cur, "usage.py")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def load(data_path: str | None) -> list[dict]:
    if data_path:
        path = data_path
    else:
        repo = find_repo()
        if not repo:
            sys.exit("Could not locate the extractor. Run this from inside the "
                     "ghcp-usage-metrics checkout, set GHCP_USAGE_REPO, or pass --data.")
        path = os.path.join(repo, "out", "projects.json")
    if not os.path.isfile(path):
        sys.exit(f"No extract at {path}\nRun: python usage.py")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fmt(n: float) -> str:
    return f"{int(n):,}"


def faiu(x: float) -> str:
    return f"{x:,.1f}"


def in_range(date: str, args: argparse.Namespace) -> bool:
    if args.since and date < args.since:
        return False
    if args.until and date > args.until:
        return False
    return True


def day_totals(rows: list[dict], args: argparse.Namespace,
               clients: tuple[str, ...] = CLIENTS) -> dict:
    """Sum by_day across the selected projects/harnesses, honouring the date range."""
    t = {"sessions": 0, "requests": 0, "in": 0, "out": 0, "aiu": 0.0, "days": set()}
    for p in rows:
        for c in clients:
            for date, b in p[c]["by_day"].items():
                if not in_range(date, args):
                    continue
                t["days"].add(date)
                for f in ("sessions", "requests", "in", "out", "aiu"):
                    t[f] += b[f]
    return t


def acc_dim(rows: list[dict], dim: str, fields: tuple[str, ...]) -> dict:
    """Aggregate a lifetime dimension (by_model / by_agent / by_skill)."""
    out: dict[str, dict] = {}
    for p in rows:
        for c in CLIENTS:
            for key, b in p[c].get(dim, {}).items():
                t = out.setdefault(key, dict.fromkeys(fields, 0))
                for f in fields:
                    t[f] += b.get(f, 0)
    return out


def table(headers: list[str], rows: list[list[str]]) -> None:
    if not rows:
        print("(nothing recorded)")
        return
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(line)
    print("  ".join("-" * w for w in widths))
    for r in rows:
        cells = [r[0].ljust(widths[0])] + [r[i].rjust(widths[i]) for i in range(1, len(r))]
        print("  ".join(cells))


def pick(rows: list[dict], needle: str) -> list[dict]:
    n = needle.lower()
    return [p for p in rows if n in p["name"].lower()]


def cmd_summary(rows: list[dict], args: argparse.Namespace) -> None:
    t = day_totals(rows, args)
    days = sorted(t["days"])
    active = [p for p in rows if day_totals([p], args)["requests"] > 0]
    print(f"projects       {len(rows)} ({len(active)} with requests)")
    print(f"sessions       {fmt(t['sessions'])}")
    print(f"requests       {fmt(t['requests'])}")
    print(f"AIU            {faiu(t['aiu'])}")
    print(f"input tokens   {fmt(t['in'])}")
    print(f"output tokens  {fmt(t['out'])}")
    print(f"active days    {len(days)}" + (f"  ({days[0]} .. {days[-1]})" if days else ""))
    print()
    table(["harness", "sessions", "requests", "AIU"],
          [[HARNESS_LABEL[c],
            fmt(day_totals(rows, args, (c,))["sessions"]),
            fmt(day_totals(rows, args, (c,))["requests"]),
            faiu(day_totals(rows, args, (c,))["aiu"])] for c in CLIENTS])


def cmd_projects(rows: list[dict], args: argparse.Namespace) -> None:
    scored = []
    for p in rows:
        t = day_totals([p], args)
        if t["requests"]:
            scored.append((p["name"], t))
    scored.sort(key=lambda x: -x[1]["aiu"])
    table(["project", "sessions", "requests", "AIU"],
          [[n, fmt(t["sessions"]), fmt(t["requests"]), faiu(t["aiu"])]
           for n, t in scored[:args.top]])


def cmd_agents(rows: list[dict], args: argparse.Namespace) -> None:
    agg = acc_dim(rows, "by_agent", ("requests", "in", "out", "aiu"))
    items = sorted(agg.items(), key=lambda kv: -kv[1]["aiu"])
    table(["agent", "requests", "AIU", "AIU/req", "input", "output"],
          [[k, fmt(v["requests"]), faiu(v["aiu"]),
            faiu(v["aiu"] / v["requests"]) if v["requests"] else "-",
            fmt(v["in"]), fmt(v["out"])] for k, v in items])
    print("\nLifetime totals — the date range does not apply to this breakdown.")


def cmd_models(rows: list[dict], args: argparse.Namespace) -> None:
    agg = acc_dim(rows, "by_model", ("requests", "in", "out", "aiu"))
    untracked = agg.pop(NO_TOKEN, None)
    items = sorted(agg.items(), key=lambda kv: -kv[1]["aiu"])
    table(["model", "requests", "AIU", "input", "output"],
          [[k, fmt(v["requests"]), faiu(v["aiu"]), fmt(v["in"]), fmt(v["out"])]
           for k, v in items])
    if untracked:
        print(f"\nPlus {fmt(untracked['requests'])} requests with no recorded model/tokens.")
    print("Lifetime totals — the date range does not apply to this breakdown.")


def cmd_skills(rows: list[dict], args: argparse.Namespace) -> None:
    agg = acc_dim(rows, "by_skill", ("reads", "sessions", "requests", "in", "out", "aiu"))
    items = sorted(agg.items(), key=lambda kv: -kv[1]["reads"])
    table(["skill", "invocations", "sessions", "AIU"],
          [[k, fmt(v["reads"]), fmt(v["sessions"]), faiu(v["aiu"])] for k, v in items])
    print("\nInvocations are exact SKILL.md reads. AIU is the total of the sessions that")
    print("used the skill, so a multi-skill session counts toward each skill it used.")


def cmd_daily(rows: list[dict], args: argparse.Namespace) -> None:
    per: dict[str, dict] = {}
    for p in rows:
        for c in CLIENTS:
            for date, b in p[c]["by_day"].items():
                if not in_range(date, args):
                    continue
                t = per.setdefault(date, {"sessions": 0, "requests": 0, "aiu": 0.0})
                for f in ("sessions", "requests", "aiu"):
                    t[f] += b[f]
    table(["date", "sessions", "requests", "AIU"],
          [[d, fmt(v["sessions"]), fmt(v["requests"]), faiu(v["aiu"])]
           for d, v in sorted(per.items())])


def cmd_project(rows: list[dict], args: argparse.Namespace) -> None:
    hits = pick(rows, args.name)
    if not hits:
        sys.exit(f"No project matching {args.name!r}. Try: query.py projects")
    if len(hits) > 1:
        print("Matches: " + ", ".join(p["name"] for p in hits) + "\n")
    for p in hits:
        t = day_totals([p], args)
        days = sorted(t["days"])
        print(f"== {p['name']}")
        print(f"   sessions {fmt(t['sessions'])} | requests {fmt(t['requests'])} | "
              f"AIU {faiu(t['aiu'])} | in {fmt(t['in'])} | out {fmt(t['out'])}")
        if days:
            print(f"   active {len(days)} days ({days[0]} .. {days[-1]})")
        for dim, label in (("by_model", "models"), ("by_agent", "agents")):
            agg = acc_dim([p], dim, ("requests", "aiu"))
            agg.pop(NO_TOKEN, None)
            top = sorted(agg.items(), key=lambda kv: -kv[1]["aiu"])[:6]
            if top:
                print(f"   {label}: " + ", ".join(
                    f"{k} ({faiu(v['aiu'])} AIU)" for k, v in top))
        print()


COMMANDS = {"summary": cmd_summary, "projects": cmd_projects, "agents": cmd_agents,
            "models": cmd_models, "skills": cmd_skills, "daily": cmd_daily,
            "project": cmd_project}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=sorted(COMMANDS))
    ap.add_argument("name", nargs="?", help="project name or substring (project command)")
    ap.add_argument("--data", help="path to projects.json")
    ap.add_argument("--since", help="earliest date, YYYY-MM-DD")
    ap.add_argument("--until", help="latest date, YYYY-MM-DD")
    ap.add_argument("--top", type=int, default=15, help="rows for the projects command")
    args = ap.parse_args()
    if args.command == "project" and not args.name:
        ap.error("the project command needs a project name")
    COMMANDS[args.command](load(args.data), args)


if __name__ == "__main__":
    main()
