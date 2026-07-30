"""Quick-scan window + diagnostics record.

The quick pass exists so the first open of the dashboard is not held up by a
cold full scan. It must be genuinely cheaper (old, uncached logs are skipped)
and it must say so — a partial report that looks complete would be worse than a
slow one. These tests lock both halves of that contract, plus the coverage
analysis that explains requests whose source never stored token counts.
"""
from __future__ import annotations

import datetime
import json
import os
import time

import pytest

import usage
from ghcp.constants import NO_TOKEN
from ghcp.diagnostics import coverage


def _ms(y: int, m: int, d: int) -> int:
    return int(datetime.datetime(y, m, d, 12, tzinfo=datetime.timezone.utc).timestamp() * 1000)


def _write(path: str, text: str, age_days: float = 0) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    if age_days:
        t = time.time() - age_days * 86400
        os.utime(path, (t, t))


def _billing(day_ms: int, in_: int, out: int, nano: int) -> str:
    return json.dumps({"type": "llm_request", "ts": day_ms,
                       "attrs": {"inputTokens": in_, "outputTokens": out,
                                 "model": "gpt-x", "copilotUsageNanoAiu": nano}})


@pytest.fixture(autouse=True)
def _clean_scan_state():
    usage.diag_reset()
    usage.set_quick_window(0)
    yield
    usage.diag_reset()
    usage.set_quick_window(0)


@pytest.fixture()
def vs_tree(tmp_path, monkeypatch):
    """One recent session and one 60-day-old session, neither cached."""
    root = tmp_path / "vs"
    ws = root / "ws1"
    _write(str(ws / "workspace.json"), json.dumps({"folder": "file:///C:/proj/alpha"}))
    dbg = ws / "GitHub.copilot-chat" / "debug-logs"
    _write(str(dbg / "recent" / "main.jsonl"),
           _billing(_ms(2026, 5, 2), 100, 20, 5_000_000_000) + "\n")
    _write(str(dbg / "ancient" / "main.jsonl"),
           _billing(_ms(2026, 1, 2), 700, 70, 9_000_000_000) + "\n", age_days=60)

    monkeypatch.setattr(usage, "VS_ROOT", str(root))
    monkeypatch.setattr(usage, "VS_DB", str(tmp_path / "vs.db"))
    monkeypatch.setattr(usage, "CLI_HOME", str(tmp_path / "no-cli"))
    monkeypatch.setattr(usage, "CLAUDE_ROOT", str(tmp_path / "no-claude"))
    return tmp_path


def _alpha_aiu(out: dict) -> float:
    return sum(b["aiu"] for b in out["alpha"]["by_day"].values())


def test_full_scan_reads_every_log(vs_tree, monkeypatch):
    monkeypatch.setattr(usage, "CACHE", str(vs_tree / "cache-full.json"))
    out = usage.scan_vscode()
    assert _alpha_aiu(out) == pytest.approx(14.0)
    src = usage.DIAG["sources"]["vscode_debug"]
    assert src["files_deferred"] == 0
    assert src["files_parsed"] == 2


def test_quick_scan_defers_old_uncached_logs(vs_tree, monkeypatch):
    monkeypatch.setattr(usage, "CACHE", str(vs_tree / "cache-quick.json"))
    usage.set_quick_window(10)
    out = usage.scan_vscode()

    # only the recent log contributed credits; the old one was left for later
    assert _alpha_aiu(out) == pytest.approx(5.0)
    src = usage.DIAG["sources"]["vscode_debug"]
    assert src["files_deferred"] == 1
    assert src["files_parsed"] == 1
    assert usage.DIAG["partial"] is True
    assert usage.DIAG["quick_days"] == 10
    assert usage.DIAG["mode"] == "quick"


def test_quick_scan_still_uses_cached_old_logs(vs_tree, monkeypatch):
    """A memoised log costs nothing to include, so the window must not drop it."""
    cache = str(vs_tree / "cache-shared.json")
    monkeypatch.setattr(usage, "CACHE", cache)
    usage.scan_vscode()                      # full pass warms the cache

    usage.diag_reset()
    usage.set_quick_window(10)
    out = usage.scan_vscode()
    assert _alpha_aiu(out) == pytest.approx(14.0)
    assert usage.DIAG["sources"]["vscode_debug"]["files_deferred"] == 0


def test_malformed_lines_are_counted_not_swallowed(vs_tree, monkeypatch):
    monkeypatch.setattr(usage, "CACHE", str(vs_tree / "cache-bad.json"))
    dbg = vs_tree / "vs" / "ws1" / "GitHub.copilot-chat" / "debug-logs"
    _write(str(dbg / "broken" / "main.jsonl"),
           _billing(_ms(2026, 5, 2), 10, 2, 1_000_000_000) + "\n"
           + '{"type": "llm_request", "attrs": {"inputTokens": oops\n')
    usage.scan_vscode()
    assert usage.DIAG["sources"]["vscode_debug"]["bad_lines"] == 1


def test_coverage_explains_requests_without_tokens():
    metrics = usage._metrics()
    usage._add_day(metrics, "2026-07-01", requests=3, in_=90, out=9, aiu=1.5)
    usage._add_flat(metrics["by_model"], "gpt-x", requests=1, in_=90, out=9, aiu=1.5)
    usage._add_flat(metrics["by_model"], NO_TOKEN, requests=2)
    projects = usage.build_projects({}, {"acme/beta": metrics}, {})

    coverage(projects)
    cov = usage.DIAG["coverage"]
    assert cov["requests"] == 3
    assert cov["requests_no_tokens"] == 2
    assert cov["pct_no_tokens"] == pytest.approx(66.67, abs=0.01)
    assert cov["by_client"]["cli"] == {"requests": 3, "no_tokens": 2}

    rows = usage.DIAG["no_token_rows"]
    assert len(rows) == 1
    assert rows[0]["project"] == "acme/beta"
    assert rows[0]["client"] == "cli"
    assert rows[0]["no_tokens"] == 2
    assert "turns" in rows[0]["reason"]


def test_write_dashboard_injects_diagnostics(tmp_path, monkeypatch):
    monkeypatch.setattr(usage, "OUT", str(tmp_path / "out"))
    usage.set_quick_window(7)
    usage.write_dashboard([])

    html = (tmp_path / "out" / "dashboard.html").read_text(encoding="utf-8")
    assert "__DIAG__" not in html
    written = json.loads((tmp_path / "out" / "diagnostics.json").read_text(encoding="utf-8"))
    assert written["quick_days"] == 7
    assert written["partial"] is True
