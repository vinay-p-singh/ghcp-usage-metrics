---
name: ghcp-usage-metrics
description: Answer questions about the user's own GitHub Copilot usage — AI Units (AIU) spend, requests, tokens, cost per project, per agent, per model, per skill, per day, plus the HTML dashboard. Reads local Copilot logs (VS Code, Copilot CLI, Claude Code) via the ghcp-usage-metrics extractor. USE FOR: "how much Copilot have I used", "what's my AIU spend", "which project costs the most", "most expensive agent", "which subagent burns the most credits", "what models am I using", "which skills do I actually use", "usage this week/month", "open my usage dashboard", "refresh my usage data". DO NOT USE FOR: GitHub org/enterprise billing APIs (unreachable for this account), other people's usage, or estimating usage that was never recorded.
---

# GHCP Usage Metrics

Local, honest reporting on the user's own Copilot usage. A Python extractor reads
the logs Copilot already writes on this machine and produces two artifacts:

- `out/projects.json` — the data (~130 KB nested JSON, **do not read wholesale**)
- `out/dashboard.html` — a self-contained interactive dashboard

Answer questions by running `query.py` against the JSON. Read the raw JSON only
if a question genuinely has no matching subcommand.

## Where to run it

This folder is self-contained: it carries the extractor (`usage.py`, `ghcp/`,
`build_dashboard.py`) alongside the instructions and the query CLI. Run every
command below from this folder, and the artifacts land in `out/` beside them.
Python 3 with no third-party packages is the only requirement.

## Refresh when stale

`out/projects.json` is a snapshot. Re-run the extractor when the user asks for
fresh numbers, or when the file is missing or more than a day old:

```pwsh
python usage.py
```

That rewrites both `out/projects.json` and `out/dashboard.html` and prints a
one-line total. It takes a few seconds and needs no arguments. Otherwise reuse
the existing snapshot rather than rescanning on every question.

## When the machine has no Copilot Chat request logs

VS Code holds the same sessions in two places, and neither is complete. Request
logs (`debug-logs/*/main.jsonl`) carry every model call but rotate away; saved
sessions (`chatSessions/`) survive far longer but keep only the most recent
turns of each. `python usage.py` prefers the request log and lets saved sessions
cover what it no longer holds — and if the machine has no request logs at all,
it falls back to saved sessions on its own and says so in a banner.

To force one store:

```pwsh
python usage.py --source sessions   # saved sessions only
python usage.py --source debug      # request logs only
```

`--source sessions` is what a machine without request logs is really reporting,
so use it to reproduce someone else's view. Everything downstream is unchanged:
`query.py` still gives the full project-wise breakdown.

**Say this whenever a sessions-only report is being discussed**, because the
numbers are a floor and nothing in them shows it:

- Saved sessions only carry an AI-credit figure from the date VS Code began
  writing one. `out/diagnostics.json` → `source.chat_credit_first` holds that
  date, measured from the logs. Earlier days have requests and tokens, no credits.
- The calendar shows one saved-session coverage note instead of per-day warning
  badges in this mode. Missing coverage is systemic here; Diagnostics retains
  the detailed request and token-payload counts.
- Only the most recent turns of each session survive, so request counts and
  totals are lower than the account was actually billed.
- On the machine this was built on, saved-sessions-only reported roughly a third
  of the credits the default scan found. Treat the gap as coverage, not as a
  discrepancy to explain away.

## Query

```pwsh
python query.py <command> [options]
```

| Command | Answers |
| --- | --- |
| `summary` | Totals plus the split across the three harnesses |
| `projects [--top N]` | Projects ranked by AIU (default 15) |
| `agents` | Agents and subagents ranked by AIU, with AIU per request |
| `models` | Models ranked by AIU |
| `skills` | Skills ranked by invocation count, with attributed AIU |
| `daily` | One row per active day |
| `project <name>` | One project in detail; `<name>` is a substring match |

Options: `--since YYYY-MM-DD`, `--until YYYY-MM-DD` (applies to `summary`,
`projects`, `daily`, `project`), `--top N`, `--data <path to projects.json>`.
Set `GHCP_USAGE_REPO` to point at a different checkout when one is available.

Prefer one targeted command over dumping several. For "what did I spend last
week", use `summary --since <date>` and follow up with `projects --since <date>`
only if the user wants the breakdown.

## Open the dashboard

For anything visual — the calendar heatmap, charts, the forecast tab — point the
user at `out/dashboard.html` rather than describing numbers:

```pwsh
Start-Process out/dashboard.html
```

There is also a VS Code extension in `extension/` that opens the same dashboard
in a webview with a live **Refresh data** button.

## Honesty rules — carry these into every answer

The whole point of this tool is that it never guesses. Do not soften or
extrapolate past what it reports.

- **Nothing is estimated.** AIU comes from GitHub's own `copilotUsageNanoAiu`
  telemetry. Sessions predating that telemetry count their real requests and
  tokens and add **zero** AIU — a low early-month figure is missing telemetry,
  not low usage.
- **Claude Code reports no AIU.** Its requests and tokens are real; its AIU is
  genuinely 0. Never present that as free or as cheap.
- **Agent personas mostly fold together.** Only subagents launched via the
  `runSubagent` tool get their own attribution. Agent-picker modes are recorded
  as "GitHub Copilot Chat".
- **Agent and skill data is retention-limited.** VS Code keeps roughly the most
  recent 70 sessions in its session store, so older runs are purged and
  unrecoverable. Skill invocation counts are exact for the sessions that
  survived, not for all time.
- **Agent and skill breakdowns are lifetime**, not date-filtered — the per-day
  buckets carry no agent or skill dimension. Models are dated and do follow
  `--since` / `--until`; `query.py` prints a reminder when it matters.
- **Skill AIU overlaps.** A session that used three skills counts its tokens
  toward all three, so skill AIU does not sum to the total.
- **No cloud fallback.** Enterprise-managed accounts cannot reach GitHub's org
  metrics or personal billing APIs. Local logs are the only source; if something
  is not in them, say so instead of filling the gap.
- **Harness coverage varies by platform.** VS Code data is read from the
  platform's own user directory, Copilot CLI from `~/.copilot`, and Claude Code
  from `~/.claude`. A harness the user never ran simply contributes nothing.
- **`query.py` sees more projects than the dashboard shows.** The dashboard
  hides projects that never recorded a token or a credit, so its project count
  is lower by design. The JSON keeps them all. If a count here disagrees with
  the screen, that is why — say so rather than treating either as wrong.
