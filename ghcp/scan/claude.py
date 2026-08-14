"""Claude Code usage, from ``~/.claude/projects/<dir>/<session>.jsonl``.

Each file is one session; ``assistant`` events carry the real model and token
usage. Claude does not emit GitHub's AI-credit metric, so credits stay 0 here --
requests, input/output tokens, model and active days are all real recorded
values. A model of ``<synthetic>`` marks an injected or aborted turn, not a
billed call, so those are skipped.
"""
from __future__ import annotations

import glob
import json
import os
from collections import defaultdict

from ghcp.constants import AGENT_CLAUDE, AM_SEP
from ghcp.diagnostics import diag_err, src
from ghcp.model import _add_day, _add_flat, _metrics
from ghcp.naming import is_junk_cwd, project_name
from ghcp.normalize import _any_date
from ghcp.window import in_window


def scan_claude(claude_root: str) -> dict[str, dict]:
    """project -> metrics for the Claude Code sessions under ``claude_root``."""
    out: dict[str, dict] = defaultdict(_metrics)
    s = src("claude")
    s["roots"].append({"path": claude_root, "exists": os.path.isdir(claude_root)})
    if not os.path.isdir(claude_root):
        return out
    for path in glob.glob(os.path.join(claude_root, "*", "*.jsonl")):
        s["files_found"] += 1
        if not in_window(path):
            s["files_deferred"] += 1
            continue
        name = ""
        rows: list[tuple[str, str, int, int, int]] = []
        first_date: str | None = None
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if '"assistant"' not in line:
                        continue
                    try:
                        ev = json.loads(line)
                    except Exception:
                        s["bad_lines"] += 1
                        continue
                    if ev.get("type") != "assistant":
                        continue
                    msg = ev.get("message") or {}
                    model = msg.get("model") or ""
                    if not model or model == "<synthetic>":
                        continue
                    if not name:
                        cwd = ev.get("cwd") or ""
                        if cwd and not is_junk_cwd(cwd):
                            name = project_name(cwd)
                    date = _any_date(ev.get("timestamp"))
                    if not date:
                        continue
                    u = msg.get("usage") or {}
                    cached = ((u.get("cache_creation_input_tokens") or 0)
                              + (u.get("cache_read_input_tokens") or 0))
                    in_ = (u.get("input_tokens") or 0) + cached
                    out_ = u.get("output_tokens") or 0
                    rows.append((date, model, in_, out_, cached))
                    if first_date is None or date < first_date:
                        first_date = date
        except Exception as e:
            diag_err("claude", path, e)
            continue
        s["files_parsed"] += 1
        if not name or not rows:
            continue
        m = out[name]
        sid = os.path.splitext(os.path.basename(path))[0]
        for date, model, in_, out_, cached in rows:
            _add_day(m, date, requests=1, in_=in_, out=out_, cached=cached,
                     cached_req=1)
            for bucket, key in ((m["by_model"], model),
                                (m["by_agent"], AGENT_CLAUDE),
                                (m["by_da"], date + AM_SEP + AGENT_CLAUDE),
                                (m["by_am"], AGENT_CLAUDE + AM_SEP + model),
                                (m["by_dam"],
                                 date + AM_SEP + AGENT_CLAUDE + AM_SEP + model),
                                (m["by_dm"], date + AM_SEP + model),
                                (m["by_sdm"], sid + AM_SEP + date + AM_SEP + model)):
                _add_flat(bucket, key, requests=1, in_=in_, out=out_,
                          cached=cached, cached_req=1)
        if first_date:
            _add_day(m, first_date, sessions=1)
    return out
