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

_CLIENT_DIMS = ("by_day", "by_model", "by_agent", "by_am", "by_dm", "by_skill", "by_tool", "by_lang")
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
            for dim in ("by_model", "by_agent", "by_am", "by_dm"):
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


def test_claude_records_tokens_but_never_credits():
    """INV-10 against real data. Claude publishes no credit figure of its own."""
    for p in PROJECTS:
        for dim in ("by_day", "by_model", "by_agent", "by_am", "by_dm"):
            for key, b in p["claude"][dim].items():
                assert b.get("aiu", 0) == 0, f"{p['name']}/claude/{dim}[{key}]"


def test_model_less_requests_carry_no_tokens_and_no_credits():
    """INV-11 against real data -- 625 such requests across 40 projects today.

    These are real calls whose source never wrote a token payload. If one ever
    turns up carrying tokens, the placeholder is being used for something other
    than 'nothing was recorded' and the filter semantics stop making sense.
    """
    from ghcp.constants import NO_TOKEN
    for p in PROJECTS:
        for surface in ("vscode", "cli", "claude"):
            c = p[surface]
            found = [("by_model", NO_TOKEN, c["by_model"].get(NO_TOKEN))]
            found += [("by_dm", k, b) for k, b in c["by_dm"].items()
                      if k.rpartition(usage._AM_SEP)[2] == NO_TOKEN]
            for dim, key, b in found:
                if not b:
                    continue
                for measure in ("in", "out", "aiu"):
                    assert b.get(measure, 0) == 0, (
                        f"{p['name']}/{surface}/{dim}[{key}] has {measure}={b[measure]}")


def test_session_cells_decompose_to_the_coarser_dimensions():
    """INV-28 against real data.

    ``by_sdm`` is the finest grain recorded, so dropping the session from its key
    must reproduce ``by_dm``, and dropping the model as well must reproduce
    ``by_day``. This is what lets a per-session view and the headline credits be
    two readings of the same requests rather than two different claims.
    """
    checked = 0
    for p in PROJECTS:
        for surface in ("vscode", "cli", "claude"):
            c = p[surface]
            if not c["by_sdm"]:
                continue
            checked += 1
            dm: dict[str, float] = {}
            day: dict[str, float] = {}
            req_day: dict[str, int] = {}
            for key, b in c["by_sdm"].items():
                _session, date, model = key.split(usage._AM_SEP)
                dm[date + usage._AM_SEP + model] = (
                    dm.get(date + usage._AM_SEP + model, 0.0) + b["aiu"])
                day[date] = day.get(date, 0.0) + b["aiu"]
                req_day[date] = req_day.get(date, 0) + b["requests"]
            for key, v in dm.items():
                assert abs(v - c["by_dm"].get(key, {}).get("aiu", 0.0)) <= _TOL, (
                    f"{p['name']}/{surface}/by_dm[{key}]")
            for date, v in day.items():
                assert abs(v - c["by_day"].get(date, {}).get("aiu", 0.0)) <= _TOL, (
                    f"{p['name']}/{surface}/by_day[{date}]")
                assert req_day[date] == c["by_day"].get(date, {}).get("requests", 0), (
                    f"{p['name']}/{surface}/by_day[{date}] requests")
    assert checked, "no session cells in the snapshot -- this test proved nothing"


def test_cached_tokens_never_exceed_the_input_they_came_from():
    """INV-29 against real data. Cache is part of the input each harness already
    counted, never an addition to it. If this ever fails, either a harness
    changed its convention or we started adding a figure twice."""
    seen = 0
    for p in PROJECTS:
        for surface in ("vscode", "cli", "claude"):
            for dim in ("by_day", "by_model", "by_agent", "by_am", "by_dm", "by_sdm"):
                for key, b in p[surface][dim].items():
                    assert b["cached"] <= b["in"], (
                        f"{p['name']}/{surface}/{dim}[{key}]: cached {b['cached']} "
                        f"> in {b['in']}")
                    assert b["cached_req"] <= b["requests"], (
                        f"{p['name']}/{surface}/{dim}[{key}]: more cache reports "
                        "than requests")
                    seen += b["cached"] > 0
    assert seen, "no cached tokens in the snapshot -- this test proved nothing"


def test_session_names_are_capped_and_never_invented():
    """INV-31 against real data. Names come straight from the session stores, so
    they exist only where a store still holds the session.

    A named session need not have any request cells: a CLI session that predates
    per-request billing is counted as a session with no recorded requests, and
    naming it is still honest. What must not happen is naming more sessions than
    the harness counted, which would mean names were being invented.
    """
    named = 0
    for p in PROJECTS:
        for surface in ("vscode", "cli", "claude"):
            names = p[surface]["session_names"]
            counted = sum(b["sessions"] for b in p[surface]["by_day"].values())
            for sid, name in names.items():
                named += 1
                assert isinstance(name, str) and name.strip(), f"{p['name']} {sid}"
                assert len(name) <= 120, f"{p['name']} session {sid} name uncapped"
            assert len(names) <= counted, (
                f"{p['name']}/{surface}: {len(names)} names for {counted} sessions")
    assert named, "no session names in the snapshot -- this test proved nothing"
