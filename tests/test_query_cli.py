"""The skill's query CLI must date-scope what it can, and say so when it cannot.

``by_dm`` pairs a date with a model on the same recorded event, so a model
breakdown can honour ``--since``/``--until``. There is no date-by-agent
dimension, so an agent breakdown genuinely cannot -- and has to keep saying so
rather than quietly reporting lifetime figures under a date range.
"""
from __future__ import annotations

import importlib.util
import json
import os

import pytest

SEP = "\x1f"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_QUERY = os.path.join(_ROOT, "skills", "ghcp-usage-metrics", "query.py")
_SNAPSHOT = os.path.join(_ROOT, "out", "projects.json")


def _load():
    spec = importlib.util.spec_from_file_location("ghcp_query", _QUERY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


query = _load()


def _client(by_day=None, by_model=None, by_dm=None, by_agent=None):
    return {"by_day": by_day or {}, "by_model": by_model or {},
            "by_agent": by_agent or {}, "by_am": {}, "by_dm": by_dm or {},
            "by_sdm": {}, "by_skill": {}, "by_tool": {}, "by_lang": {}}


def _empty():
    return _client()


@pytest.fixture
def rows():
    """One project that used model-a in BOTH months and model-b only in August.

    A model spanning the window boundary is what makes the test meaningful: its
    lifetime total (75) and its July total (50) differ, so a breakdown that
    ignores the range is visibly wrong rather than coincidentally right.
    Every dimension agrees, as the extractor's invariant requires -- the days
    sum to the models sum to the date-model cells.
    """
    july_a = {"requests": 10, "in": 1000, "out": 100, "aiu": 50.0}
    aug_a = {"requests": 5, "in": 500, "out": 50, "aiu": 25.0}
    aug_b = {"requests": 3, "in": 300, "out": 30, "aiu": 15.0}
    vscode = _client(
        by_day={"2026-07-15": {"sessions": 1, **july_a},
                "2026-08-02": {"sessions": 1, "requests": 8, "in": 800,
                               "out": 80, "aiu": 40.0}},
        by_model={"model-a": {"requests": 15, "in": 1500, "out": 150, "aiu": 75.0},
                  "model-b": dict(aug_b)},
        by_dm={"2026-07-15" + SEP + "model-a": dict(july_a),
               "2026-08-02" + SEP + "model-a": dict(aug_a),
               "2026-08-02" + SEP + "model-b": dict(aug_b)},
        by_agent={"GitHub Copilot Chat": {"requests": 18, "in": 1800,
                                          "out": 180, "aiu": 90.0}})
    return [{"name": "demo", "vscode": vscode, "cli": _empty(), "claude": _empty()}]


class Args:
    def __init__(self, since=None, until=None, top=15, name=None):
        self.since = since
        self.until = until
        self.top = top
        self.name = name


def test_model_breakdown_only_reports_models_used_in_the_window(rows, capsys):
    query.cmd_models(rows, Args(since="2026-07-01", until="2026-07-31"))
    out = capsys.readouterr().out
    assert "model-a" in out
    assert "model-b" not in out, "August's model leaked into a July-only range"


def test_model_breakdown_reports_the_windowed_figures_not_lifetime(rows, capsys):
    query.cmd_models(rows, Args(since="2026-07-01", until="2026-07-31"))
    out = capsys.readouterr().out
    assert "50.0" in out, "expected model-a's July credits"
    assert "75.0" not in out, "reported model-a's lifetime total under a date range"
    assert "1,000" in out, "expected July's input tokens, not the lifetime 1,500"


def test_model_totals_agree_with_the_day_totals_for_the_same_window(rows, capsys):
    """The property that makes a reconciliation against an official report mean
    anything: the same window has to produce the same credits on both axes."""
    args = Args(since="2026-07-01", until="2026-07-31")
    day = query.day_totals(rows, args)
    query.cmd_models(rows, args)
    out = capsys.readouterr().out
    assert f"{day['aiu']:,.1f}" in out


def test_model_breakdown_no_longer_disclaims_the_date_range(rows, capsys):
    query.cmd_models(rows, Args(since="2026-07-01", until="2026-07-31"))
    out = capsys.readouterr().out
    assert "date range does not apply" not in out


def test_agent_breakdown_still_admits_it_cannot_be_dated(rows, capsys):
    """No date-by-agent dimension exists, so this one must keep its caveat."""
    query.cmd_agents(rows, Args(since="2026-07-01", until="2026-07-31"))
    out = capsys.readouterr().out
    assert "date range does not apply" in out


def test_untracked_requests_are_still_reported_separately(capsys):
    """A request whose source named no model stays visible instead of vanishing."""
    vscode = _client(
        by_day={"2026-07-15": {"sessions": 1, "requests": 3, "in": 0,
                               "out": 0, "aiu": 0.0}},
        by_model={query.NO_TOKEN: {"requests": 3, "in": 0, "out": 0, "aiu": 0.0}},
        by_dm={"2026-07-15" + SEP + query.NO_TOKEN: {"requests": 3, "in": 0,
                                                     "out": 0, "aiu": 0.0}})
    rows = [{"name": "quiet", "vscode": vscode, "cli": _empty(), "claude": _empty()}]
    query.cmd_models(rows, Args(since="2026-07-01", until="2026-07-31"))
    out = capsys.readouterr().out
    assert "3 requests with no recorded model" in out


def test_project_model_line_is_windowed(rows, capsys):
    query.cmd_project(rows, Args(since="2026-07-01", until="2026-07-31", name="demo"))
    out = capsys.readouterr().out
    assert "model-a" in out
    assert "model-b" not in out


@pytest.mark.skipif(not os.path.isfile(_SNAPSHOT),
                    reason="out/projects.json not generated (run `python usage.py`)")
def test_on_real_data_a_windowed_model_breakdown_sums_to_that_window():
    """The property any external reconciliation rests on.

    If the per-model figures for a date range do not add up to that range's own
    totals, then comparing either of them against an official report says
    nothing. Asserted on a narrow interior window, because whole-span equality
    would hold even if the range were being ignored.
    """
    with open(_SNAPSHOT, encoding="utf-8") as fh:
        projects = json.load(fh)
    dates = sorted({d for p in projects for c in ("vscode", "cli", "claude")
                    for d in p[c]["by_day"]})
    assert len(dates) > 8, "not enough recorded days to form an interior window"
    args = Args(since=dates[len(dates) // 4], until=dates[3 * len(dates) // 4])

    day = query.day_totals(projects, args)
    models = query.model_totals(projects, args)

    assert day["requests"] > 0, "window is empty; the assertions below prove nothing"
    assert len(models) > 1, "only one model in range; would pass even unwindowed"
    assert day["requests"] < query.day_totals(projects, Args())["requests"], \
        "the window covers everything, so it does not test windowing"

    assert sum(v["requests"] for v in models.values()) == day["requests"]
    assert abs(sum(v["aiu"] for v in models.values()) - day["aiu"]) < 0.05
    assert abs(sum(v["in"] for v in models.values()) - day["in"]) < 1
