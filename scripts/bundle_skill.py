"""Copy the extractor into the skill folder so the skill can run standalone.

The copies are committed, so anyone who downloads `skills/ghcp-usage-metrics/`
gets a working tool. Re-run this after changing usage.py, dashboard_template.py
or ghcp/, otherwise the bundled copy drifts from the source.
"""
from __future__ import annotations

import filecmp
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "skills", "ghcp-usage-metrics")
FILES = ("usage.py", "dashboard_template.py")
PACKAGE = "ghcp"


def _copy(src: str, dst: str, changed: list[str]) -> None:
    if not (os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False)):
        changed.append(os.path.relpath(dst, ROOT))
    shutil.copyfile(src, dst)


def main() -> int:
    if not os.path.isdir(SKILL):
        sys.exit(f"Skill folder missing: {SKILL}")
    changed: list[str] = []
    for name in FILES:
        _copy(os.path.join(ROOT, name), os.path.join(SKILL, name), changed)

    pkg_dst = os.path.join(SKILL, PACKAGE)
    os.makedirs(pkg_dst, exist_ok=True)
    for name in sorted(os.listdir(os.path.join(ROOT, PACKAGE))):
        if name.endswith(".py"):
            _copy(os.path.join(ROOT, PACKAGE, name),
                  os.path.join(pkg_dst, name), changed)

    if changed:
        print("updated:")
        for path in changed:
            print(f"  {path}")
    else:
        print("skill bundle already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
