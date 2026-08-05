# Changelog

Releases are recorded here from 1.0.0 onward. The development that led up to it
is summarised at the end, as phases rather than versions — those builds never
shipped to anyone, and listing them as releases would overstate what happened.

## [1.2.1] — 2026-08-05

A scan that hits one unreadable file no longer takes the whole report with it,
and a failure that does happen is reported as a sentence rather than a wall of
Python.

Fixed

- One bad session, chat file, workspace or log source used to abort the entire
  scan, so a single oddity on a machine left the reader with no dashboard at
  all. Each of those is now contained: the failure is recorded in the
  Diagnostics tab, that one unit is skipped, and everything else still reports.

Changed

- Failure notifications carry one line — what failed and why — instead of the
  raw traceback. **Show details** opens the full record in the output panel and
  **Open report file** opens it as a file to attach to a bug report.
- A run that dies writes `out/error.log`: the traceback, the platform and
  Python version it ran on, what the scan had already read, and every contained
  failure. A successful run deletes it, so its presence always means the last
  run failed.

## [1.2.0] — 2026-08-05

Puts this tool's total beside GitHub's own, and names what the difference is
made of instead of leaving a reader to assume one side is wrong.

Added

- **Reconciliation card** in Diagnostics. Enter your billing cycle dates and the
  credits figure from your GitHub Copilot settings page, and the card shows both
  totals side by side with the share accounted for. The gap is explained rather
  than closed: a second machine, Copilot on github.com, the coding agent, mobile,
  and spend since the last scan are all invisible to a tool that reads local
  logs. Nothing is scaled up to meet GitHub's number.
- The card compares against every recorded credit in the cycle, deliberately
  ignoring the sidebar filters — a filtered subset measured against an
  account-wide total would overstate the gap.
- Our total exceeding GitHub's is reported as a bug in this tool, not a gap,
  because we can only ever see a subset of what GitHub bills.
- A staleness warning when today falls outside the cycle you entered, so a
  closed cycle is not read as a current one.

Fixed

- Timestamps carrying a UTC offset were sliced to their first ten characters,
  which filed a request on the wrong day whenever the local date and the UTC
  date differed. They are now converted. A timestamp with no offset is still
  read as written — guessing a zone would be estimation.

## [1.1.0] — 2026-08-03

Answers a question the previous release could not: what did one piece of work
cost, and how much of that was the conversation being re-read.

Added

- **Sessions view.** One row per conversation, folded across the days and models
  it spanned, ranked by credits. Every column sorts. Sessions the store still
  holds carry the label it recorded; older ones show their id rather than an
  invented name.
- **Cache breakdown.** Input tokens split into what was served from the model's
  prompt cache and what was fresh. On the machine this was built with, 93% of
  all input was cache — the figure was in the logs all along and was being
  discarded.
- **Credit coverage floor.** Credit reporting did not arrive in every harness at
  once, so the view now opens at the start of the month in which the last one
  began, rather than averaging complete months together with months that
  recorded requests and no credits. The date is measured from your own logs, not
  hardcoded, and the earlier data is still there — a banner explains it and one
  click widens the range.
- **Thin-day markers.** Days inside the range that recorded no credits, or where
  a material share of requests carry no token payload, are marked and explain
  themselves on hover instead of being quietly averaged in.
- Per-session and per-day cache figures in the extract, and session names where
  the session stores still hold them.

Fixed

- Retained chat sessions that recorded their token counts under `result.metadata`
  rather than on the request itself were being read as zero. Found by comparing
  against an official usage report; no internal check could see it.
- `by_sdm` merged inside another dimension's loop and would have been dropped had
  that dimension been empty.
- The skill's `query.py` reported lifetime model totals under `--since` /
  `--until`. Model breakdowns are now date-scoped; agent breakdowns still are not,
  because no date-by-agent dimension exists, and they now say so.

Notes

- Nothing about scanning changed. `ghcpUsage.quickScanDays` (default 10) still
  only affects the first paint; a full scan always follows and no log is
  permanently skipped. The coverage floor changes which dates the view opens on,
  not which are read.
- "Cached" does not mean the same thing in every harness: VS Code publishes one
  combined figure for cache reads, the CLI publishes reads and writes separately
  and both are counted. See DOMAIN.md.

## [1.0.0] — 2026-07-30

First release.

Reads the GitHub Copilot logs already on your machine — VS Code, Copilot CLI and
Claude Code — and reports what they recorded: AI credits, requests, tokens and
active days, split by project, model, agent, skill and day.

### The dashboard

- Eight views: overview, activity calendar, breakdown, agents, skills,
  strengths, forecast and diagnostics.
- The calendar is clickable and draggable — pick a day or a range and every
  number follows.
- Costs appear in your own currency once you set a rate. Nothing is shown until
  you do, because no credit price is readable locally.

### Scanning

- A quick pass over recent logs paints the dashboard, then a full scan replaces
  it in place without costing you your tab, filters or selection.
- Diagnostics reports what the last scan read, skipped and failed on, including
  which requests carry no token payload and why.

### Filtering

- Date range, harness and project filters. Every project is counted by default;
  untick one to exclude it.
- Projects that never recorded a token or a credit start unticked and sit behind
  a link in the sidebar. They are hidden, never discarded.
- Model checkboxes work the same way as projects: unticking a model removes it
  from every figure — totals, charts, calendar and breakdowns — and the model
  list follows the date range. Session counts and requests with no recorded
  model are the two things a model filter cannot reach.
- A hard-filter config for projects, prefixes, harnesses, models and agents,
  saved in the browser.

### Beyond the dashboard

- A VS Code extension that runs the extractor and shows the report in a webview.
- An agent skill with a query CLI, so a coding agent can answer questions from
  your own numbers without loading the whole report into a conversation.

Every figure comes from what GitHub actually wrote down. Nothing is estimated,
extrapolated or back-filled — gaps are reported as gaps.

---

## Before 1.0

How the tool got here. Kept because the reversals are the interesting part, and
because the reasoning behind each one still constrains what gets built next.
[ARCHITECTURE.md](../ARCHITECTURE.md) carries the detail.

### Reading the logs at all

The first working version read VS Code chat logs and the Copilot CLI database
and produced a single HTML page. One decision from that week still holds: Python
decides every number, and the dashboard, the extension and the chat skill are
all just ways of looking at the same output. It has meant one place to check
when a figure looks wrong.

### Estimating credits, then deleting all of it

Credits are only recorded from mid-May 2026. Earlier sessions had tokens but no
credits, so the tool inferred them from a per-model rate. The totals looked
fuller and the charts looked complete.

They were also unverifiable, and nothing on screen distinguished a recorded
credit from a computed one. Removing every estimate cost roughly 25,000 credits
off the headline and turned the remainder into something worth trusting. That
became the rule the project is now built around: show what was recorded, report
gaps as gaps, and never let a plausible number stand in for a missing one.

### Finding credits that were genuinely there

Roughly 12,400 credits were being missed entirely. Subagents launched through
`runSubagent` write their own log file beside the parent's, and nothing was
reading them. Adding them was the opposite of the estimation problem — real
recorded values that had simply gone unread — and the cross-dimension invariant
proved they were not being counted twice.

Saved chat sessions were added as a second source around the same time. VS Code
rotates its debug logs but keeps session files far longer, so history reached
back from about three months to seven. Sessions already covered by the debug
logs are skipped, which is what stops the two sources overlapping.

### Making it answer questions

One page became eight views as the questions got sharper: which day, which
model, which agent, which skill, what it might cost next month. Then a VS Code
extension so the report could be regenerated without a terminal, and an agent
skill with a query CLI so a coding agent could answer from the numbers directly
— the full report is far too large to read into a conversation.

### Making it safe to change

By this point one file held a thousand lines of extractor and another held two
thousand lines of dashboard. Both were split, into the `ghcp` package and into
`web/`, but only after golden-master tests were in place to prove the output had
not moved. That order mattered: the tests came first, so the refactor was
provable rather than hopeful.

Test coverage then grew to meet the code — unit tests either side of the
language boundary, a synthetic log tree for end-to-end runs, jsdom for the
interactions, and a browser pass for what only a real cascade can catch.

### Saying what the numbers do not cover

Several projects showed requests but no credits, which reads as a bug and is
not. A diagnostics view now reports what each scan read, skipped and failed on,
and names the projects whose requests carry no token payload.

The filters were rethought in the same spirit: every project counts unless you
exclude it, projects that never recorded a token are demoted rather than
deleted, and the model filter states plainly which panels it can and cannot
reach.
