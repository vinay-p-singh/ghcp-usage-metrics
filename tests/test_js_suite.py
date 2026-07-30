"""Run the JavaScript unit suite as part of `python -m pytest`.

The dashboard's pure helpers are tested by Node's built-in runner, but nobody
remembers a second command. Wiring it in here means one command covers both
languages -- and a broken helper fails the build rather than waiting to be
noticed as a wrong number on screen.

Skipped when Node or the dev dependencies are absent, so the Python suite still
runs on a machine that has never seen npm.
"""
from __future__ import annotations

import os
import shutil
import subprocess

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PATTERN = "tests/js/*.test.js"
_JSDOM = os.path.join(_ROOT, "node_modules", "jsdom")


def test_javascript_unit_suite_passes():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed; run `node --test \"tests/js/*.test.js\"` elsewhere")
    if not os.path.isdir(_JSDOM):
        pytest.skip("dev dependencies missing; run `npm install` for the interaction tests")
    proc = subprocess.run([node, "--test", _PATTERN], cwd=_ROOT,
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, (
        "JavaScript tests failed:\n" + proc.stdout + proc.stderr)
