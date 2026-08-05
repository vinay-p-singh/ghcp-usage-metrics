# Domain

The vocabulary and the rules. [ARCHITECTURE](ARCHITECTURE.md) explains how the
code is arranged; this explains what the words mean and what must stay true.

It exists because of a specific failure. The claim *"GitHub's per-day telemetry
records no model"* was written into three files, quoted in the docs, and pinned
by a passing test. It was false — the logs had carried the date and the model on
the same event all along, and the code was discarding the pairing. Nothing
caught it, because a rule that lives in prose has nothing to fail against.

So: every rule below is either enforced by a named test, or explicitly marked as
not yet enforced. There is no third category.

---

## The ubiquitous language

One agreed word per concept. Where the code currently uses a different word, the
disagreement is recorded rather than hidden.

| Term | Means | Notes |
|---|---|---|
| **Harness** | The tool that produced the record: VS Code, Copilot CLI, Claude Code | The code says `client` (`CLIENT_KEYS`, `by_client`), the UI says "Harness". Same thing. |
| **Project** | The unit a reader cares about; the aggregate root | Identified by git remote slug, else folder leaf. `_canon` merges rows sharing a basename. |
| **Request** | One recorded call to a model | The atomic fact. Everything else is a sum of these. |
| **Session** | A distinct conversation containing requests | Unfiltered totals use every recorded session; model-filtered totals intersect activity facts with selected dates and models. |
| **Day** | A **UTC** calendar day | Local midnight is not a boundary. Every harness normalises through `_any_date`, so a request at 19:00 UTC files under that UTC date even where the reader's clock already says tomorrow. |
| **Machine scope** | This machine's harnesses, and nothing else | The unit of measurement is *this device*, not the account. GitHub bills the account. See [Known tensions](#the-tool-measures-a-machine-github-bills-an-account). |
| **Measure** | A number that sums: requests, in, out, aiu, cached | Never estimated. Sessions are distinct entities, not an additive model measure. |
| **Cached tokens** | Input that was served from the model's prompt cache | A *subset* of `in`, never an addition. 89.6% of all recorded input on this machine. |
| **Miss tokens** | Input that was not served from cache: `in - cached` | Derived when displayed, never stored — storing both halves invites them to disagree. |
| **Coverage counter** | `cached_req`: how many of a bucket's requests reported a cache figure | Cache reporting began part-way through the history, so "not reported" must stay distinct from "nothing cached". |
| **Session name** | The short summary a session store recorded for a session | Present for ~69% of sessions; the rest were purged. Absent means absent — shown by id. |
| **Credit onset** | The first date a harness reported any AI credits | VS Code 2026-05-17, Copilot CLI 2026-07-09. Claude Code has none and never will. |
| **Coverage floor** | The latest onset among harnesses that report credits at all | Below it a total is arithmetically right and materially incomplete. Computed, never hardcoded. |
| **Dimension** | A way of grouping requests: by day, model, agent, skill, tool, language | A projection of the same facts, not separate data. |
| **Composite dimension** | A dimension keyed on multiple values joined by the separator | `by_am` (agent × model), `by_dm` (date × model), and `by_sdm` (session × date × model). |
| **Credit / AIU** | GitHub's own `copilotUsageNanoAiu ÷ 1e9` | Never computed by us. Claude Code reports none, so its credits are zero — a fact, not a gap. |
| **Agent** | Overloaded — see [Known tensions](#known-tensions) | Three distinct meanings in the code today. |
| **Placeholder** | A stand-in for a value the source never recorded | `(no token data)` for an unrecorded model. Not a member of the set it sits in. |

---

## The aggregates

```text
Project  (aggregate root — the only thing the dashboard lists)
  │
  ├── name                     identity; merged across harnesses by basename
  │
  └── one record per Harness   vscode │ cli │ claude
        │
        ├── by_day     date          → sessions, requests, in, out, aiu, cached, cached_req
        ├── by_model   model         → requests, in, out, aiu, cached, cached_req
        ├── by_agent   agent         → requests, in, out, aiu, cached, cached_req
        ├── by_am      agent×model   → requests, in, out, aiu, cached, cached_req
        ├── by_dm      date×model    → requests, in, out, aiu, cached, cached_req
        ├── by_sdm     session×date×model → the same measures
        ├── by_skill   skill         → reads, sessions, requests, in, out, aiu
        ├── by_tool    tool          → count
        ├── by_lang    language      → count
        └── session_names  session   → the name its source recorded, if any
```

Every dimension is the same set of requests, sliced differently. That is why the
totals must agree, and why disagreement means something is double-counted rather
than merely inconsistent.

`by_sdm` is the finest grain recorded, so every coarser dimension is a projection
of it: drop the session and it is `by_dm`, drop the model too and it is `by_day`.

Session *counts* remain on `by_day` and `by_skill`, and never appear on a
breakdown. A session spans days and models, so its cells carry magnitudes only —
distinctness comes from counting distinct keys, never from summing a measure. A
session that used two models has two cells and still counts once.

---

## What a request always and never has

Derived from the live data, not assumed. Verified across all 51 projects.

| | always | never |
|---|---|---|
| a request | a date, a harness, a project | — |
| a recorded request | a model, tokens, credits | — |
| a **model-less** request | a date, a request count of 1 | tokens, credits, a model |

Model-less requests are real calls whose source never wrote a token payload —
pre-telemetry CLI turns and trimmed-session activity floors. They are filed under
the `(no token data)` placeholder. Confirmed on live data: 625 such requests
across 40 projects, and **not one carries a single token or credit**.

---

## The invariant register

Status is either the test that enforces it, or `NOT ENFORCED`.

### Extraction

| # | Invariant | Enforced by |
|---|---|---|
| INV-1 | Per harness, total credits agree across `by_day`, `by_model`, `by_agent`, `by_am`, `by_dm` | `test_extract_synthetic`, `test_snapshot_live` |
| INV-2 | `by_dm` decomposes on both axes: summed per date it equals `by_day`, per model it equals `by_model` | `test_extract_synthetic`, `test_snapshot_live` |
| INV-28 | `by_sdm` decomposes on every axis: dropping the session reproduces `by_dm`, dropping the model too reproduces `by_day`, dropping the date reproduces `by_model` | `test_invariants`, `test_snapshot_live` |
| INV-29 | `cached` never exceeds `in`, and `cached_req` never exceeds `requests` — cache is a subset of input, not an addition | `test_invariants`, `test_snapshot_live` |
| INV-30 | A request that reported no cache figure is not recorded as zero cache; it raises `requests` without raising `cached_req` | `test_invariants` |
| INV-31 | A session name exists only where a session store recorded one, capped at 120 characters, and never exceeds the sessions the harness counted | `test_invariants`, `test_snapshot_live` |
| INV-32 | A retained chat session's tokens are read whether the source wrote them on the request or under `result.metadata` | `test_invariants` |
| INV-33 | The coverage floor is the latest credit onset among reporting harnesses; a harness that never reports credits cannot hold it back, and no credits anywhere yields no floor rather than a guess | `test_quick_and_diagnostics`, `tests/js/qualify.test.js` |
| INV-34 | Every harness buckets a request on its **UTC** day. A source timestamp is normalised through `_any_date`, never sliced as a raw string, so a local-midnight boundary cannot move a request between days | `test_invariants` |
| INV-3 | No breakdown carries a session count; sessions are counted by distinct `by_sdm` key, never summed | `test_contract`, `test_invariants`, `test_extract_synthetic` |
| INV-4 | Only declared composite dimensions use the separator, with exactly the declared number of parts | `test_contract` |
| INV-5 | A project carries a name and exactly one record per harness, each with every dimension | `test_contract` |
| INV-6 | A chat session already covered by a debug log is skipped, never counted twice | `test_extract_synthetic` |
| INV-7 | A subagent's tokens are attributed to the subagent, never to its parent | `test_extract_synthetic` |
| INV-8 | A memoised log is used even when it falls outside the quick-scan window | `test_quick_and_diagnostics` |
| INV-9 | Requests that could not be parsed are counted as skipped, never as zero-usage requests | `test_quick_and_diagnostics` |
| INV-10 | Claude Code records tokens but never credits | `test_invariants`, `test_snapshot_live` |
| INV-11 | A model-less request carries zero tokens and zero credits | `test_invariants`, `test_snapshot_live` |
| INV-12 | Every project name in the output is non-empty and de-duplicated by canonical basename | `test_invariants` |
| INV-27 | A request is never attributed to a model the source did not name — a missing name is refused and reported, not replaced | `test_invariants`, `test_helpers` |

### Dashboard

| # | Invariant | Enforced by |
|---|---|---|
| INV-13 | Unticking a model re-scopes credits, requests, tokens, sessions, projects, and days | `interaction.test.js` |
| INV-14 | Unfiltered totals retain every recorded session; a filtered session counts once when selected-model activity occurred inside the selected date range, and unattributed activity cannot match | `dimensions.test.js`, `interaction.test.js` |
| INV-15 | The no-model placeholder is never offered as a filterable model | `interaction.test.js` |
| INV-16 | The model list follows the selected date range rather than reporting lifetime | `dimensions.test.js` |
| INV-17 | Projects with no recorded usage are demoted, never discarded | `qualify.test.js` |
| INV-18 | Demotion is judged on lifetime usage, so the sidebar does not reshuffle as the range moves | **NOT ENFORCED** |
| INV-19 | A project the reader unticked stays unticked when a setting changes | `interaction.test.js` |
| INV-20 | Agents that recorded no credits keep their real request counts | `insights.test.js` |
| INV-21 | The priciest-per-request ranking ignores agents below a minimum sample | `insights.test.js` |
| INV-22 | A project name containing markup cannot inject HTML | `interaction.test.js` |
| INV-35 | The reconciliation panel compares against an externally supplied figure and never alters a recorded total; when the current date falls outside the entered cycle it reports itself stale rather than comparing | `reconcile.test.js` |

### Structure

| # | Invariant | Enforced by |
|---|---|---|
| INV-23 | The assembled dashboard HTML is byte-identical unless deliberately regenerated | `test_golden` |
| INV-24 | All four copies of the extractor stay in sync | `test_bundle_sync` |
| INV-25 | The test harness builds data in the shape the extractor really produces | `contract.test.js` |
| INV-26 | The dashboard splits composite keys on the separator the extractor wrote | `contract.test.js` |

---

## Known tensions

Recorded because each one has already caused a bug or is positioned to.

### The tool measures a machine, GitHub bills an account

Everything here is read from **this device's** local logs. GitHub's own
"usage this cycle" counter is account-wide, so the two answer different
questions and are not expected to be equal. Our figure should always be the
smaller one; if it ever exceeds GitHub's, something is double-counted.

The difference is made up of activity we cannot see by construction:

- the same licence used on **another machine**
- Copilot on **github.com** — chat, code review, PR summaries
- the **coding agent** running server-side
- mobile
- spend after the most recent scan, including the session doing the scanning

This is a deliberate limit, not a defect. A local-log reader cannot observe
surfaces that never write to this disk, and no amount of parsing will change
that. The reconciliation panel exists to make the gap **visible and
attributable** rather than to close it — which is why it never adjusts a
recorded number to match.

Measured on 2026-08-05 against a stated 47,752 credits for the cycle opening
2026-07-31: we accounted for 43,387 (90.9%), on a machine the reader confirmed
was their only one.

### The coverage floor is a first-sighting rule, not a completeness rule

`credit_floor` takes a harness's onset to be the first date it reported *any*
credits. That is correct for the data we have — the CLI's billing table starts
abruptly and is complete after — but it is fragile by construction: one stray
early credit would drag the floor backwards and hide the wrong period.

Measured, and the reason this is written down rather than fixed: the CLI's
`~/.copilot/session-state/*/events.jsonl` rollups carry credits on only **31 of
209** otherwise-usable sessions, scattered from 2026-05-13 to the present. Had
that source been adopted, three May sessions would have moved the CLI onset back
two months on the strength of 1.4% of the data.

The honest definition is "the first date from which the harness credits
essentially all of its token-bearing requests". That needs a threshold and has
to tolerate an incomplete trailing edge, so it is a judgement call rather than a
correction. **Decided: leave the first-sighting rule, document the weakness.**

### The CLI keeps a session store we deliberately do not read

`~/.copilot/session-state/<sid>/events.jsonl` (286 files, 215 MB) carries
per-model `modelMetrics` with input, output, cache read/write, reasoning and
`totalNanoAiu`, and **277 of 286 sessions have no row in the billing table**. It
is tempting, and it is not used. Three findings decided it:

- Only **31 of 209** clean sessions record credits at all; 178 record tokens and
  zero credits, right up to the present. Adopting the 31 would cherry-pick the
  expensive sessions — 14,444 of 18,479 credits come from three of them.
- **11 sessions span 2–4 days** and the rollup is a session total, so a date
  would have to be chosen. `assistant.message` events carry a timestamp, a model
  and `outputTokens` — but no input, cache or credits — so a per-day split would
  be estimation.
- **4 sessions carry contradictory rollups.** One repeats an identical total four
  times (last-wins is right, summing overcounts 4×); another goes 49.5M then
  21.9M (a counter reset, so last-wins *under*counts). No single rule is correct
  for all of them.

What the investigation did establish, and is kept: its cache read + write comes
to **99.4%** of input against the official report's **99.85%**, confirming that
GitHub counts cache *writes* as cached input while VS Code's `cachedTokens`
reports reads only. That is why our VS Code cache share reads ~94% and the CLI's
reads ~99%, and why the two are not directly comparable.

### A comment that outlived its truth

`web/js/01-config.js` still states that the per-day buckets carry no model
dimension and that "pretending otherwise would be a lie". The code directly
below it re-scopes every figure by model, correctly. The comment is the lie now.
Five call sites were corrected when `by_dm` was added; the sentence that caused
the misconception was missed.

**The lesson is not "update comments".** It is that a claim about the data was
never checked against the data. INV-13 now fails if the behaviour regresses; the
comment has no such protection, which is why it must not be the place a rule
lives.

### "Agent" means three things

1. A **display agent** — the harness itself (`GitHub Copilot Chat`, `Copilot CLI`, `Claude Code`)
2. An **internal surface** — `panel/editAgent`, `summarizeConversationHistory`, which collapse into the display agent
3. A **named subagent** — launched via `runSubagent`, with its own child log and its own credits

The dashboard's Agents tab splits 1 from 3 by consulting a hardcoded list of
three names. Python holds the same three names as constants. Two copies of one
fact.

### A placeholder living inside the set it stands outside

`(no token data)` is stored as if it were a model. It is not one — it means *no
model was recorded*. Every consumer therefore has to remember to special-case it,
and each site that forgets produces a bug. That is now handled once, by
`NO_MODEL` and `isRecordedModel()` in `web/js/00-lib.js`, with a contract test
asserting the literal is spelled out in that module and no other.

The same modelling choice used to appear a second time, as `"?"` for an unknown
model, hardcoded across four Python scanners. **Resolved by deletion, not by
naming it.** A probe of the whole snapshot found zero requests filed under `"?"`
across 51 projects and 14,119 requests — it had never once fired. It was not a
domain concept but an unexamined guess about the log format, and giving it a
constant would have dignified it. All four sites now refuse a missing model
(INV-27). `billing_or_defer` turns the refusal into a Diagnostics entry naming
the file, so a format change announces itself instead of hiding inside a bucket
nobody can interpret.

### Vocabulary split down the language boundary

Python and the dashboard code both say `client`. The user interface says
`harness`. Neither is wrong; having both is.

**Decided: keep the split, deliberately.** The rename was considered and
declined. `client` is a settled internal spelling touching `CLIENT_KEYS`,
`CLIENT_ALIAS`, the stored per-project keys and every docstring around them; the
churn buys a word, not a behaviour, and a rename that wide is exactly the kind of
edit that hides a real change inside noise. The equivalence is therefore recorded
here and in the ubiquitous-language table rather than enforced in code:
**`client` in code == "Harness" in the interface, always, with no third meaning.**

---

## Adding a dimension

The rules above imply the procedure, and `by_dm` is the worked example.

1. **Check the raw log first.** Ask whether the source already records the two
   values on the same event. `by_dm` was thought impossible for months because
   nobody looked; the pairing was there the whole time and was being thrown away.
2. **Decide whether it carries measures or facts.** If a unit can span another,
   do not divide it. `by_dm` carries no sessions, and neither does `by_sdm`:
   a session spans days and models, so its cells carry magnitudes and the
   distinct count is left to the query.
3. **Write the invariant before the code**, as a test that fails.
4. Add it to `_metrics`, `_merge`, and every attribution site, then extend the
   cross-dimension assertion so the new dimension must reconcile with the others.
5. Bump the cache format — a stale cache will silently omit the new dimension.
6. Record it here.
