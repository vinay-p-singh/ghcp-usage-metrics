"""Choosing between two partial copies of the same session.

VS Code keeps every session twice and truncates each copy differently: request
logs drop calls, saved sessions drop turns. Preferring one store outright means
that whenever it is the more truncated copy, the better one is thrown away. So
the copy that kept more of the session wins, and only one of them is counted.

The shared fixture holds the ordinary case -- s1's saved copy is the thinner one
and loses. A swap is set up per test below, so what is being weighed is visible
in the test that depends on it.
"""
from __future__ import annotations

import json
import os

import usage
from synthetic import build_tree, ms, point_usage_at, write

# s2's request logs hold 3.0 credits: 1.0 in the main log, 2.0 in a subagent's
# child log. Anything above that makes its saved copy the better record.
S2_REQUEST_LOG_CREDITS = 3.0


def _vs(projects: list[dict], field: str) -> float:
    total = 0.0
    for p in projects:
        for b in p["vscode"]["by_day"].values():
            total += b[field]
    return round(total, 2)


def _run(tmp_path, monkeypatch, source: str = "auto", extra_chat=None) -> list[dict]:
    # A fresh subtree per run: build_tree creates the session store from scratch
    # and cannot be pointed at an existing one.
    root = tmp_path / source
    root.mkdir(exist_ok=True)
    paths = build_tree(root)
    for name, body in (extra_chat or {}).items():
        write(os.path.join(paths["vs_root"], "ws1", "chatSessions", name),
              json.dumps(body))
    point_usage_at(monkeypatch, paths)
    monkeypatch.setattr(usage, "SOURCE", source)
    usage.diag_reset()
    usage.set_quick_window(0)
    return usage.build_projects(usage.scan_vscode(), {}, {})


def _s2_saved(credits: float, prompt: int = 40) -> dict:
    """A saved copy of s2, whose request logs hold 3.0 credits across two files."""
    return {"s2.json": {
        "sessionId": "s2",
        "requests": [{"timestamp": ms(2026, 5, 2), "promptTokens": prompt,
                      "completionTokens": 8, "copilotCredits": credits,
                      "modelId": "copilot/gpt-x"}]}}


def test_the_thinner_saved_copy_is_not_counted(tmp_path, monkeypatch):
    """The ordinary case. s1 is in both stores and its request log kept more, so
    the saved copy's 9,999 tokens stay out of every total."""
    projects = _run(tmp_path, monkeypatch)
    assert _vs(projects, "aiu") == 13.0
    assert _vs(projects, "in") == 1560


def test_the_saved_copy_wins_when_it_kept_more_of_the_session(tmp_path, monkeypatch):
    """s2's request logs hold 3.0 credits; a saved copy holding 50.0 means those
    logs lost most of the session, so the saved copy is the better record."""
    projects = _run(tmp_path, monkeypatch, extra_chat=_s2_saved(50.0))
    # 8.0 (s1, request log) + 50.0 (s2, saved) + 0.5 (s3) + 1.5 (s4)
    assert _vs(projects, "aiu") == 60.0


def test_a_session_is_counted_once_not_added_together(tmp_path, monkeypatch):
    """Both stores describe the same calls. Summing them double-counts."""
    projects = _run(tmp_path, monkeypatch, extra_chat=_s2_saved(50.0))
    assert _vs(projects, "aiu") != 8.0 + S2_REQUEST_LOG_CREDITS + 50.0 + 0.5 + 1.5
    # s2 contributes its saved copy's 40 input tokens, not the logs' 550.
    assert _vs(projects, "in") == 300 + 40 + 10 + 700


def test_the_request_log_still_wins_when_it_kept_more(tmp_path, monkeypatch):
    projects = _run(tmp_path, monkeypatch, extra_chat=_s2_saved(0.2))
    assert _vs(projects, "aiu") == 13.0


def test_a_tie_keeps_the_request_log(tmp_path, monkeypatch):
    """Equal credits means neither copy lost more, so keep the one carrying
    per-call detail: a subagent's child log has no saved-session equivalent."""
    projects = _run(tmp_path, monkeypatch,
                    extra_chat=_s2_saved(S2_REQUEST_LOG_CREDITS))
    row = next(p for p in projects if p["name"] == "acme/alpha")
    assert row["vscode"]["by_agent"]["Researcher"]["aiu"] == 2.0


def test_a_saved_copy_with_no_credits_cannot_displace_a_billed_one(tmp_path, monkeypatch):
    """Saved sessions carried no credit figure before VS Code began writing one.
    Zero there means unrecorded, never cheaper -- however many tokens it lists."""
    projects = _run(tmp_path, monkeypatch, extra_chat=_s2_saved(0.0, prompt=999_999))
    assert _vs(projects, "aiu") == 13.0
    assert _vs(projects, "in") == 1560


def test_taking_the_saved_copy_costs_that_session_its_per_call_detail(tmp_path, monkeypatch):
    """The price of a swap, recorded rather than hidden.

    A subagent's tokens live only in a child log the saved session never had. We
    give that up rather than understate the credits by an order of magnitude,
    which is the worse error in a spend report.
    """
    projects = _run(tmp_path, monkeypatch, extra_chat=_s2_saved(50.0))
    row = next(p for p in projects if p["name"] == "acme/alpha")
    assert "Researcher" not in row["vscode"]["by_agent"]


def test_a_swap_is_counted_so_the_rotation_stays_visible(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch, extra_chat=_s2_saved(50.0))
    assert usage.DIAG["source"]["sessions_from_saved"] == 1


def test_no_swap_is_recorded_when_the_request_logs_win(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch)
    assert usage.DIAG["source"]["sessions_from_saved"] == 0


def test_choosing_one_store_disables_the_comparison(tmp_path, monkeypatch):
    """With one store read there is nothing to weigh, and the totals must match
    that store exactly."""
    assert _vs(_run(tmp_path, monkeypatch, "debug"), "aiu") == 11.0
    assert _vs(_run(tmp_path, monkeypatch, "sessions"), "aiu") == 2.0


def test_every_dimension_agrees_after_a_swap(tmp_path, monkeypatch):
    """Replacing one session's copy must leave the breakdowns consistent, or the
    swap has torn a hole in the invariant the whole tool rests on."""
    projects = _run(tmp_path, monkeypatch, extra_chat=_s2_saved(50.0))
    for p in projects:
        m = p["vscode"]
        day = round(sum(b["aiu"] for b in m["by_day"].values()), 4)
        for dim in ("by_model", "by_agent", "by_am", "by_dm", "by_sdm"):
            got = round(sum(b["aiu"] for b in m[dim].values()), 4)
            assert got == day, f"{p['name']} {dim} {got} != by_day {day}"
        req = sum(b["requests"] for b in m["by_day"].values())
        for dim in ("by_model", "by_agent", "by_dm", "by_sdm"):
            assert sum(b["requests"] for b in m[dim].values()) == req, dim
