"""Unit tests for the pure, side-effect-free helpers in usage.py.

These lock the small building blocks (identity, normalisation, patch replay,
bucket maths, merge/build) so the Phase 2 refactor cannot silently change them.
No live logs are touched — every input is synthetic.
"""
from __future__ import annotations

import datetime
import os
from collections import defaultdict

import pytest

import usage


def _ms(y: int, m: int, d: int, hh: int = 12) -> int:
    """Epoch-milliseconds at a fixed UTC time (avoids timezone edge cases)."""
    return int(datetime.datetime(y, m, d, hh, tzinfo=datetime.timezone.utc)
               .timestamp() * 1000)


# --------------------------------------------------------------------------- #
# identity / naming
# --------------------------------------------------------------------------- #
class TestRepoSlug:
    def test_https(self):
        assert usage.repo_slug("https://github.com/acme/repo.git") == "acme/repo"

    def test_git_ssh(self):
        assert usage.repo_slug("git@github.com:acme/repo.git") == "acme/repo"

    def test_bare_slug(self):
        assert usage.repo_slug("acme/repo") == "acme/repo"

    def test_trailing_slash(self):
        assert usage.repo_slug("https://github.com/acme/repo/") == "acme/repo"

    def test_empty(self):
        assert usage.repo_slug("") == ""
        assert usage.repo_slug(None) == ""


class TestProjectName:
    def test_basename(self):
        assert usage.project_name("C:/foo/bar") == "bar"

    def test_trailing_sep(self):
        assert usage.project_name("C:/foo/bar/") == "bar"

    def test_code_workspace_suffix(self):
        assert usage.project_name("C:/foo/proj.code-workspace") == "proj"

    def test_empty(self):
        assert usage.project_name("") == "(unknown)"


class TestUriToPath:
    def test_file_uri(self):
        assert usage.uri_to_path("file:///C:/foo/bar").replace(os.sep, "/") == "C:/foo/bar"

    def test_percent_encoded(self):
        assert usage.uri_to_path("file:///C:/a%20b").replace(os.sep, "/") == "C:/a b"

    def test_plain_path_passthrough(self):
        assert usage.uri_to_path("C:/plain") == "C:/plain"

    def test_empty(self):
        assert usage.uri_to_path("") == ""


class TestIsJunkCwd:
    def test_empty_is_junk(self):
        assert usage.is_junk_cwd("") is True

    def test_home_is_junk(self):
        assert usage.is_junk_cwd(usage.HOME) is True

    def test_copilot_chats_is_junk(self):
        p = os.path.join(usage.HOME, ".copilot", "chats", "abc")
        assert usage.is_junk_cwd(p) is True

    def test_real_project_is_not_junk(self):
        assert usage.is_junk_cwd(os.path.join("C:", os.sep, "work", "myproj")) is False


class TestCanon:
    def test_last_segment_lowercased(self):
        assert usage._canon("acme/Alpha") == "alpha"
        assert usage._canon("beta") == "beta"


# --------------------------------------------------------------------------- #
# normalisation
# --------------------------------------------------------------------------- #
class TestNormAgent:
    def test_none_is_base(self):
        assert usage._norm_agent(None) == "GitHub Copilot Chat"

    def test_internal_surfaces_collapse(self):
        for name in ("panel/editAgent", "SummarizeConversationHistory",
                     "default", "retry-foo", "copilotcli"):
            assert usage._norm_agent(name) == "GitHub Copilot Chat"

    def test_real_subagent_kept(self):
        assert usage._norm_agent("Researcher Subagent") == "Researcher Subagent"


class TestNormModel:
    def test_strips_copilot_prefix(self):
        assert usage._norm_model("copilot/claude-opus-4.8") == "claude-opus-4.8"

    def test_bare_name_kept(self):
        assert usage._norm_model("gpt-4.1") == "gpt-4.1"

    def test_falsy_is_refused_rather_than_renamed(self):
        # A model name we were never given is a fact worth surfacing, not a hole
        # to plug with "?" -- see INV-27.
        with pytest.raises(ValueError):
            usage._norm_model("")
        with pytest.raises(ValueError):
            usage._norm_model(None)


class TestAnyDate:
    def test_epoch_ms(self):
        assert usage._any_date(_ms(2026, 1, 2)) == "2026-01-02"

    def test_iso_string(self):
        assert usage._any_date("2026-03-04T05:06:07Z") == "2026-03-04"

    def test_short_string_is_none(self):
        assert usage._any_date("nope") is None

    def test_none(self):
        assert usage._any_date(None) is None


# --------------------------------------------------------------------------- #
# jsonl patch replay
# --------------------------------------------------------------------------- #
class TestSetAtPath:
    def test_nested_dict(self):
        obj: dict = {}
        usage._set_at_path(obj, ["a", "b"], 1)
        assert obj == {"a": {"b": 1}}

    def test_list_index(self):
        obj: dict = {}
        usage._set_at_path(obj, ["arr", 0], "x")
        assert obj == {"arr": ["x"]}


class TestAppendAtPath:
    def test_creates_and_appends(self):
        obj: dict = {}
        usage._append_at_path(obj, ["arr"], 1)
        usage._append_at_path(obj, ["arr"], 2)
        assert obj == {"arr": [1, 2]}


class TestReconstructJsonl:
    def test_kind_0_1_2(self, tmp_path):
        p = tmp_path / "s.jsonl"
        p.write_text(
            '{"kind":0,"v":{"requests":[]}}\n'
            '{"kind":1,"k":["title"],"v":"Hi"}\n'
            '{"kind":2,"k":["requests"],"v":{"timestamp":1}}\n',
            encoding="utf-8")
        state = usage._reconstruct_jsonl(str(p))
        assert state == {"requests": [{"timestamp": 1}], "title": "Hi"}


class TestLangsFromResponse:
    def test_value_part(self):
        resp = [{"value": "text ```python\nprint()``` more"}]
        assert usage._langs_from_response(resp) == ["python"]

    def test_nested_content_value(self):
        resp = [{"content": {"value": "```json\n{}```"}}]
        assert usage._langs_from_response(resp) == ["json"]

    def test_plain_string(self):
        assert usage._langs_from_response("```bash\nx```") == ["bash"]

    def test_unlabelled_and_nonalnum_skipped(self):
        assert usage._langs_from_response("``` \ncode```") == []
        assert usage._langs_from_response("```c++\nx```") == []


# --------------------------------------------------------------------------- #
# bucket maths
# --------------------------------------------------------------------------- #
class TestBuckets:
    def test_daybucket_shape(self):
        assert usage._daybucket() == {
            "sessions": 0, "requests": 0, "in": 0, "out": 0, "aiu": 0.0}

    def test_add_day_accumulates(self):
        m = usage._metrics()
        usage._add_day(m, "2026-01-01", sessions=1, requests=2, in_=10, out=3, aiu=1.5)
        usage._add_day(m, "2026-01-01", requests=1, aiu=0.5)
        b = m["by_day"]["2026-01-01"]
        assert (b["sessions"], b["requests"], b["in"], b["out"], b["aiu"]) == (1, 3, 10, 3, 2.0)

    def test_add_flat_accumulates(self):
        bucket: dict = defaultdict(usage._flatbucket)
        usage._add_flat(bucket, "gpt", requests=1, in_=5, out=2, aiu=0.25)
        usage._add_flat(bucket, "gpt", requests=1, in_=5, out=2, aiu=0.25)
        assert bucket["gpt"] == {"requests": 2, "in": 10, "out": 4, "aiu": 0.5}


# --------------------------------------------------------------------------- #
# merge + build
# --------------------------------------------------------------------------- #
def _metrics_with(day: str, requests: int, aiu: float, model: str = "gpt",
                  agent: str = "GitHub Copilot Chat", sessions: int = 1) -> dict:
    m = usage._metrics()
    usage._add_day(m, day, sessions=sessions, requests=requests, in_=requests, out=requests, aiu=aiu)
    usage._add_flat(m["by_model"], model, requests=requests, in_=requests, out=requests, aiu=aiu)
    usage._add_flat(m["by_agent"], agent, requests=requests, in_=requests, out=requests, aiu=aiu)
    usage._add_flat(m["by_am"], agent + usage._AM_SEP + model, requests=requests,
                    in_=requests, out=requests, aiu=aiu)
    return m


class TestMerge:
    def test_sums_across_members_and_rounds(self):
        d = {
            "acme/alpha": _metrics_with("2026-01-01", 2, 1.11115),
            "alpha": _metrics_with("2026-01-01", 3, 2.22225, sessions=1),
        }
        merged = usage._merge(d, ["acme/alpha", "alpha"])
        b = merged["by_day"]["2026-01-01"]
        assert b["requests"] == 5
        assert b["sessions"] == 2
        # aiu rounded to 4 dp
        assert b["aiu"] == round(1.11115 + 2.22225, 4)
        assert merged["by_model"]["gpt"]["requests"] == 5


class TestBuildProjects:
    def test_canon_merges_slug_and_basename(self):
        vs = {"acme/alpha": _metrics_with("2026-01-01", 2, 1.0)}
        cli = {"alpha": _metrics_with("2026-01-02", 3, 2.0)}
        rows = usage.build_projects(vs, cli, {})
        assert len(rows) == 1
        # fullest label (the one with a slash) wins
        assert rows[0]["name"] == "acme/alpha"
        # both members' days are present after merge
        assert set(rows[0]["vscode"]["by_day"]) == {"2026-01-01"}
        assert set(rows[0]["cli"]["by_day"]) == {"2026-01-02"}

    def test_distinct_projects_stay_separate(self):
        vs = {"acme/alpha": _metrics_with("2026-01-01", 1, 1.0)}
        cli = {"acme/beta": _metrics_with("2026-01-01", 1, 1.0)}
        rows = usage.build_projects(vs, cli, {})
        assert {r["name"] for r in rows} == {"acme/alpha", "acme/beta"}
