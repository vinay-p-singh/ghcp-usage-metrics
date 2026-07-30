"""Golden masters: proof that a refactor changed structure and nothing else.

Both files under `tests/golden/` are recordings of what the code produces today.
Splitting a module, moving a function or extracting the template into separate
files must leave these byte-identical; if one moves, the refactor changed
behaviour and is wrong.

When a change to output *is* intended, regenerate deliberately and review the
diff as part of that change:

    $env:UPDATE_GOLDEN = "1"; python -m pytest tests/test_golden.py -q
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

import synthetic
from build_dashboard import DASHBOARD_TEMPLATE

GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")
UPDATING = os.environ.get("UPDATE_GOLDEN") == "1"

_REGEN = ('\nIf this change was intended, regenerate with:\n'
          '    $env:UPDATE_GOLDEN = "1"; python -m pytest tests/test_golden.py -q\n'
          'and review the diff in the same commit.')


def _read(name: str) -> str | None:
    path = os.path.join(GOLDEN, name)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _write(name: str, text: str) -> None:
    os.makedirs(GOLDEN, exist_ok=True)
    with open(os.path.join(GOLDEN, name), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def test_dashboard_template_is_unchanged():
    """The assembled HTML must survive being split into separate source files."""
    digest = hashlib.sha256(DASHBOARD_TEMPLATE.encode("utf-8")).hexdigest()
    body = f"{digest}  len={len(DASHBOARD_TEMPLATE)}\n"
    if UPDATING:
        _write("template.sha256", body)
        pytest.skip("golden updated")
    recorded = _read("template.sha256")
    assert recorded is not None, "missing tests/golden/template.sha256" + _REGEN
    assert body == recorded, (
        "the assembled dashboard HTML changed." + _REGEN)


def test_extractor_output_is_unchanged(tmp_path, monkeypatch):
    """Full scanner output for the synthetic tree, not just spot assertions."""
    projects = synthetic.scan(tmp_path, monkeypatch)
    body = json.dumps(projects, indent=2, sort_keys=True) + "\n"
    if UPDATING:
        _write("projects.json", body)
        pytest.skip("golden updated")
    recorded = _read("projects.json")
    assert recorded is not None, "missing tests/golden/projects.json" + _REGEN
    assert json.loads(body) == json.loads(recorded), (
        "the extractor produced different data for the synthetic tree." + _REGEN)
