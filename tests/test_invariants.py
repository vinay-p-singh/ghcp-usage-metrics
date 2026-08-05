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
from ghcp.normalize import _any_date


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


def test_session_cells_decompose_to_the_day_and_model_totals(projects):
    """INV-28. ``by_sdm`` is the finest grain we record, so every coarser
    dimension has to be a projection of it.

    Dropping the session from the key must reproduce ``by_dm`` exactly; dropping
    the model as well must reproduce ``by_day``; dropping the date must
    reproduce ``by_model``. If these ever disagree, a session breakdown and the
    headline credits are telling different stories about the same requests.
    """
    from ghcp.constants import AM_SEP

    checked = 0
    for p in projects:
        for h in ("vscode", "cli", "claude"):
            rec = p[h]
            if not rec["by_sdm"]:
                continue
            checked += 1
            dm: dict[str, dict] = {}
            day: dict[str, dict] = {}
            model: dict[str, dict] = {}
            for key, b in rec["by_sdm"].items():
                _session, date, mdl = key.split(AM_SEP)
                for target, k in ((dm, date + AM_SEP + mdl), (day, date),
                                  (model, mdl)):
                    t = target.setdefault(k, {"requests": 0, "in": 0,
                                              "out": 0, "aiu": 0.0})
                    for f in ("requests", "in", "out", "aiu"):
                        t[f] += b[f]

            for f in ("requests", "in", "out", "aiu"):
                for k, t in dm.items():
                    assert abs(t[f] - rec["by_dm"][k][f]) < 1e-6, (
                        f"{p['name']} {h} by_dm[{k}] {f}")
                for k, t in day.items():
                    assert abs(t[f] - rec["by_day"][k][f]) < 1e-6, (
                        f"{p['name']} {h} by_day[{k}] {f}")
                for k, t in model.items():
                    assert abs(t[f] - rec["by_model"][k][f]) < 1e-6, (
                        f"{p['name']} {h} by_model[{k}] {f}")
    assert checked, "no session cells in the fixture -- this test proved nothing"


def test_a_session_cell_never_carries_a_session_count(projects):
    """INV-3, preserved. A session spans days and models, so its cells record
    magnitudes only; distinctness still comes from the key, never from a sum."""
    seen = 0
    for p in projects:
        for h in ("vscode", "cli", "claude"):
            for b in p[h]["by_sdm"].values():
                seen += 1
                assert "sessions" not in b
    assert seen, "no session cells in the fixture -- this test proved nothing"


def test_cached_tokens_are_a_subset_of_input_never_an_addition(projects):
    """INV-29. Every harness reports cache as part of what it already counted as
    input, so a cache figure can never exceed the input it came from.

    Verified against the raw logs before this was written: VS Code's
    ``cachedTokens`` never exceeded ``inputTokens`` across 5,464 events, the
    CLI's read+write never exceeded ``input_tokens`` across 953 rows, and
    Claude's cache fields are added into input at the point they are read.
    """
    seen = 0
    for p in projects:
        for h in ("vscode", "cli", "claude"):
            for dim in ("by_day", "by_model", "by_agent", "by_am", "by_dm", "by_sdm"):
                for key, b in p[h][dim].items():
                    assert b["cached"] <= b["in"], (
                        f"{p['name']} {h} {dim}[{key}] claims more cache than input")
                    assert b["cached_req"] <= b["requests"], (
                        f"{p['name']} {h} {dim}[{key}] counted more cache reports "
                        "than requests")
                    seen += b["cached"] > 0
    assert seen, "no cached tokens in the fixture -- this test proved nothing"


def test_a_request_that_reported_no_cache_is_not_recorded_as_zero_cache(projects):
    """INV-30. Cache reporting only began part-way through the recorded history,
    so 'no figure' must stay distinguishable from 'nothing was cached'.

    The fixture's s1 has two requests on the same day and model: one predating
    cache reporting, one reporting 150. Recording ``cached_req`` = 1 of 2 is the
    honest answer; silently calling the first one zero would claim we know
    something we do not.
    """
    vs = next(p for p in projects if p["name"] == "acme/alpha")["vscode"]
    cell = next(b for k, b in vs["by_dm"].items() if k.endswith("gpt-x")
                and b["requests"] >= 2)
    assert cell["cached_req"] < cell["requests"], (
        "every request appears to have reported a cache figure -- the fixture no "
        "longer covers the pre-reporting case this test exists for")
    assert cell["cached"] > 0, "the reporting request's cache figure was lost"


def test_a_session_name_is_recorded_only_when_the_source_wrote_one(projects):
    """INV-31. Roughly a third of VS Code sessions survive in the session store;
    the rest are purged. A missing name stays missing rather than being invented
    or back-filled from anything else."""
    named = {sid: name for p in projects for h in ("vscode", "cli", "claude")
             for sid, name in p[h]["session_names"].items()}
    assert named, "no session names in the fixture -- this test proved nothing"
    assert "s1" in named and named["s1"] == "Refactor the parser"
    assert "s2" not in named, "invented a name for a session that had none"
    for name in named.values():
        assert len(name) <= 120, "a session name was stored uncapped"


def test_retained_sessions_report_tokens_from_wherever_they_recorded_them(projects):
    """INV-32. A retained chat session may carry its counts on the request or
    under ``result.metadata``; both are the source's own figures.

    Reading only the top level scored 24 real requests as zero on live data --
    1.7M input tokens silently dropped. Found by comparing against the official
    report, which is exactly what a reconciliation is for.
    """
    vs = next(p for p in projects if p["name"] == "acme/alpha")["vscode"]
    cell = next(b for k, b in vs["by_sdm"].items() if k.startswith("s4"))
    assert cell["in"] == 700, "metadata-only prompt tokens were read as zero"
    assert cell["out"] == 40, "metadata-only completion tokens were read as zero"
    assert cell["aiu"] == 1.5


@pytest.mark.parametrize("value,expected", [
    (synthetic.ms(2026, 5, 1, 19), "2026-05-01"),
    ("2026-05-01T19:00:00Z", "2026-05-01"),
    ("2026-05-02T00:30:00+05:30", "2026-05-01"),
    ("2026-04-30T21:00:00-05:00", "2026-05-01"),
    ("2026-05-01T19:00:00", "2026-05-01"),
])
def test_a_day_is_a_utc_day_whatever_clock_the_source_wrote(value, expected):
    """INV-34. Harnesses disagree on how they stamp time: VS Code writes epoch
    milliseconds, the CLI and Claude Code write ISO-8601 strings. All three go
    through ``_any_date`` so the bucket is the UTC day in every case.

    The offset cases are the ones that matter. Slicing the first ten characters
    of ``2026-05-02T00:30:00+05:30`` yields 2026-05-02, which is a day late --
    that was the behaviour before this rule was written down, and it was only
    ever correct because every source happened to emit UTC.
    """
    assert _any_date(value) == expected


def test_a_day_is_never_invented_when_the_source_gave_nothing_usable():
    """INV-34, other half. Absent stays absent: an unparseable or missing stamp
    yields None so the caller can skip the record, rather than a guessed date
    that would silently move usage onto a day it did not happen."""
    for junk in (None, "", "not-a-date", [], {}):
        assert _any_date(junk) is None
