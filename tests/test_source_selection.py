"""Choosing which VS Code source the scan reads.

Two stores hold the same sessions and neither is complete: request logs carry
every model call but rotate away, saved sessions survive far longer but keep
only the most recent turns. A machine that never wrote request logs still has
the saved sessions, so the tool has to be able to run on them alone -- and has
to say so, because the credit figure only appears in saved sessions from the
day VS Code started writing it.
"""
from __future__ import annotations

import json
import os
import shutil

import pytest

import usage
from synthetic import build_tree, ms, point_usage_at, write


def _totals(projects: list[dict]) -> dict:
    t = {"requests": 0, "in": 0, "out": 0, "aiu": 0.0}
    for p in projects:
        for b in p["vscode"]["by_day"].values():
            t["requests"] += b["requests"]
            t["in"] += b["in"]
            t["out"] += b["out"]
            t["aiu"] += b["aiu"]
    t["aiu"] = round(t["aiu"], 2)
    return t


def _run(tmp_path, monkeypatch, source: str, drop_debug: bool = False) -> dict:
    paths = build_tree(tmp_path)
    if drop_debug:
        shutil.rmtree(os.path.join(paths["vs_root"], "ws1",
                                   "GitHub.copilot-chat", "debug-logs"))
    point_usage_at(monkeypatch, paths)
    monkeypatch.setattr(usage, "SOURCE", source)
    usage.diag_reset()
    usage.set_quick_window(0)
    projects = usage.build_projects(usage.scan_vscode(), {}, {})
    return {"totals": _totals(projects), "diag": usage.DIAG["source"]}


def test_auto_still_prefers_the_request_log_over_the_saved_session(tmp_path, monkeypatch):
    """The default must not change: s1 exists in both stores and the richer
    request log wins, so the saved session's 9,999 tokens stay out."""
    t = _run(tmp_path, monkeypatch, "auto")["totals"]
    assert t == {"requests": 6, "in": 1560, "out": 212, "aiu": 13.0}


def test_debug_only_ignores_saved_sessions_entirely(tmp_path, monkeypatch):
    """s3 and s4 exist only as saved sessions, so they disappear."""
    t = _run(tmp_path, monkeypatch, "debug")["totals"]
    assert t == {"requests": 4, "in": 850, "out": 170, "aiu": 11.0}


def test_sessions_only_reads_what_the_request_log_would_have_shadowed(tmp_path, monkeypatch):
    """s1 is in both stores. Without the request logs its saved copy is all
    there is, so it must be counted rather than skipped as a duplicate. Its
    credits are 0 because saved sessions predate VS Code writing a credit
    figure -- the tokens are still real."""
    t = _run(tmp_path, monkeypatch, "sessions")["totals"]
    assert t == {"requests": 3, "in": 10709, "out": 10041, "aiu": 2.0}


def test_sessions_only_uses_the_recorded_fallback_model_and_completion_time(
        tmp_path, monkeypatch):
    paths = build_tree(tmp_path)
    chat = os.path.join(paths["vs_root"], "ws1", "chatSessions")
    write(os.path.join(chat, "s5.json"), json.dumps({
        "sessionId": "s5",
        "requests": [{
            "promptTokens": 123,
            "completionTokens": 45,
            "copilotCredits": 6.5,
            "modelState": {"completedAt": ms(2026, 5, 3), "value": 2},
            "result": {"metadata": {"resolvedModel": "copilot/gpt-fallback"}},
        }],
    }))
    point_usage_at(monkeypatch, paths)
    monkeypatch.setattr(usage, "SOURCE", "sessions")
    usage.diag_reset()
    usage.set_quick_window(0)

    projects = usage.build_projects(usage.scan_vscode(), {}, {})

    assert _totals(projects) == {
        "requests": 4,
        "in": 10832,
        "out": 10086,
        "aiu": 8.5,
    }


def test_sessions_only_reads_empty_window_sessions_without_double_counting(
        tmp_path, monkeypatch):
    paths = build_tree(tmp_path)
    empty = os.path.join(os.path.dirname(paths["vs_root"]), "globalStorage",
                         "emptyWindowChatSessions")
    write(os.path.join(empty, "empty-1.json"), json.dumps({
        "sessionId": "empty-1",
        "requests": [{
            "timestamp": ms(2026, 5, 3),
            "promptTokens": 321,
            "completionTokens": 12,
            "copilotCredits": 2.25,
            "modelId": "copilot/gpt-empty",
        }],
    }))
    # s3 already exists in the workspace's chatSessions store. The global copy
    # must not be added again, even if it retained larger-looking totals.
    write(os.path.join(empty, "s3.json"), json.dumps({
        "sessionId": "s3",
        "requests": [{
            "timestamp": ms(2026, 5, 1),
            "promptTokens": 9999,
            "completionTokens": 999,
            "copilotCredits": 99.0,
            "modelId": "copilot/gpt-empty",
        }],
    }))
    point_usage_at(monkeypatch, paths)
    monkeypatch.setattr(usage, "SOURCE", "sessions")
    usage.diag_reset()
    usage.set_quick_window(0)

    projects = usage.build_projects(usage.scan_vscode(), {}, {})

    assert _totals(projects) == {
        "requests": 4,
        "in": 11030,
        "out": 10053,
        "aiu": 4.25,
    }


def test_sessions_only_counts_recorded_summary_model_usage(tmp_path, monkeypatch):
    paths = build_tree(tmp_path)
    chat = os.path.join(paths["vs_root"], "ws1", "chatSessions")
    write(os.path.join(chat, "s6.json"), json.dumps({
        "sessionId": "s6",
        "requests": [{
            "timestamp": ms(2026, 5, 3),
            "promptTokens": 100,
            "completionTokens": 20,
            "copilotCredits": 1.0,
            "modelId": "copilot/gpt-parent",
            "result": {"metadata": {"summaries": [{
                "toolCallRoundId": "round-1",
                "model": "copilot/gpt-summary",
                "usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 50,
                    "total_tokens": 1050,
                    "prompt_tokens_details": {"cached_tokens": 900},
                },
            }]}},
        }],
    }))
    point_usage_at(monkeypatch, paths)
    monkeypatch.setattr(usage, "SOURCE", "sessions")
    usage.diag_reset()
    usage.set_quick_window(0)

    projects = usage.build_projects(usage.scan_vscode(), {}, {})

    assert _totals(projects) == {
        "requests": 5,
        "in": 11809,
        "out": 10111,
        "aiu": 3.0,
    }
    row = next(project for project in projects if project["name"] == "acme/alpha")
    summary = row["vscode"]["by_model"]["gpt-summary"]
    assert summary == {
        "requests": 1,
        "in": 1000,
        "out": 50,
        "aiu": 0.0,
        "cached": 900,
        "cached_req": 1,
    }


def test_a_machine_with_no_request_logs_falls_back_on_its_own(tmp_path, monkeypatch):
    """Nobody should have to discover a setting to get a report at all."""
    r = _run(tmp_path, monkeypatch, "auto", drop_debug=True)
    assert r["diag"]["requested"] == "auto"
    assert r["diag"]["effective"] == "sessions"
    assert r["diag"]["debug_sessions"] == 0
    assert r["totals"]["requests"] == 3


def test_the_fallback_does_not_engage_while_request_logs_exist(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch, "auto")
    assert r["diag"]["effective"] == "auto"
    assert r["diag"]["debug_sessions"] == 2


def test_an_explicit_choice_is_never_overridden(tmp_path, monkeypatch):
    """Asking for one store and silently getting the other would make any
    comparison between the two meaningless."""
    r = _run(tmp_path, monkeypatch, "debug", drop_debug=True)
    assert r["diag"]["requested"] == "debug"
    assert r["diag"]["effective"] == "debug"
    assert r["totals"]["requests"] == 0


def test_the_credit_onset_is_read_from_the_logs_not_assumed(tmp_path, monkeypatch):
    """Saved sessions only carry a credit figure from the day VS Code began
    writing one. The date is evidence, so it is measured, never hardcoded."""
    r = _run(tmp_path, monkeypatch, "sessions")
    assert r["diag"]["chat_credit_first"] == "2026-05-01"


def test_no_credit_bearing_saved_session_reports_no_onset(tmp_path, monkeypatch):
    """Absent evidence is reported as absent, not as a guess."""
    paths = build_tree(tmp_path)
    chat = os.path.join(paths["vs_root"], "ws1", "chatSessions")
    for name in os.listdir(chat):
        os.remove(os.path.join(chat, name))
    point_usage_at(monkeypatch, paths)
    monkeypatch.setattr(usage, "SOURCE", "sessions")
    usage.diag_reset()
    usage.set_quick_window(0)
    usage.build_projects(usage.scan_vscode(), {}, {})
    assert usage.DIAG["source"]["chat_credit_first"] is None


@pytest.mark.parametrize("argv,expected", [
    ([], "auto"),
    (["--source", "sessions"], "sessions"),
    (["--source", "debug"], "debug"),
    (["--source", "nonsense"], "auto"),
])
def test_the_flag_parses_and_an_unknown_value_falls_back_to_auto(argv, expected):
    assert usage._source(argv) == expected
