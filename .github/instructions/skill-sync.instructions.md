---
description: 'Keep the three copies of the extractor in sync and the tests honest whenever source files change.'
applyTo: 'usage.py, build_dashboard.py, ghcp/**, web/**, extension/src/**'
---

# Changing the extractor or dashboard

The tool ships from one source but runs from four places. None of them notice
when they fall behind — a stale copy just reports different numbers. So every
change to the files above ends with the same two commands.

## After any edit

```powershell
python -m pytest -q                    # Python + JS suites + the drift check
python scripts/bundle_skill.py         # syncs skills/ and ~/.copilot/skills/
node extension/scripts/bundle.js       # syncs extension/py/
```

`tests/test_bundle_sync.py` fails when a copy is stale, so a forgotten sync
shows up as a red test rather than as wrong numbers weeks later. The JS suite
runs inside pytest via `tests/test_js_suite.py`; run it alone with
`node --test "tests/js/*.test.js"`.

## Where each copy lives and why

| Copy | Purpose | Kept current by |
|---|---|---|
| repo root | source of truth; what the tests import | you |
| `skills/ghcp-usage-metrics/` | committed, so downloading that folder alone gives a working tool | `bundle_skill.py` |
| `~/.copilot/skills/ghcp-usage-metrics/` | what the chat agent actually loads | `bundle_skill.py` |
| `extension/py/` | bundled into the `.vsix`; gitignored, rebuilt at package time | `bundle.js` |

Adding a new root module or asset folder means adding it to `FILES` /
`PACKAGES` in [scripts/bundle_skill.py](../../scripts/bundle_skill.py) and to
`packages` in [extension/scripts/bundle.js](../../extension/scripts/bundle.js).
A test catches the first omission; nothing catches the second, so do both.

`SKILL.md` and `query.py` are authored inside `skills/ghcp-usage-metrics/`
rather than at the root, so that folder is their source and `SKILL_FILES`
carries them to `~/.copilot/skills/`. A new skill-only file belongs there too,
or the chat agent keeps loading the previous version of it.

## Write the test first

New behaviour starts with a failing test, not with the implementation:

1. Write or extend the test that describes what should happen. Run it and watch
   it fail for the right reason — a test that passes before the code exists is
   testing nothing.
2. Implement the smallest change that makes it pass.
3. Run the whole suite. A failure elsewhere means the change is wrong, not that
   the other test is wrong.
4. Sync the bundles.

A red test only proves something if it is red for the reason you predicted.
Two ways that quietly goes wrong, both seen in practice: a fixture that writes
to a key nothing reads (`project()` puts clients at the top level, not under
`.clients`) fails for the right message and the wrong reason; and editing a
shared fixture to suit a new test breaks every older test that relied on its
old shape. Read the failure message before writing the fix, and add a fixture
rather than reshaping one.

Fixtures also have to be faithful to the real data, not merely convenient. The
model filter looked complete against a fixture where model-less requests sat in
a project of their own — real logs file them beside real usage in projects that
have both, and `hideEmptyProjects` was quietly deleting the invented project
before the assertion could run.

Python logic belongs in `ghcp/` with a test in `tests/`. Pure dashboard logic —
formatting, config parsing, date maths, aggregation, pie geometry, forecasting,
agent ranking — belongs in `web/js/00-lib.js` with a test in `tests/js/`, run by
`node --test "tests/js/*.test.js"`. Anything that touches the DOM stays in the
numbered `web/js/NN-*.js` modules, which are concatenated in filename order and
share one scope; those are covered by `tests/js/interaction.test.js`, which
loads the real assembled page into jsdom.

`npm install` once to get the dev dependencies. jsdom is test-only — the
extractor, the dashboard, the `.vsix` and the skill bundle all ship with no
dependencies at all. Two jsdom limitations to know: it does not apply author
attribute-selector rules (so CSS `[hidden]` behaviour is asserted against the
stylesheet, not the computed style), and `let` at the top level of a classic
script is script-scoped, so tests cannot reach `CFG` or `DATA` from `window` —
drive those through the real controls instead.

## What the tests already lock

Do not weaken these without a deliberate decision:

- Per client, `sum(by_day.aiu)` equals `by_model`, `by_agent` and `by_am`.
  Any dimension disagreeing means something is double-counted.
- A chatSessions file whose session id already has a debug log is skipped.
- Subagent child logs attribute to their own agent, never the parent.
- The assembled dashboard HTML is byte-identical to its golden hash. When a UI
  change is intended, regenerate the hash deliberately in the same commit.

## Honesty rules that outrank tidiness

The dashboard only ever shows values GitHub actually recorded. Requests whose
source stored no tokens are counted as requests and contribute zero credits;
they are never estimated to fill a gap, and never dropped to make a chart look
complete. Anything unrecoverable is explained in the Diagnostics tab instead of
being smoothed over.
