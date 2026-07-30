"""Keep every copy of the extractor identical to the source in this repo.

The tool lives in three places and each one has to work on its own:

  repo root                     the source of truth, what the tests run against
  skills/ghcp-usage-metrics/    committed, so downloading that folder alone
                                gives a working tool
  ~/.copilot/skills/...         what the chat agent actually loads

Nothing detects drift at runtime -- a stale copy simply reports different
numbers -- so this script both performs the sync and, with ``--check``, proves
it happened. Run it after touching usage.py, build_dashboard.py, ghcp/, web/,
or the skill's own SKILL.md and query.py.

Usage:
    python scripts/bundle_skill.py              sync repo + global copies
    python scripts/bundle_skill.py --check      report drift, exit 1, copy nothing
    python scripts/bundle_skill.py --no-global  skip the machine-local copy
"""
from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_NAME = "ghcp-usage-metrics"
REPO_SKILL = os.path.join(ROOT, "skills", SKILL_NAME)
GLOBAL_SKILL = os.path.join(os.path.expanduser("~"), ".copilot", "skills", SKILL_NAME)

# Everything a standalone copy needs to run. Extend when the source grows a new
# module or asset folder.
FILES = ("usage.py", "build_dashboard.py")
PACKAGES = ("ghcp", "web")

# Authored in the skill folder rather than at the root, so the repo copy is
# their source. The global copy still needs them: stale instructions send the
# agent looking for files that moved and describe limits that were since fixed.
SKILL_FILES = ("SKILL.md", "query.py")

# Written at runtime by whichever copy was last used; never part of the source.
IGNORED_DIRS = {"__pycache__", "out", ".cache", ".pytest_cache"}
IGNORED_SUFFIXES = (".pyc",)


def source_root(rel: str) -> str:
    """Where ``rel`` is authored -- the repo root, or the skill folder itself."""
    return REPO_SKILL if rel in SKILL_FILES else ROOT


def sources() -> list[str]:
    """Relative paths of every file that must exist, identically, in each copy."""
    paths = [f for f in FILES if os.path.isfile(os.path.join(ROOT, f))]
    paths += [f for f in SKILL_FILES if os.path.isfile(os.path.join(REPO_SKILL, f))]
    for package in PACKAGES:
        base = os.path.join(ROOT, package)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
            for name in filenames:
                if name.endswith(IGNORED_SUFFIXES):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, name), ROOT)
                paths.append(rel.replace("\\", "/"))
    return sorted(paths)


def drift(target: str) -> list[str]:
    """Source paths missing from ``target`` or differing from the source."""
    stale = []
    for rel in sources():
        dst = os.path.join(target, rel.replace("/", os.sep))
        src = os.path.join(source_root(rel), rel.replace("/", os.sep))
        if not (os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False)):
            stale.append(rel)
    return stale


def sync(target: str) -> tuple[list[str], list[str]]:
    """Copy sources into ``target``, drop generated junk. Returns (copied, pruned)."""
    copied = drift(target)
    for rel in copied:
        dst = os.path.join(target, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(source_root(rel), rel.replace("/", os.sep)), dst)

    pruned = []
    for dirpath, dirnames, _files in os.walk(target, topdown=True):
        for name in list(dirnames):
            if name in IGNORED_DIRS:
                victim = os.path.join(dirpath, name)
                shutil.rmtree(victim, ignore_errors=True)
                dirnames.remove(name)
                pruned.append(os.path.relpath(victim, target).replace("\\", "/"))
    return copied, pruned


def targets(include_global: bool) -> list[tuple[str, str]]:
    """(label, path) for each copy to keep in step; the global one may not exist."""
    out = [("skills/" + SKILL_NAME, REPO_SKILL)]
    if include_global and os.path.isdir(GLOBAL_SKILL):
        out.append(("~/.copilot/skills/" + SKILL_NAME, GLOBAL_SKILL))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sync the standalone skill copies.")
    ap.add_argument("--check", action="store_true",
                    help="report drift and exit 1 without copying anything")
    ap.add_argument("--no-global", action="store_true",
                    help="skip ~/.copilot/skills (the machine-local copy)")
    args = ap.parse_args(argv)

    if not os.path.isdir(REPO_SKILL):
        sys.exit(f"Skill folder missing: {REPO_SKILL}")

    todo = targets(not args.no_global)
    if args.check:
        stale = False
        for label, path in todo:
            missing = drift(path)
            if missing:
                stale = True
                print(f"STALE  {label}")
                for rel in missing:
                    print(f"         {rel}")
            else:
                print(f"ok     {label}")
        if stale:
            print("\nRun: python scripts/bundle_skill.py")
            return 1
        return 0

    for label, path in todo:
        copied, pruned = sync(path)
        if copied or pruned:
            print(f"{label}:")
            for rel in copied:
                print(f"  updated {rel}")
            for rel in pruned:
                print(f"  removed {rel}/ (generated)")
        else:
            print(f"{label}: already up to date")

    if not args.no_global and not os.path.isdir(GLOBAL_SKILL):
        print(f"note: no global copy at {GLOBAL_SKILL} (nothing to sync there)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
