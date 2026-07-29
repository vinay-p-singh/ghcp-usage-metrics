"""Structural invariants over the real, generated out/projects.json.

Unlike the synthetic golden-master these assert PROPERTIES that hold for any
data volume, so they stay green as usage grows day to day. They guard the shape
of the extractor output and the no-double-count property against refactors.

Skips cleanly when out/projects.json has not been generated yet.
"""
from __future__ import annotations

import json
import os

import pytest

import usage

_SNAPSHOT = os.path.join(os.path.dirname(usage.OUT), "out", "projects.json")

if not os.path.isfile(_SNAPSHOT):
    pytest.skip("out/projects.json not generated (run `python usage.py`)",
                allow_module_level=True)

with open(_SNAPSHOT, encoding="utf-8") as _fh:
    PROJECTS = json.load(_fh)

_CLIENT_DIMS = ("by_day", "by_model", "by_agent", "by_am", "by_skill", "by_tool", "by_lang")
# Per-bucket AIU is rounded to 4 dp, so summed dimensions may drift slightly.
_TOL = 0.05


def _sum(dim: dict, field: str) -> float:
    return sum(b.get(field, 0) for b in dim.values())


def test_projects_is_nonempty_list():
    assert isinstance(PROJECTS, list) and PROJECTS


def test_every_project_has_all_client_dimensions():
    for p in PROJECTS:
        assert "name" in p and p["name"]
        for surface in ("vscode", "cli", "claude"):
            assert surface in p, p["name"]
            for dim in _CLIENT_DIMS:
                assert dim in p[surface], f"{p['name']}/{surface}/{dim}"


def test_no_negative_values():
    for p in PROJECTS:
        for surface in ("vscode", "cli", "claude"):
            for b in p[surface]["by_day"].values():
                assert b["requests"] >= 0 and b["aiu"] >= -1e-9


def test_aiu_consistent_across_dimensions():
    """by_day / by_model / by_agent / by_am must report the same AIU per client."""
    for p in PROJECTS:
        for surface in ("vscode", "cli", "claude"):
            c = p[surface]
            base = _sum(c["by_day"], "aiu")
            for dim in ("by_model", "by_agent", "by_am"):
                assert abs(_sum(c[dim], "aiu") - base) <= _TOL, f"{p['name']}/{surface}/{dim}"


def test_am_splits_back_to_agents_and_models():
    for p in PROJECTS:
        for surface in ("vscode", "cli", "claude"):
            c = p[surface]
            ag: dict = {}
            md: dict = {}
            for key, b in c["by_am"].items():
                agent, _, model = key.partition(usage._AM_SEP)
                ag[agent] = ag.get(agent, 0.0) + b["aiu"]
                md[model] = md.get(model, 0.0) + b["aiu"]
            for agent, v in ag.items():
                assert abs(v - c["by_agent"].get(agent, {}).get("aiu", 0.0)) <= _TOL
            for model, v in md.items():
                assert abs(v - c["by_model"].get(model, {}).get("aiu", 0.0)) <= _TOL
