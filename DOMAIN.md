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
| **Measure** | A number that sums: requests, in, out, aiu | Never estimated. Sessions are distinct entities, not an additive model measure. |
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
        ├── by_day     date          → sessions, requests, in, out, aiu
        ├── by_model   model         → requests, in, out, aiu
        ├── by_agent   agent         → requests, in, out, aiu
        ├── by_am      agent×model   → requests, in, out, aiu
        ├── by_dm      date×model    → requests, in, out, aiu
      ├── by_sdm     session×date×model → fact present (1)
        ├── by_skill   skill         → reads, sessions, requests, in, out, aiu
        ├── by_tool    tool          → count
        └── by_lang    language      → count
```

Every dimension is the same set of requests, sliced differently. That is why the
totals must agree, and why disagreement means something is double-counted rather
than merely inconsistent.

Session totals remain on `by_day` and `by_skill`. Model membership is not stored
as a divisible total: `by_sdm` records set-like activity facts. A session that
uses two models has two facts but still counts once after filtering.

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
| INV-3 | Session totals exist on `by_day` and `by_skill`; session/model membership is represented only by idempotent `by_sdm` facts | `test_contract`, `test_extract_synthetic` |
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
   do not divide it. `by_dm` carries no sessions; `by_sdm` records membership
   facts and leaves distinct counting to the query.
3. **Write the invariant before the code**, as a test that fails.
4. Add it to `_metrics`, `_merge`, and every attribution site, then extend the
   cross-dimension assertion so the new dimension must reconcile with the others.
5. Bump the cache format — a stale cache will silently omit the new dimension.
6. Record it here.
