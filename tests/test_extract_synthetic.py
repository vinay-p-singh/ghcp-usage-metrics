"""End-to-end golden-master over a synthetic log tree.

Builds a tiny but complete fixture for all four surfaces (VS Code debug-logs +
session-store.db + chatSessions, CLI session-store.db, Claude JSONL), points the
usage.py module constants at it, runs the real scanners + build_projects, and
asserts BOTH exact hand-computed aggregates AND the structural invariants that
future refactors must preserve:

  * per client:  sum(by_day.aiu) == sum(by_model.aiu) == sum(by_agent.aiu) == sum(by_am.aiu)
  * by_am re-sums to by_agent and by_model on every key
  * dedup: a chatSessions file whose sid already has a debug-log is NOT counted
  * subagent child logs attribute to their own agent, not the parent
  * SKILL.md reads attribute exact counts + the session's token totals
"""
from __future__ import annotations

import datetime
import json
import os
import sqlite3

import pytest

import usage


def _ms(y: int, m: int, d: int, hh: int = 12) -> int:
    return int(datetime.datetime(y, m, d, hh, tzinfo=datetime.timezone.utc)
               .timestamp() * 1000)


DAY0, DAY1, DAY2 = "2026-05-01", "2026-05-02", "2026-05-03"


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _billing_line(day_ms: int, in_: int, out: int, model: str, nano: int | None) -> str:
    attrs: dict = {"inputTokens": in_, "outputTokens": out, "model": model}
    if nano is not None:
        attrs["copilotUsageNanoAiu"] = nano
    return json.dumps({"type": "llm_request", "ts": day_ms, "attrs": attrs})


def _build_vscode(root: str, db_path: str) -> None:
    ws = os.path.join(root, "ws1")
    _write(os.path.join(ws, "workspace.json"),
           json.dumps({"folder": "file:///C:/proj/alpha"}))
    dbg = os.path.join(ws, "GitHub.copilot-chat", "debug-logs")

    # s1: two billing events (day1) + one tool_call, no children
    _write(os.path.join(dbg, "s1", "main.jsonl"),
           _billing_line(_ms(2026, 5, 2), 100, 20, "gpt-x", 5_000_000_000) + "\n"
           + _billing_line(_ms(2026, 5, 2), 200, 40, "gpt-x", 3_000_000_000) + "\n"
           + json.dumps({"type": "tool_call", "attrs": {"name": "read_file"}}) + "\n")

    # s2: one billing event (day1) + a child_session_ref to a runSubagent log
    _write(os.path.join(dbg, "s2", "main.jsonl"),
           _billing_line(_ms(2026, 5, 2), 50, 10, "gpt-x", 1_000_000_000) + "\n"
           + json.dumps({"type": "child_session_ref",
                         "attrs": {"childLogFile": "runSubagent-Researcher-c1.jsonl",
                                   "label": "runSubagent-Researcher"}}) + "\n")
    # subagent child log (day2, different model) -> agent "Researcher"
    _write(os.path.join(dbg, "s2", "runSubagent-Researcher-c1.jsonl"),
           _billing_line(_ms(2026, 5, 3), 500, 100, "claude", 2_000_000_000) + "\n")

    # chatSessions: s1 must be SKIPPED (already in debug-logs); s3 is new/older
    chat = os.path.join(ws, "chatSessions")
    _write(os.path.join(chat, "s1.json"), json.dumps({
        "sessionId": "s1",
        "requests": [{"timestamp": _ms(2026, 5, 2), "promptTokens": 9999,
                      "completionTokens": 9999, "copilotCredits": 99.0,
                      "modelId": "copilot/gpt-x"}]}))
    _write(os.path.join(chat, "s3.json"), json.dumps({
        "sessionId": "s3", "creationDate": _ms(2026, 5, 1),
        "requests": [{"timestamp": _ms(2026, 5, 1), "promptTokens": 10,
                      "completionTokens": 2, "copilotCredits": 0.5,
                      "modelId": "copilot/gpt-x"}]}))

    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE sessions (id TEXT, repository TEXT, agent_name TEXT, cwd TEXT)")
    conn.executemany(
        "INSERT INTO sessions (id, repository, agent_name, cwd) VALUES (?,?,?,?)",
        [("s1", "https://github.com/acme/alpha", None, ""),
         ("s2", "https://github.com/acme/alpha", None, ""),
         ("s3", "https://github.com/acme/alpha", None, "")])
    conn.execute("CREATE TABLE session_files "
                 "(id INTEGER, session_id TEXT, file_path TEXT, tool_name TEXT, turn_index INTEGER)")
    conn.execute(
        "INSERT INTO session_files (id, session_id, file_path) VALUES (?,?,?)",
        (1, "s1", "C:/x/skills/web-artifacts-builder/SKILL.md"))
    conn.commit()
    conn.close()


def _build_cli(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE sessions (id TEXT, repository TEXT, cwd TEXT, created_at TEXT)")
    conn.executemany(
        "INSERT INTO sessions (id, repository, cwd, created_at) VALUES (?,?,?,?)",
        [("cs1", "https://github.com/acme/beta", "", "2026-07-10T09:00:00Z"),
         ("cs2", "https://github.com/acme/beta", "", "2026-07-05T09:00:00Z")])
    conn.execute("CREATE TABLE assistant_usage_events "
                 "(session_id TEXT, input_tokens INT, output_tokens INT, "
                 "total_nano_aiu INT, model TEXT, created_at TEXT)")
    conn.execute(
        "INSERT INTO assistant_usage_events VALUES (?,?,?,?,?,?)",
        ("cs1", 1000, 200, 4_000_000_000, "gpt-cli", "2026-07-10T09:00:00Z"))
    conn.execute("CREATE TABLE turns (session_id TEXT, timestamp TEXT)")
    conn.executemany(
        "INSERT INTO turns VALUES (?,?)",
        [("cs1", "2026-07-10T09:05:00Z"),   # same day as real -> skipped
         ("cs2", "2026-07-05T09:05:00Z")])  # pre-telemetry -> recovered
    conn.commit()
    conn.close()


def _build_claude(root: str) -> None:
    line = json.dumps({
        "type": "assistant",
        "message": {"model": "claude-3",
                    "usage": {"input_tokens": 100, "cache_creation_input_tokens": 10,
                              "cache_read_input_tokens": 5, "output_tokens": 20}},
        "timestamp": "2026-06-01T10:00:00Z", "cwd": "C:/proj/gamma"})
    _write(os.path.join(root, "gammaproj", "sess.jsonl"), line + "\n")


@pytest.fixture()
def projects(tmp_path, monkeypatch):
    vs_root = tmp_path / "vs"
    vs_db = tmp_path / "vs.db"
    cli_home = tmp_path / "cli"
    claude_root = tmp_path / "claude"
    cli_home.mkdir()
    _build_vscode(str(vs_root), str(vs_db))
    _build_cli(str(cli_home / "session-store.db"))
    _build_claude(str(claude_root))

    monkeypatch.setattr(usage, "VS_ROOT", str(vs_root))
    monkeypatch.setattr(usage, "VS_DB", str(vs_db))
    monkeypatch.setattr(usage, "CLI_HOME", str(cli_home))
    monkeypatch.setattr(usage, "CLAUDE_ROOT", str(claude_root))
    monkeypatch.setattr(usage, "CACHE", str(tmp_path / "cache.json"))

    vs = usage.scan_vscode()
    cli = usage.scan_cli()
    claude = usage.scan_claude()
    return {p["name"]: p for p in usage.build_projects(vs, cli, claude)}


def _sum(dim: dict, field: str) -> float:
    return sum(b[field] for b in dim.values())


def _assert_cross_dim_invariant(client: dict) -> None:
    """The core no-double-count guard: every dimension must total the same AIU."""
    a = round(_sum(client["by_day"], "aiu"), 4)
    for dim in ("by_model", "by_agent", "by_am"):
        assert round(_sum(client[dim], "aiu"), 4) == a, dim
    # and by_am must re-sum to by_agent + by_model per key
    ag: dict = {}
    md: dict = {}
    for key, b in client["by_am"].items():
        agent, model = key.split(usage._AM_SEP, 1)
        ag[agent] = ag.get(agent, 0.0) + b["aiu"]
        md[model] = md.get(model, 0.0) + b["aiu"]
    for agent, v in ag.items():
        assert round(v, 4) == round(client["by_agent"][agent]["aiu"], 4)
    for model, v in md.items():
        assert round(v, 4) == round(client["by_model"][model]["aiu"], 4)


class TestSynthetic:
    def test_project_set(self, projects):
        assert set(projects) == {"acme/alpha", "acme/beta", "gamma"}

    def test_vscode_totals_exact(self, projects):
        vs = projects["acme/alpha"]["vscode"]
        assert _sum(vs["by_day"], "requests") == 5   # 2 (s1) + 1 (s2) + 1 (child) + 1 (s3)
        assert _sum(vs["by_day"], "in") == 860        # 300 + 50 + 500 + 10
        assert _sum(vs["by_day"], "out") == 172       # 60 + 10 + 100 + 2
        assert round(_sum(vs["by_day"], "aiu"), 4) == 11.5  # 8 + 1 + 2 + 0.5
        assert _sum(vs["by_day"], "sessions") == 3
        assert set(vs["by_day"]) == {DAY0, DAY1, DAY2}

    def test_dedup_chatsession_not_double_counted(self, projects):
        # s1.json carried 9999 tokens; it must be skipped because s1 has a debug-log.
        vs = projects["acme/alpha"]["vscode"]
        assert _sum(vs["by_day"], "in") < 9999

    def test_subagent_attribution(self, projects):
        vs = projects["acme/alpha"]["vscode"]
        assert "Researcher" in vs["by_agent"]
        assert vs["by_agent"]["Researcher"]["requests"] == 1
        assert round(vs["by_agent"]["Researcher"]["aiu"], 4) == 2.0
        # base agent got everything except the child
        assert vs["by_agent"]["GitHub Copilot Chat"]["requests"] == 4

    def test_skill_attribution(self, projects):
        vs = projects["acme/alpha"]["vscode"]
        sk = vs["by_skill"]["web-artifacts-builder"]
        assert sk["reads"] == 1
        assert sk["sessions"] == 1
        assert sk["requests"] == 2        # s1's session total (main only, no child)
        assert round(sk["aiu"], 4) == 8.0

    def test_tool_counts(self, projects):
        vs = projects["acme/alpha"]["vscode"]
        assert vs["by_tool"]["read_file"] == 1

    def test_cli_totals(self, projects):
        cli = projects["acme/beta"]["cli"]
        assert _sum(cli["by_day"], "requests") == 2   # 1 real event + 1 recovered turn
        assert _sum(cli["by_day"], "in") == 1000
        assert round(_sum(cli["by_day"], "aiu"), 4) == 4.0
        assert "Copilot CLI" in cli["by_agent"]

    def test_claude_totals(self, projects):
        cla = projects["gamma"]["claude"]
        assert _sum(cla["by_day"], "requests") == 1
        assert _sum(cla["by_day"], "in") == 115       # 100 + 10 + 5
        assert _sum(cla["by_day"], "out") == 20
        assert round(_sum(cla["by_day"], "aiu"), 4) == 0.0  # Claude emits no AIU
        assert "Claude Code" in cla["by_agent"]

    def test_cross_dimension_invariant_all_projects(self, projects):
        for p in projects.values():
            for surface in ("vscode", "cli", "claude"):
                _assert_cross_dim_invariant(p[surface])
