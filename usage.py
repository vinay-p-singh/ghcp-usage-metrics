"""ghcp-usage — where the data lives, and the command that pulls it together.

This module owns three things and delegates everything else:

  * where the logs are on this platform (VS Code, Copilot CLI, Claude Code)
  * the ``--quick`` / ``--diagnostics`` command line
  * a probe that reports what is readable, for the extension's Diagnostics command

The scanning, parsing, aggregation and rendering live in the ``ghcp`` package.
The zero-argument ``scan_*`` wrappers below read the module-level paths at call
time, so tests can point the whole tool at a fixture by patching one constant
each -- while the implementations underneath take explicit paths and are
testable on their own.

Project identity prefers the git repo slug (owner/repo), falling back to the
folder or cwd basename. Nothing is estimated anywhere: values GitHub did not
record are reported as zero and explained in the diagnostics.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time

from ghcp.diagnostics import DIAG, coverage, diag_reset
from ghcp.model import build_projects
from ghcp.report import write_dashboard as _write_dashboard
from ghcp.scan.claude import scan_claude as _scan_claude
from ghcp.scan.cli import scan_cli as _scan_cli
from ghcp.scan.vscode import scan_vscode as _scan_vscode
from ghcp.window import set_quick_window

# Re-exported so ``usage.<name>`` stays importable: these are the module's public
# helpers, exercised directly by the test-suite. Imported for re-export only.
from ghcp.constants import AM_SEP as _AM_SEP  # noqa: F401  # pylint: disable=unused-import
from ghcp.jsonl import (_append_at_path, _langs_from_response,  # noqa: F401
                        _reconstruct_jsonl, _set_at_path)  # pylint: disable=unused-import
from ghcp.model import (_add_day, _add_flat, _daybucket,  # noqa: F401
                        _flatbucket, _merge, _metrics, _sessions,
                        _skillbucket)  # pylint: disable=unused-import
from ghcp.naming import (_canon, is_junk_cwd, project_name,  # noqa: F401
                         repo_slug, uri_to_path)  # pylint: disable=unused-import
from ghcp.normalize import (_any_date, _date_of_path, _norm_agent,  # noqa: F401
                            _norm_model, _utc_date_ms)  # pylint: disable=unused-import

HOME = os.path.expanduser("~")


def _vscode_base() -> str:
    """Directory holding the VS Code install folders, which differs per platform."""
    if sys.platform == "win32":
        return os.environ.get("APPDATA", "")
    if sys.platform == "darwin":
        return os.path.join(HOME, "Library", "Application Support")
    return os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config")


VS_BASE = _vscode_base()
VS_ROOT = os.path.join(VS_BASE, "Code", "User", "workspaceStorage")
VS_DB = os.path.join(VS_BASE, "Code", "User", "globalStorage",
                     "github.copilot-chat", "session-store.db")
CLI_HOME = os.path.join(HOME, ".copilot")
CLAUDE_ROOT = os.path.join(HOME, ".claude", "projects")
_ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(_ROOT, "out")
CACHE = os.path.join(_ROOT, ".cache", "vscode_billing.json")


def _vs_variants() -> list[tuple[str, str]]:
    """(workspaceStorage, session-store.db) pairs to scan. Always the current
    VS_ROOT/VS_DB (tests/users may point these elsewhere); plus sibling installs
    (Insiders / VSCodium / Exploration), but only when scanning the real default
    Code install \u2014 so an overridden VS_ROOT stays the single source scanned."""
    pairs = [(VS_ROOT, VS_DB)]
    default_root = os.path.join(VS_BASE, "Code", "User", "workspaceStorage") if VS_BASE else ""
    if VS_BASE and VS_ROOT == default_root:
        for variant in ("Code - Insiders", "VSCodium", "Code - Exploration"):
            r = os.path.join(VS_BASE, variant, "User", "workspaceStorage")
            if not os.path.isdir(r):
                continue
            db = os.path.join(VS_BASE, variant, "User", "globalStorage",
                              "github.copilot-chat", "session-store.db")
            pairs.append((r, db))
    return pairs


def scan_vscode() -> dict[str, dict]:
    """Scan every installed VS Code variant using this module's configured paths."""
    return _scan_vscode(_vs_variants(), CACHE)


def scan_cli() -> dict[str, dict]:
    """Scan the Copilot CLI store using this module's configured path."""
    return _scan_cli(CLI_HOME)


def scan_claude() -> dict[str, dict]:
    """Scan Claude Code sessions using this module's configured path."""
    return _scan_claude(CLAUDE_ROOT)


def write_dashboard(projects: list[dict], diag: dict | None = None) -> None:
    """Write dashboard.html + projects.json + diagnostics.json into ``OUT``."""
    _write_dashboard(projects, OUT, DIAG if diag is None else diag)


def diagnostics() -> dict:
    """What the extractor can actually see locally. Used by the *GHCP Usage:
    Diagnostics* command to explain why token/AIU data may be missing on a
    machine: it reports which VS Code roots were scanned and, critically, how
    many logs still carry the token/credit fields the dashboard needs
    (``inputTokens`` in debug-logs; ``promptTokens``/``copilotCredits`` in
    chatSessions). Log level is irrelevant \u2014 this is about what was retained.
    """
    info: dict = {
        "vscode_base": VS_BASE,
        "vscode_variants": [],
        "roots": [],
        "workspaces": 0,
        "debug_log_sessions": 0,
        "main_jsonl_with_tokens": 0,
        "chat_files": 0,
        "chat_files_with_tokens": 0,
    }
    if VS_BASE and os.path.isdir(VS_BASE):
        for d in os.scandir(VS_BASE):
            if d.is_dir() and d.name.lower().startswith("code"):
                info["vscode_variants"].append(d.name)
    for vs_root, _db in _vs_variants():
        info["roots"].append({"path": vs_root, "exists": os.path.isdir(vs_root)})
        if not os.path.isdir(vs_root):
            continue
        info["workspaces"] += len(glob.glob(os.path.join(vs_root, "*", "workspace.json")))
        for mj in glob.glob(os.path.join(
                vs_root, "*", "GitHub.copilot-chat", "debug-logs", "*", "main.jsonl")):
            info["debug_log_sessions"] += 1
            try:
                with open(mj, encoding="utf-8", errors="replace") as fh:
                    if any("inputTokens" in ln for ln in fh):
                        info["main_jsonl_with_tokens"] += 1
            except Exception:
                pass
        for cf in (glob.glob(os.path.join(vs_root, "*", "chatSessions", "*.json"))
                   + glob.glob(os.path.join(vs_root, "*", "chatSessions", "*.jsonl"))):
            info["chat_files"] += 1
            try:
                with open(cf, encoding="utf-8", errors="replace") as fh:
                    head = fh.read(300_000)
                if "promptTokens" in head or "copilotCredits" in head:
                    info["chat_files_with_tokens"] += 1
            except Exception:
                pass
    info["has_token_data"] = (info["main_jsonl_with_tokens"] > 0
                              or info["chat_files_with_tokens"] > 0)
    return info


def _quick_days(argv: list[str]) -> int:
    """Days requested via ``--quick [N]`` (default 10); 0 when absent."""
    if "--quick" not in argv:
        return 0
    i = argv.index("--quick")
    if i + 1 < len(argv) and argv[i + 1].isdigit():
        return int(argv[i + 1])
    return 10


def _totals(projects: list[dict]) -> tuple[int, int, int, float, int]:
    days: set[str] = set()
    sess = req = 0
    aiu = 0.0
    for p in projects:
        for client in (p["vscode"], p["cli"], p["claude"]):
            for date, b in client["by_day"].items():
                days.add(date)
                sess += b["sessions"]
                req += b["requests"]
                aiu += b["aiu"]
    return len(projects), sess, req, aiu, len(days)


def main() -> None:
    argv = sys.argv[1:]
    if "--diagnostics" in argv:
        print(json.dumps(diagnostics(), indent=2))
        return
    diag_reset()
    set_quick_window(_quick_days(argv))

    results = {}
    for key, fn in (("vscode", scan_vscode), ("cli", scan_cli), ("claude", scan_claude)):
        t0 = time.time()
        results[key] = fn()
        DIAG["elapsed"][key] = round(time.time() - t0, 2)
    projects = build_projects(results["vscode"], results["cli"], results["claude"])
    coverage(projects)
    DIAG["elapsed"]["total"] = round(sum(DIAG["elapsed"].values()), 2)
    write_dashboard(projects)

    nproj, sess, req, aiu, ndays = _totals(projects)
    print(f"projects: {nproj}  | sessions: {sess}  | requests: {req}  | "
          f"aiu: {round(aiu, 2)}  | active days: {ndays}")
    if DIAG["partial"]:
        deferred = sum(s["files_deferred"] for s in DIAG["sources"].values())
        print(f"PARTIAL: quick scan of the last {DIAG['quick_days']} days "
              f"({deferred} older files deferred to the full pass)")
    print(f"scan time: {DIAG['elapsed']['total']}s   "
          f"no-token requests: {DIAG['coverage']['requests_no_tokens']} "
          f"({DIAG['coverage']['pct_no_tokens']}%)")
    print("dashboard -> out/dashboard.html   data -> out/projects.json")


if __name__ == "__main__":
    main()
