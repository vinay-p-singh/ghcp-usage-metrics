"""Assembles the dashboard from the source files in ``web/``.

The markup, styles and scripts used to live in one 2,000-line Python string,
which meant none of the JavaScript could be unit tested and every UI change
touched the same file. They are now real ``.html`` / ``.css`` / ``.js`` files;
this module only stitches them together into the single self-contained page the
extension and the browser both expect.

The JS modules are plain scripts sharing one scope, exactly as before -- they
are concatenated in filename order, so ``01-config.js`` runs before
``02-format.js``. Each pure module ends with a guarded ``module.exports`` so
``node --test`` can import it while the browser ignores it.

``web/`` is resolved relative to this file, so a copied skill folder or the
extension's bundled ``py/`` directory works with no configuration.
"""
from __future__ import annotations

import os

_ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(_ROOT, "web")

CSS_MARK = "<!--@css-->"
BOOT_MARK = "<!--@boot-js-->"
MAIN_MARK = "<!--@main-js-->"


def _read(*parts: str) -> str:
    with open(os.path.join(WEB, *parts), encoding="utf-8", newline="") as fh:
        return fh.read()


def _main_js() -> str:
    """Every js module except the head-boot one, in filename order."""
    js_dir = os.path.join(WEB, "js")
    names = sorted(n for n in os.listdir(js_dir)
                   if n.endswith(".js") and n != "boot.js")
    return "".join(_read("js", n) for n in names)


def build_template() -> str:
    """The complete page, with ``__DATA__``/``__DIAG__``/``__GENERATED__`` unfilled."""
    return (_read("dashboard.html")
            .replace(CSS_MARK, _read("dashboard.css"))
            .replace(BOOT_MARK, _read("js", "boot.js"))
            .replace(MAIN_MARK, _main_js()))


DASHBOARD_TEMPLATE = build_template()
