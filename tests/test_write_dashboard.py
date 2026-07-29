"""Smoke test for the template-injection writer."""
from __future__ import annotations

import json
import os

import usage


def test_write_dashboard_fills_placeholders(tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setattr(usage, "OUT", str(out))
    sample = [{"name": "acme/alpha",
               "vscode": usage._merge({"acme/alpha": usage._metrics()}, ["acme/alpha"]),
               "cli": usage._merge({}, []),
               "claude": usage._merge({}, [])}]

    usage.write_dashboard(sample)

    html_path = out / "dashboard.html"
    json_path = out / "projects.json"
    assert html_path.is_file() and json_path.is_file()

    html = html_path.read_text(encoding="utf-8")
    assert "__DATA__" not in html
    assert "__GENERATED__" not in html
    # the injected JSON is present and round-trips
    assert json.loads(json_path.read_text(encoding="utf-8"))[0]["name"] == "acme/alpha"
    assert '"acme/alpha"' in html
