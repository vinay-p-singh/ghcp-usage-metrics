"""What happens when one piece of the scan goes wrong.

A user's machine holds thousands of log files written by software we do not
control. One of them being unreadable, half-written or shaped unexpectedly is
normal; the whole report vanishing because of it is not. These tests pin the
two behaviours that follow from that: a failure inside one unit is recorded and
skipped, and a failure that really is fatal leaves a shareable file behind
rather than a wall of traceback in a notification.
"""
from __future__ import annotations

import json
import os

import pytest

import synthetic
import usage
from ghcp import window
from ghcp.diagnostics import DIAG, diag_reset
from ghcp.scan import vscode as vs


@pytest.fixture(autouse=True)
def _clean_state():
    diag_reset()
    window.set_quick_window(0)
    yield
    diag_reset()
    window.set_quick_window(0)


def _errors_mentioning(text: str) -> list[dict]:
    return [e for e in DIAG["errors"] if text in e["error"]]


class TestScanContainment:
    """One bad unit must cost that unit only."""

    def test_failing_session_dir_leaves_the_rest_of_the_workspace(self, tmp_path, monkeypatch):
        paths = synthetic.build_tree(tmp_path)
        real = vs._scan_session_dir

        def boom(entry, m, agent, cache):
            if entry.name == "s1":
                raise OSError("session dir on fire")
            return real(entry, m, agent, cache)

        monkeypatch.setattr(vs, "_scan_session_dir", boom)
        out = vs.scan_vscode([(paths["vs_root"], paths["vs_db"])], paths["cache"])

        assert out, "the scan aborted instead of skipping the broken session"
        # s2's subagent log is the proof the workspace kept going after s1 died.
        assert any("Researcher" in m["by_agent"] for m in out.values())
        assert _errors_mentioning("session dir on fire")

    def test_failing_chat_file_leaves_the_rest_of_the_workspace(self, tmp_path, monkeypatch):
        paths = synthetic.build_tree(tmp_path)
        real = vs.scan_chat_file

        def boom(cf, *a, **kw):
            if os.path.basename(cf) == "s3.json":
                raise ValueError("chat file on fire")
            return real(cf, *a, **kw)

        monkeypatch.setattr(vs, "scan_chat_file", boom)
        out = vs.scan_vscode([(paths["vs_root"], paths["vs_db"])], paths["cache"])

        assert out
        assert _errors_mentioning("chat file on fire")

    def test_failing_workspace_leaves_the_other_workspaces(self, tmp_path, monkeypatch):
        paths = synthetic.build_tree(tmp_path)
        synthetic.write(os.path.join(paths["vs_root"], "ws2", "workspace.json"),
                        json.dumps({"folder": "file:///C:/proj/beta"}))
        real = vs._scan_workspace

        def boom(vs_root, h, fallback, out, cache, maps, seen_sids):
            if h == "ws2":
                raise RuntimeError("workspace on fire")
            return real(vs_root, h, fallback, out, cache, maps, seen_sids)

        monkeypatch.setattr(vs, "_scan_workspace", boom)
        out = vs.scan_vscode([(paths["vs_root"], paths["vs_db"])], paths["cache"])

        assert "acme/alpha" in out, "ws1 was lost when ws2 failed"
        assert _errors_mentioning("workspace on fire")

    def test_failing_scanner_still_reports_the_others(self, tmp_path, monkeypatch):
        synthetic.point_usage_at(monkeypatch, synthetic.build_tree(tmp_path))
        monkeypatch.setattr(usage, "OUT", str(tmp_path / "out"))

        def boom():
            raise RuntimeError("cli store on fire")

        monkeypatch.setattr(usage, "scan_cli", boom)
        assert usage.cli([]) == 0

        projects = json.loads((tmp_path / "out" / "projects.json").read_text(encoding="utf-8"))
        assert any(p["name"] == "acme/alpha" for p in projects), "VS Code data was lost"
        diag = json.loads((tmp_path / "out" / "diagnostics.json").read_text(encoding="utf-8"))
        assert any("cli store on fire" in e["error"] for e in diag["errors"])


class TestCrashReport:
    """A fatal failure is written down once, in full, somewhere shareable."""

    def _fatal(self, tmp_path, monkeypatch):
        synthetic.point_usage_at(monkeypatch, synthetic.build_tree(tmp_path))
        monkeypatch.setattr(usage, "OUT", str(tmp_path / "out"))
        monkeypatch.setattr(usage, "build_projects",
                            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("kaboom")))

    def test_full_traceback_goes_to_the_log_file(self, tmp_path, monkeypatch, capsys):
        self._fatal(tmp_path, monkeypatch)
        assert usage.cli([]) == 1

        text = (tmp_path / "out" / "error.log").read_text(encoding="utf-8")
        assert "Traceback" in text
        assert "RuntimeError: kaboom" in text
        assert "python:" in text and "platform:" in text

    def test_stderr_stays_short_enough_for_a_notification(self, tmp_path, monkeypatch, capsys):
        self._fatal(tmp_path, monkeypatch)
        usage.cli([])

        err = capsys.readouterr().err.strip()
        assert "Traceback" not in err, "the whole traceback reached the notification again"
        assert len(err.splitlines()) <= 4
        assert str(tmp_path / "out" / "error.log") in err
        assert "kaboom" in err

    def test_a_successful_run_clears_an_old_report(self, tmp_path, monkeypatch):
        synthetic.point_usage_at(monkeypatch, synthetic.build_tree(tmp_path))
        monkeypatch.setattr(usage, "OUT", str(tmp_path / "out"))
        stale = tmp_path / "out" / "error.log"
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_text("yesterday's failure", encoding="utf-8")

        assert usage.cli([]) == 0
        assert not stale.exists(), "a fixed run still looks broken to the reader"
