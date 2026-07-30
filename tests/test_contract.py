"""The published shape of `out/projects.json`, written down once.

Three separate readers consume this file -- the dashboard, the chat skill's
`query.py`, and the VS Code extension -- so its key names are a contract, not an
implementation detail. The golden masters already prove the *values* are
unchanged; this proves the *names* are, and does it in a diff a human can read.

Renaming a key here is allowed. It just has to be deliberate: the assertion
below names every key in full, so the change shows up as an obvious edit rather
than as noise inside a regenerated recording.

`tests/golden/contract.json` is emitted from the real extractor output and is
what `tests/js/contract.test.js` checks the JS test harness against, so a
fixture cannot drift away from the shape the extractor actually produces.
"""
from __future__ import annotations

import json
import os

import pytest

import synthetic
from ghcp.constants import AGENT_CLAUDE, AGENT_CLI, AGENT_DEFAULT, AM_SEP, NO_TOKEN

GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")
UPDATING = os.environ.get("UPDATE_GOLDEN") == "1"

HARNESSES = ["vscode", "cli", "claude"]
PROJECT_KEYS = ["name"] + HARNESSES
DIMENSIONS = ["by_day", "by_model", "by_agent", "by_am", "by_dm", "by_sdm",
              "by_skill", "by_tool", "by_lang"]
DAY_FIELDS = ["sessions", "requests", "in", "out", "aiu"]
FLAT_FIELDS = ["requests", "in", "out", "aiu"]
SKILL_FIELDS = ["reads", "sessions", "requests", "in", "out", "aiu"]

# Dimensions whose key is two values joined by AM_SEP, and what those two are.
COMPOSITE = {"by_am": ["agent", "model"], "by_dm": ["date", "model"],
             "by_sdm": ["session", "date", "model"]}
# Dimensions that carry a plain count rather than a bucket of measures.
COUNTED = ["by_sdm", "by_tool", "by_lang"]


@pytest.fixture(scope="module")
def projects(tmp_path_factory, request):
    mp = pytest.MonkeyPatch()
    request.addfinalizer(mp.undo)
    return synthetic.scan(tmp_path_factory.mktemp("contract"), mp)


def test_a_project_carries_a_name_and_one_record_per_harness(projects):
    assert projects, "the synthetic tree produced no projects"
    for p in projects:
        assert sorted(p) == sorted(PROJECT_KEYS), p.get("name")


def test_every_harness_record_carries_every_dimension(projects):
    for p in projects:
        for h in HARNESSES:
            assert sorted(p[h]) == sorted(DIMENSIONS), f"{p['name']} / {h}"


def test_measures_are_named_the_same_wherever_they_appear(projects):
    for p in projects:
        for h in HARNESSES:
            rec = p[h]
            for b in rec["by_day"].values():
                assert sorted(b) == sorted(DAY_FIELDS)
            for dim in ("by_model", "by_agent", "by_am", "by_dm"):
                for b in rec[dim].values():
                    assert sorted(b) == sorted(FLAT_FIELDS), dim
            for b in rec["by_skill"].values():
                assert sorted(b) == sorted(SKILL_FIELDS)
            for dim in COUNTED:
                for c in rec[dim].values():
                    assert isinstance(c, int), dim


def test_only_the_composite_dimensions_use_the_separator(projects):
    for p in projects:
        for h in HARNESSES:
            for dim in DIMENSIONS:
                composite = dim in COMPOSITE
                for key in p[h][dim]:
                    assert (AM_SEP in key) == composite, f"{dim} key {key!r}"
                    if composite:
                        assert len(key.split(AM_SEP)) == len(COMPOSITE[dim]), (
                            f"{dim} key {key!r}")


def test_sessions_are_recorded_only_where_they_can_be_attributed(projects):
    # Session activity is a set of facts, not an additive measure. A mixed-model
    # session appears in several by_sdm facts but is counted distinctly by its ID.
    for p in projects:
        for h in HARNESSES:
            for dim in ("by_model", "by_agent", "by_am", "by_dm"):
                for b in p[h][dim].values():
                    assert "sessions" not in b, dim


def test_the_contract_is_recorded_for_the_javascript_side(projects):
    body = json.dumps({
        "harnesses": HARNESSES,
        "project_keys": PROJECT_KEYS,
        "dimensions": DIMENSIONS,
        "day_fields": DAY_FIELDS,
        "flat_fields": FLAT_FIELDS,
        "skill_fields": SKILL_FIELDS,
        "counted_dimensions": COUNTED,
        "composite_dimensions": COMPOSITE,
        "separator": AM_SEP,
        "sentinels": {"no_token_model": NO_TOKEN,
                      "default_agent": AGENT_DEFAULT,
                      "cli_agent": AGENT_CLI,
                      "claude_agent": AGENT_CLAUDE},
    }, indent=2, sort_keys=True) + "\n"
    path = os.path.join(GOLDEN, "contract.json")
    if UPDATING or not os.path.isfile(path):
        os.makedirs(GOLDEN, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        if UPDATING:
            pytest.skip("golden updated")
    with open(path, encoding="utf-8") as fh:
        assert json.loads(fh.read()) == json.loads(body), (
            "the published contract changed; regenerate with UPDATE_GOLDEN=1 "
            "and update tests/js/contract.test.js in the same commit")
