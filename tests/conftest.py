"""Shared pytest setup: make the repo-root modules importable.

``usage.py`` and ``dashboard_template.py`` live at the repository root (not in a
package), so add that root to ``sys.path`` before any test imports them.
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
