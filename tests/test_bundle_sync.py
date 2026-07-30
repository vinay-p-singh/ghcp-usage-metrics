"""The standalone copies of the extractor must not drift from the source.

A stale copy does not crash -- it silently reports different numbers than the
repo does, which is the worst kind of bug to chase. The repo copy is committed,
so drift there is a hard failure. The global copy under ``~/.copilot/skills`` is
machine-local, so it is checked when present and skipped in CI.
"""
from __future__ import annotations

import importlib.util
import os

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_bundler():
    path = os.path.join(_ROOT, "scripts", "bundle_skill.py")
    spec = importlib.util.spec_from_file_location("bundle_skill", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bundler = _load_bundler()


def test_repo_skill_copy_is_in_sync():
    stale = bundler.drift(bundler.REPO_SKILL)
    assert not stale, (
        "skills/ghcp-usage-metrics is stale: " + ", ".join(stale)
        + "\nRun: python scripts/bundle_skill.py"
    )


def test_global_skill_copy_is_in_sync():
    if not os.path.isdir(bundler.GLOBAL_SKILL):
        pytest.skip("no global skill copy on this machine")
    stale = bundler.drift(bundler.GLOBAL_SKILL)
    assert not stale, (
        "~/.copilot/skills/ghcp-usage-metrics is stale: " + ", ".join(stale)
        + "\nRun: python scripts/bundle_skill.py"
    )


def test_every_root_module_is_bundled():
    """A new root module that nobody added to FILES would ship broken copies."""
    root_modules = {
        name for name in os.listdir(_ROOT)
        if name.endswith(".py") and not name.startswith(("_", "test_"))
    }
    missing = root_modules - set(bundler.FILES)
    assert not missing, (
        "root module(s) not bundled into the skill copies: " + ", ".join(sorted(missing))
        + "\nAdd them to FILES in scripts/bundle_skill.py"
    )


def test_every_skill_only_file_is_bundled():
    """SKILL.md and query.py are authored in the skill folder, not at the root.

    Nothing else carries them to ~/.copilot/skills, so an unbundled one leaves
    the chat agent loading instructions that describe an older tool.
    """
    authored = {
        name for name in os.listdir(bundler.REPO_SKILL)
        if os.path.isfile(os.path.join(bundler.REPO_SKILL, name))
        and not name.endswith(".pyc")
    }
    missing = authored - set(bundler.sources())
    assert not missing, (
        "skill file(s) never copied to the global skill: " + ", ".join(sorted(missing))
        + "\nAdd them to SKILL_FILES in scripts/bundle_skill.py"
    )


def test_generated_output_is_never_bundled():
    """out/, .cache/ and __pycache__ belong to whoever ran the tool, not the source."""
    for rel in bundler.sources():
        head = rel.split("/")[0]
        assert head not in bundler.IGNORED_DIRS
        assert not rel.endswith(".pyc")
