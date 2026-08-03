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

import pytest

import synthetic
import usage
from synthetic import DAY0, DAY1, DAY2


@pytest.fixture()
def projects(tmp_path, monkeypatch):
    return {p["name"]: p for p in synthetic.scan(tmp_path, monkeypatch)}


def _sum(dim: dict, field: str) -> float:
    return sum(b[field] for b in dim.values())


def _assert_cross_dim_invariant(client: dict) -> None:
    """The core no-double-count guard: every dimension must total the same AIU."""
    a = round(_sum(client["by_day"], "aiu"), 4)
    for dim in ("by_model", "by_agent", "by_am", "by_dm"):
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
    # by_dm is what lets a model filter re-scope the day figures, so it has to
    # decompose cleanly along BOTH of its axes -- per date and per model.
    dd: dict = {}
    dmd: dict = {}
    for key, b in client["by_dm"].items():
        date, model = key.split(usage._AM_SEP, 1)
        dd[date] = dd.get(date, 0.0) + b["aiu"]
        dmd[model] = dmd.get(model, 0.0) + b["aiu"]
    for date, v in dd.items():
        assert round(v, 4) == round(client["by_day"][date]["aiu"], 4), date
    for model, v in dmd.items():
        assert round(v, 4) == round(client["by_model"][model]["aiu"], 4), model
    # requests must decompose too -- the token-less floors live only here
    r = _sum(client["by_day"], "requests")
    assert _sum(client["by_dm"], "requests") == r


class TestSynthetic:
    def test_project_set(self, projects):
        assert set(projects) == {"acme/alpha", "acme/beta", "gamma"}

    def test_vscode_totals_exact(self, projects):
        vs = projects["acme/alpha"]["vscode"]
        # 2 (s1) + 1 (s2) + 1 (child) + 1 (s3) + 1 (s4, metadata-only counts)
        assert _sum(vs["by_day"], "requests") == 6
        assert _sum(vs["by_day"], "in") == 1560     # 300 + 50 + 500 + 10 + 700
        assert _sum(vs["by_day"], "out") == 212      # 60 + 10 + 100 + 2 + 40
        assert round(_sum(vs["by_day"], "aiu"), 4) == 13.0  # 8 + 1 + 2 + 0.5 + 1.5
        assert _sum(vs["by_day"], "sessions") == 4
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
        assert vs["by_agent"]["GitHub Copilot Chat"]["requests"] == 5

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

    def test_session_activity_preserves_session_date_model_membership(self, projects):
        vs = projects["acme/alpha"]["vscode"]
        facts = {tuple(key.split(usage._AM_SEP)): b
                 for key, b in vs["by_sdm"].items()}
        assert set(facts) == {
            ("s1", DAY1, "gpt-x"),
            ("s2", DAY1, "gpt-x"),
            ("s2", DAY2, "claude"),
            ("s3", DAY0, "gpt-x"),
            ("s4", DAY0, "gpt-x"),
        }
        assert len({session for session, _, _ in facts}) == 4
        # s1's two day-1 events: 100+200 in, 20+40 out, 5+3 credits. Only the
        # second reported a cache figure, so cached_req is 1 of 2 requests.
        assert facts[("s1", DAY1, "gpt-x")] == {
            "requests": 2, "in": 300, "out": 60, "aiu": 8.0,
            "cached": 150, "cached_req": 1}
        # s2's subagent child log is the session's own day-2 activity.
        assert facts[("s2", DAY2, "claude")] == {
            "requests": 1, "in": 500, "out": 100, "aiu": 2.0,
            "cached": 0, "cached_req": 0}

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
