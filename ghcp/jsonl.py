"""VS Code chatSessions '.jsonl' patch replay + code-fence language extraction."""
from __future__ import annotations

import json


def _set_at_path(obj, keys, val) -> None:
    cur = obj
    for i, k in enumerate(keys[:-1]):
        want_list = isinstance(keys[i + 1], int)
        if isinstance(k, int):
            if not isinstance(cur, list):
                return
            while len(cur) <= k:
                cur.append([] if want_list else {})
            if cur[k] is None:
                cur[k] = [] if want_list else {}
            cur = cur[k]
        else:
            if not isinstance(cur, dict):
                return
            if k not in cur or cur[k] is None:
                cur[k] = [] if want_list else {}
            cur = cur[k]
    last = keys[-1]
    if isinstance(last, int):
        if not isinstance(cur, list):
            return
        while len(cur) <= last:
            cur.append(None)
        cur[last] = val
    elif isinstance(cur, dict):
        cur[last] = val


def _append_at_path(obj, keys, val) -> None:
    cur = obj
    for k in keys:
        if isinstance(k, int):
            if not isinstance(cur, list):
                return
            while len(cur) <= k:
                cur.append(None)
            if cur[k] is None:
                cur[k] = []
            cur = cur[k]
        else:
            if not isinstance(cur, dict):
                return
            if k not in cur or cur[k] is None:
                cur[k] = []
            cur = cur[k]
    if isinstance(cur, list):
        cur.append(val)


def _reconstruct_jsonl(path: str) -> dict:
    """Rebuild a VS Code chatSessions '.jsonl' patch log into its final object:
    kind 0 = full snapshot, kind 1 = set-at-path, kind 2 = append-at-path."""
    state: dict = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                kind = e.get("kind")
                k = e.get("k")
                v = e.get("v")
                if kind == 0:
                    state = v if isinstance(v, dict) else {}
                elif kind == 1 and isinstance(k, list) and k:
                    _set_at_path(state, k, v)
                elif kind == 2 and isinstance(k, list) and k:
                    _append_at_path(state, k, v)
    except Exception:
        return {}
    return state


def _langs_from_response(resp) -> list:
    """Code-fence languages in a chatSessions request response."""
    text = ""
    if isinstance(resp, list):
        for part in resp:
            if isinstance(part, dict):
                v = part.get("value")
                if not isinstance(v, str):
                    c = part.get("content")
                    if isinstance(c, dict):
                        v = c.get("value")
                if isinstance(v, str):
                    text += v
    elif isinstance(resp, str):
        text = resp
    out = []
    for seg in text.split("```")[1::2]:
        lang = seg.split("\n", 1)[0].strip().lower()
        if lang and len(lang) <= 15 and lang.isalnum():
            out.append(lang)
    return out
