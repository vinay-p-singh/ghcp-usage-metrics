"""Unit tests for the modules split out of usage.py.

Each one takes its paths as arguments now, so these call the real thing directly
with a fixture path -- no module globals to patch, no full scan to run. That is
the point of the split: a change to CLI recovery can be tested without touching
VS Code parsing.
"""
from __future__ import annotations

import datetime
import json
import os
import sqlite3
import time

import pytest

import synthetic
from ghcp import billing, report, window
from ghcp.constants import AGENT_CLI, AM_SEP, NO_TOKEN
from ghcp.diagnostics import DIAG, coverage, diag_reset, src
from ghcp.model import _metrics
from ghcp.scan.claude import scan_claude
from ghcp.scan.cli import scan_cli
from ghcp.scan.vscode import scan_vscode, sid_skills_map


@pytest.fixture(autouse=True)
def _clean_state():
    diag_reset()
    window.set_quick_window(0)
    yield
    diag_reset()
    window.set_quick_window(0)


def _totals(metrics: dict, field: str) -> float:
    return sum(b[field] for b in metrics["by_day"].values())


class TestWindow:
    def test_no_window_accepts_everything(self, tmp_path):
        f = tmp_path / "a.jsonl"
        f.write_text("x", encoding="utf-8")
        assert window.cutoff() == 0.0
        assert window.in_window(str(f)) is True

    def test_window_excludes_older_files(self, tmp_path):
        f = tmp_path / "old.jsonl"
        f.write_text("x", encoding="utf-8")
        old = time.time() - 30 * 86400
        os.utime(f, (old, old))
        window.set_quick_window(10)
        assert window.in_window(str(f)) is False

    def test_missing_file_is_not_in_window(self, tmp_path):
        window.set_quick_window(10)
        assert window.in_window(str(tmp_path / "gone.jsonl")) is False

    def test_setting_the_window_marks_the_run_partial(self):
        window.set_quick_window(5)
        assert (DIAG["mode"], DIAG["quick_days"], DIAG["partial"]) == ("quick", 5, True)
        window.set_quick_window(0)
        assert (DIAG["mode"], DIAG["quick_days"], DIAG["partial"]) == ("full", 0, False)


class TestBilling:
    def _log(self, tmp_path) -> str:
        path = str(tmp_path / "main.jsonl")
        synthetic.write(path,
                        synthetic.billing_line(synthetic.ms(2026, 5, 2), 100, 20,
                                               "gpt-x", 5_000_000_000) + "\n"
                        + json.dumps({"type": "tool_call",
                                      "attrs": {"name": "read_file"}}) + "\n"
                        + json.dumps({"type": "child_session_ref",
                                      "attrs": {"childLogFile": "c.jsonl",
                                                "label": "runSubagent-R"}}) + "\n"
                        + '{"type": "llm_request", "attrs": {"inputTokens": broken\n')
        return path

    def test_parses_tokens_credits_tools_and_childrefs(self, tmp_path):
        rec = billing.billing_for_file(self._log(tmp_path), {})
        assert rec["by_day"]["2026-05-02"]["requests"] == 1
        assert rec["by_day"]["2026-05-02"]["in"] == 100
        assert rec["by_model"]["gpt-x"]["aiu"] == pytest.approx(5.0)
        assert rec["tools"] == {"read_file": 1}
        assert rec["childrefs"] == {"c.jsonl": "runSubagent-R"}

    def test_counts_malformed_lines_instead_of_dropping_them(self, tmp_path):
        assert billing.billing_for_file(self._log(tmp_path), {})["bad"] == 1

    def test_second_read_comes_from_the_cache(self, tmp_path):
        path = self._log(tmp_path)
        cache: dict = {}
        first = billing.billing_for_file(path, cache)
        assert billing.cache_hit(cache, path) is True
        assert billing.billing_for_file(path, cache) is first

    def test_cache_entry_expires_when_the_file_changes(self, tmp_path):
        path = self._log(tmp_path)
        cache: dict = {}
        billing.billing_for_file(path, cache)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(synthetic.billing_line(synthetic.ms(2026, 5, 3), 1, 1,
                                            "gpt-x", 1_000_000_000) + "\n")
        assert billing.cache_hit(cache, path) is False

    def test_deferred_log_is_counted_not_parsed(self, tmp_path):
        path = self._log(tmp_path)
        old = time.time() - 30 * 86400
        os.utime(path, (old, old))
        window.set_quick_window(10)
        assert billing.billing_or_defer(path, {}) == {}
        assert src("vscode_debug")["files_deferred"] == 1
        assert src("vscode_debug")["files_parsed"] == 0

    def test_unreadable_log_is_recorded_as_a_failure(self, tmp_path):
        assert billing.billing_or_defer(str(tmp_path / "nope.jsonl"), {}) == {}
        assert src("vscode_debug")["files_failed"] == 1
        assert DIAG["errors"][0]["source"] == "vscode_debug"

    def test_apply_billing_keeps_every_dimension_equal(self, tmp_path):
        rec = billing.billing_for_file(self._log(tmp_path), {})
        m = _metrics()
        req, in_, out, aiu = billing.apply_billing(m, "Agent A", rec)
        assert (req, in_, out) == (1, 100, 20)
        assert aiu == pytest.approx(5.0)
        assert _totals(m, "aiu") == pytest.approx(sum(b["aiu"] for b in m["by_model"].values()))
        assert _totals(m, "aiu") == pytest.approx(sum(b["aiu"] for b in m["by_agent"].values()))
        assert m["by_tool"]["read_file"] == 1


class TestScanCli:
    def test_reads_real_events_and_recovers_pre_telemetry_turns(self, tmp_path):
        synthetic.build_cli(str(tmp_path / "session-store.db"))
        out = scan_cli(str(tmp_path))
        beta = out["acme/beta"]
        assert _totals(beta, "requests") == 2      # 1 billed event + 1 recovered turn
        assert _totals(beta, "in") == 1000         # the recovered turn adds no tokens
        assert _totals(beta, "aiu") == pytest.approx(4.0)
        assert beta["by_model"][NO_TOKEN]["requests"] == 1
        assert AGENT_CLI in beta["by_agent"]

    def test_missing_store_is_reported_not_raised(self, tmp_path):
        assert scan_cli(str(tmp_path / "absent")) == {}
        assert src("cli")["roots"][0]["exists"] is False

    def test_unreadable_store_is_recorded_as_a_failure(self, tmp_path):
        db = tmp_path / "session-store.db"
        db.write_text("this is not a database", encoding="utf-8")
        scan_cli(str(tmp_path))
        assert src("cli")["files_failed"] == 1


class TestScanClaude:
    def test_tokens_are_real_but_credits_stay_zero(self, tmp_path):
        synthetic.build_claude(str(tmp_path))
        gamma = scan_claude(str(tmp_path))["gamma"]
        assert _totals(gamma, "requests") == 1
        assert _totals(gamma, "in") == 115         # input + cache creation + cache read
        assert _totals(gamma, "aiu") == 0.0        # Claude emits no GitHub credits

    def test_synthetic_turns_are_not_billed_calls(self, tmp_path):
        synthetic.write(str(tmp_path / "proj" / "s.jsonl"), json.dumps({
            "type": "assistant", "message": {"model": "<synthetic>", "usage": {}},
            "timestamp": "2026-06-01T10:00:00Z", "cwd": "C:/proj/delta"}) + "\n")
        assert scan_claude(str(tmp_path)) == {}

    def test_missing_root_is_reported_not_raised(self, tmp_path):
        assert scan_claude(str(tmp_path / "absent")) == {}
        assert src("claude")["roots"][0]["exists"] is False


class TestSkillDetection:
    def _db(self, tmp_path, paths: list[str]) -> str:
        db = str(tmp_path / "s.db")
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE session_files "
                     "(id INTEGER, session_id TEXT, file_path TEXT)")
        conn.executemany("INSERT INTO session_files VALUES (?,?,?)",
                         [(i, "sid", p) for i, p in enumerate(paths)])
        conn.commit()
        conn.close()
        return db

    def test_extracts_the_skill_folder_name(self, tmp_path):
        db = self._db(tmp_path, ["C:/x/skills/web-artifacts-builder/SKILL.md",
                                 r"C:\y\Skills\obsidian\SKILL.md"])
        assert sid_skills_map(db) == {"sid": {"web-artifacts-builder": 1, "obsidian": 1}}

    def test_repeat_reads_accumulate(self, tmp_path):
        db = self._db(tmp_path, ["C:/x/skills/chronicle/SKILL.md"] * 3)
        assert sid_skills_map(db)["sid"]["chronicle"] == 3

    def test_unrelated_skill_md_is_ignored(self, tmp_path):
        db = self._db(tmp_path, ["C:/docs/SKILL.md"])
        assert sid_skills_map(db) == {}

    def test_missing_db_returns_empty(self, tmp_path):
        assert sid_skills_map(str(tmp_path / "none.db")) == {}


class TestReport:
    def test_stamp_uses_twelve_hour_clock(self):
        import datetime
        assert report.generated_stamp(datetime.datetime(2026, 7, 24, 16, 10, 13)) \
            == "24/7/2026, 4:10:13 pm"
        assert report.generated_stamp(datetime.datetime(2026, 7, 24, 0, 5, 0)) \
            == "24/7/2026, 12:05:00 am"

    def test_render_fills_every_placeholder(self):
        html = report.render([{"name": "acme/alpha"}], {"mode": "full"}, "STAMP")
        for token in ("__DATA__", "__DIAG__", "__GENERATED__"):
            assert token not in html
        assert '"acme/alpha"' in html
        assert "STAMP" in html

    def test_write_dashboard_emits_all_three_artifacts(self, tmp_path):
        report.write_dashboard([], str(tmp_path), {"mode": "full"})
        for name in ("dashboard.html", "projects.json", "diagnostics.json"):
            assert (tmp_path / name).is_file()


class TestCoverage:
    def test_a_fully_recorded_project_reports_no_gap(self):
        m = _metrics()
        m["by_model"]["gpt-x"] = {"requests": 4, "in": 1, "out": 1, "aiu": 1.0}
        coverage([{"name": "p", "vscode": m, "cli": _metrics(), "claude": _metrics()}])
        assert DIAG["coverage"]["requests_no_tokens"] == 0
        assert DIAG["no_token_rows"] == []

    def test_rows_are_ordered_worst_first(self):
        def proj(name, n):
            m = _metrics()
            m["by_model"][NO_TOKEN] = {"requests": n, "in": 0, "out": 0, "aiu": 0.0}
            return {"name": name, "vscode": _metrics(), "cli": m, "claude": _metrics()}
        coverage([proj("small", 2), proj("big", 9)])
        assert [r["project"] for r in DIAG["no_token_rows"]] == ["big", "small"]


class TestUndatedToolCalls:
    def test_are_filed_on_the_session_day_not_the_day_the_scan_ran(self, tmp_path):
        """A tool call the log did not stamp is dated from its session.

        Reading the clock instead would move a historical figure every time the
        scan is re-run, and would quietly rot any recorded expectation of it.
        """
        paths = synthetic.build_tree(tmp_path)
        out = scan_vscode([(paths["vs_root"], paths["vs_db"])], paths["cache"])
        dated = list(out["acme/alpha"]["by_dt"])
        assert dated == ["2026-05-02" + AM_SEP + "read_file"], dated
        assert datetime.date.today().isoformat() not in "".join(dated)
