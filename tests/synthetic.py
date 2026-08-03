"""Synthetic log tree shared by the extraction tests.

One fixture builder, used by both the hand-computed assertions and the golden
master. Keeping it in one place means the upcoming refactor has a single seam to
change: when the scanners stop reading module globals, only ``point_usage_at``
moves, and every assertion above it stays exactly as it was.
"""
from __future__ import annotations

import datetime
import json
import os
import sqlite3

import usage

DAY0, DAY1, DAY2 = "2026-05-01", "2026-05-02", "2026-05-03"


def ms(y: int, m: int, d: int, hh: int = 12) -> int:
    return int(datetime.datetime(y, m, d, hh, tzinfo=datetime.timezone.utc)
               .timestamp() * 1000)


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def billing_line(day_ms: int, in_: int, out: int, model: str, nano: int | None,
                 cached: int | None = None) -> str:
    attrs: dict = {"inputTokens": in_, "outputTokens": out, "model": model}
    if nano is not None:
        attrs["copilotUsageNanoAiu"] = nano
    if cached is not None:
        attrs["cachedTokens"] = cached
    return json.dumps({"type": "llm_request", "ts": day_ms, "attrs": attrs})


def build_vscode(root: str, db_path: str) -> None:
    ws = os.path.join(root, "ws1")
    write(os.path.join(ws, "workspace.json"),
          json.dumps({"folder": "file:///C:/proj/alpha"}))
    dbg = os.path.join(ws, "GitHub.copilot-chat", "debug-logs")

    # s1: two billing events (day1) + one tool_call, no children. The first event
    # predates cache reporting and carries no cachedTokens at all -- that has to
    # stay distinguishable from a genuine zero.
    write(os.path.join(dbg, "s1", "main.jsonl"),
          billing_line(ms(2026, 5, 2), 100, 20, "gpt-x", 5_000_000_000) + "\n"
          + billing_line(ms(2026, 5, 2), 200, 40, "gpt-x", 3_000_000_000,
                         cached=150) + "\n"
          + json.dumps({"type": "tool_call", "attrs": {"name": "read_file"}}) + "\n")

    # s2: one billing event (day1) + a child_session_ref to a runSubagent log
    write(os.path.join(dbg, "s2", "main.jsonl"),
          billing_line(ms(2026, 5, 2), 50, 10, "gpt-x", 1_000_000_000) + "\n"
          + json.dumps({"type": "child_session_ref",
                        "attrs": {"childLogFile": "runSubagent-Researcher-c1.jsonl",
                                  "label": "runSubagent-Researcher"}}) + "\n")
    # subagent child log (day2, different model) -> agent "Researcher"
    write(os.path.join(dbg, "s2", "runSubagent-Researcher-c1.jsonl"),
          billing_line(ms(2026, 5, 3), 500, 100, "claude", 2_000_000_000) + "\n")

    # chatSessions: s1 must be SKIPPED (already in debug-logs); s3 is new/older
    chat = os.path.join(ws, "chatSessions")
    write(os.path.join(chat, "s1.json"), json.dumps({
        "sessionId": "s1",
        "requests": [{"timestamp": ms(2026, 5, 2), "promptTokens": 9999,
                      "completionTokens": 9999, "copilotCredits": 99.0,
                      "modelId": "copilot/gpt-x"}]}))
    write(os.path.join(chat, "s3.json"), json.dumps({
        "sessionId": "s3", "creationDate": ms(2026, 5, 1),
        "requests": [{"timestamp": ms(2026, 5, 1), "promptTokens": 10,
                      "completionTokens": 2, "copilotCredits": 0.5,
                      "modelId": "copilot/gpt-x"}]}))
    # s4 records its counts only under result.metadata, as some retained
    # sessions do -- reading just the top level would score this as zero.
    write(os.path.join(chat, "s4.json"), json.dumps({
        "sessionId": "s4", "creationDate": ms(2026, 5, 1),
        "requests": [{"timestamp": ms(2026, 5, 1), "modelId": "copilot/gpt-x",
                      "copilotCredits": 1.5,
                      "result": {"metadata": {"promptTokens": 700,
                                              "completionTokens": 40}}}]}))

    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE sessions (id TEXT, repository TEXT, agent_name TEXT, "
                 "cwd TEXT, summary TEXT)")
    conn.executemany(
        "INSERT INTO sessions (id, repository, agent_name, cwd, summary) "
        "VALUES (?,?,?,?,?)",
        [("s1", "https://github.com/acme/alpha", None, "", "Refactor the parser"),
         ("s2", "https://github.com/acme/alpha", None, "", None),
         ("s3", "https://github.com/acme/alpha", None, "", "x" * 400),
         ("s4", "https://github.com/acme/alpha", None, "", None)])
    conn.execute("CREATE TABLE session_files "
                 "(id INTEGER, session_id TEXT, file_path TEXT, tool_name TEXT, turn_index INTEGER)")
    conn.execute(
        "INSERT INTO session_files (id, session_id, file_path) VALUES (?,?,?)",
        (1, "s1", "C:/x/skills/web-artifacts-builder/SKILL.md"))
    conn.commit()
    conn.close()


def build_cli(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE sessions (id TEXT, repository TEXT, cwd TEXT, "
                 "created_at TEXT, summary TEXT)")
    conn.executemany(
        "INSERT INTO sessions (id, repository, cwd, created_at, summary) "
        "VALUES (?,?,?,?,?)",
        [("cs1", "https://github.com/acme/beta", "", "2026-07-10T09:00:00Z",
          "Wire up the billing query"),
         ("cs2", "https://github.com/acme/beta", "", "2026-07-05T09:00:00Z", None)])
    conn.execute("CREATE TABLE assistant_usage_events "
                 "(session_id TEXT, input_tokens INT, output_tokens INT, "
                 "total_nano_aiu INT, model TEXT, created_at TEXT, "
                 "cache_read_tokens INT, cache_write_tokens INT)")
    conn.execute(
        "INSERT INTO assistant_usage_events VALUES (?,?,?,?,?,?,?,?)",
        ("cs1", 1000, 200, 4_000_000_000, "gpt-cli", "2026-07-10T09:00:00Z",
         600, 100))
    conn.execute("CREATE TABLE turns (session_id TEXT, timestamp TEXT)")
    conn.executemany(
        "INSERT INTO turns VALUES (?,?)",
        [("cs1", "2026-07-10T09:05:00Z"),   # same day as real -> skipped
         ("cs2", "2026-07-05T09:05:00Z")])  # pre-telemetry -> recovered
    conn.commit()
    conn.close()


def build_claude(root: str) -> None:
    line = json.dumps({
        "type": "assistant",
        "message": {"model": "claude-3",
                    "usage": {"input_tokens": 100, "cache_creation_input_tokens": 10,
                              "cache_read_input_tokens": 5, "output_tokens": 20}},
        "timestamp": "2026-06-01T10:00:00Z", "cwd": "C:/proj/gamma"})
    write(os.path.join(root, "gammaproj", "sess.jsonl"), line + "\n")


def build_tree(tmp_path) -> dict:
    """Write the full four-surface fixture under ``tmp_path``."""
    paths = {
        "vs_root": str(tmp_path / "vs"),
        "vs_db": str(tmp_path / "vs.db"),
        "cli_home": str(tmp_path / "cli"),
        "claude_root": str(tmp_path / "claude"),
        "cache": str(tmp_path / "cache.json"),
    }
    os.makedirs(paths["cli_home"], exist_ok=True)
    build_vscode(paths["vs_root"], paths["vs_db"])
    build_cli(os.path.join(paths["cli_home"], "session-store.db"))
    build_claude(paths["claude_root"])
    return paths


def point_usage_at(monkeypatch, paths: dict) -> None:
    """Aim the scanners at the fixture. The one place path injection lives."""
    monkeypatch.setattr(usage, "VS_ROOT", paths["vs_root"])
    monkeypatch.setattr(usage, "VS_DB", paths["vs_db"])
    monkeypatch.setattr(usage, "CLI_HOME", paths["cli_home"])
    monkeypatch.setattr(usage, "CLAUDE_ROOT", paths["claude_root"])
    monkeypatch.setattr(usage, "CACHE", paths["cache"])


def scan(tmp_path, monkeypatch) -> list[dict]:
    """Build the fixture, run the real scanners, return ``build_projects`` output."""
    point_usage_at(monkeypatch, build_tree(tmp_path))
    usage.diag_reset()
    usage.set_quick_window(0)
    return usage.build_projects(usage.scan_vscode(), usage.scan_cli(), usage.scan_claude())
