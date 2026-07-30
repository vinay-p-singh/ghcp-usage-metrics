"""Domain invariants that were true but unguarded.

Each test here corresponds to a numbered rule in [DOMAIN.md](../DOMAIN.md). They
were written after the fact, which is the wrong order -- but a rule that only
exists in prose is one refactor away from being quietly false, and that has
already happened once on this project. Better late than only-in-a-comment.

If one of these fails, the honest reading is that the invariant was never true
rather than that the test is wrong.
"""
from __future__ import annotations

import pytest

import synthetic
from ghcp.constants import NO_TOKEN
from ghcp.naming import _canon


@pytest.fixture(scope="module")
def projects(tmp_path_factory, request):
    mp = pytest.MonkeyPatch()
    request.addfinalizer(mp.undo)
    return synthetic.scan(tmp_path_factory.mktemp("invariants"), mp)


def test_claude_records_tokens_but_never_credits(projects):
    """INV-10. Claude Code publishes no credit figure, so ours must stay zero.

    A non-zero value here would mean we had started computing credits from token
    counts -- the exact estimation this tool refuses to do.
    """
    seen_tokens = False
    for p in projects:
        rec = p["claude"]
        for dim in ("by_day", "by_model", "by_agent", "by_am", "by_dm"):
            for key, b in rec[dim].items():
                assert b["aiu"] == 0, f"{p['name']} claude {dim}[{key}] claims credits"
                seen_tokens = seen_tokens or b["in"] > 0 or b["out"] > 0
    assert seen_tokens, "no Claude tokens in the fixture -- this test proved nothing"


def test_a_model_less_request_carries_no_tokens_and_no_credits(projects):
    """INV-11. The placeholder means 'the source recorded nothing', so anything
    filed under it must be a bare request count."""
    seen = 0
    for p in projects:
        for h in ("vscode", "cli", "claude"):
            rec = p[h]
            buckets = [(f"by_model[{NO_TOKEN}]", rec["by_model"].get(NO_TOKEN))]
            buckets += [(f"by_dm[{k}]", b) for k, b in rec["by_dm"].items()
                        if k.endswith(NO_TOKEN)]
            for label, b in buckets:
                if not b:
                    continue
                seen += 1
                assert b["requests"] > 0, f"{p['name']} {h} {label} is empty"
                for measure in ("in", "out", "aiu"):
                    assert b[measure] == 0, (
                        f"{p['name']} {h} {label} recorded {measure}={b[measure]}, "
                        "but a model-less request has no payload to record")
    assert seen, "no model-less requests in the fixture -- this test proved nothing"


def test_every_project_is_named_and_named_once(projects):
    """INV-12. Names are identity. An empty one is unusable, and two rows sharing
    a canonical basename means the merge that is supposed to join them did not."""
    seen: dict[str, str] = {}
    for p in projects:
        name = p["name"]
        assert name and name.strip(), "a project came through with no name"
        canon = _canon(name)
        assert canon not in seen, (
            f"{name!r} and {seen[canon]!r} share the basename {canon!r} "
            "but were not merged into one project")
        seen[canon] = name


def test_a_request_is_never_attributed_to_a_model_the_source_did_not_name(tmp_path):
    """INV-27. A billing event carrying tokens but no model name used to be filed
    under "?" -- a model that does not exist, invented to keep the loop going.

    It has never once happened: zero occurrences across 51 projects and 14,119
    requests. So it is not a domain concept, it is an unexamined guess about a
    log format. If the format ever does change, that is worth hearing about,
    not worth papering over with a placeholder nobody can interpret.

    `billing_or_defer` turns this into a diagnostics entry rather than a crash,
    so one odd event costs that file's billing and reports itself -- it does not
    take the scan down.
    """
    import json

    from ghcp.billing import billing_for_file

    log = tmp_path / "main.jsonl"
    log.write_text(json.dumps({
        "type": "llm_request", "ts": 1_780_000_000_000,
        "attrs": {"inputTokens": 10, "outputTokens": 2},   # no "model"
    }) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="no model"):
        billing_for_file(str(log), {})
