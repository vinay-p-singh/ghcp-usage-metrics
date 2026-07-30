"""Writing the report: data into the template, artifacts onto disk.

``dashboard.html`` is self-contained so it can be opened straight from disk or
hosted in the extension's webview. ``projects.json`` and ``diagnostics.json`` sit
beside it for the query CLI and for pasting into a bug report.
"""
from __future__ import annotations

import datetime
import json
import os

from build_dashboard import DASHBOARD_TEMPLATE


def generated_stamp(now: datetime.datetime | None = None) -> str:
    """Local build time like '24/7/2026, 4:10:13 pm'."""
    now = now or datetime.datetime.now()
    h12 = now.hour % 12 or 12
    ampm = "am" if now.hour < 12 else "pm"
    return f"{now.day}/{now.month}/{now.year}, {h12}:{now.minute:02d}:{now.second:02d} {ampm}"


def render(projects: list[dict], diag: dict, stamp: str | None = None) -> str:
    """The complete dashboard HTML for this dataset."""
    return (DASHBOARD_TEMPLATE
            .replace("__DATA__", json.dumps(projects))
            .replace("__DIAG__", json.dumps(diag))
            .replace("__GENERATED__", stamp or generated_stamp()))


def write_dashboard(projects: list[dict], out_dir: str, diag: dict) -> None:
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "dashboard.html"), "w", encoding="utf-8") as f:
        f.write(render(projects, diag))
    with open(os.path.join(out_dir, "projects.json"), "w", encoding="utf-8") as f:
        json.dump(projects, f, indent=2)
    with open(os.path.join(out_dir, "diagnostics.json"), "w", encoding="utf-8") as f:
        json.dump(diag, f, indent=2)
