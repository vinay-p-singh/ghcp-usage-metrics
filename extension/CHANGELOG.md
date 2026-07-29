# Changelog

All notable changes to the **GHCP Usage Metrics** extension are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.9] — 2026-07-27

### Added
- **New "Auto" theme mode, now the default.** The dashboard adopts the editor's
  own palette (`--vscode-*`) instead of imposing one of its own, so a panel
  docked in a Light+ window no longer looks like a foreign dark island. It
  tracks live theme switches, and every token keeps a literal fallback so the
  same file still renders correctly when opened straight from disk in a
  browser — there it mirrors the OS light/dark preference instead. Existing
  explicit choices (Light / Dim / Dark / Contrast) are untouched.

### Changed
- **No more first-paint flash.** Size tier and theme are resolved by a small
  inline script at the top of `<body>`, so the opening frame is already
  correct. Previously a narrow panel briefly rendered the desktop layout, and a
  dark editor briefly showed light surfaces.
- **Resizing across a tier boundary now redraws only the two SVG charts** (the
  daily bar chart and the activity calendar) rather than re-aggregating and
  re-rendering the whole dataset.

## [0.3.8] — 2026-07-27

### Changed
- **Everything scales now, not just the pills and sidebar.** The tab strip,
  toolbar buttons, panels, tables, legends, donut charts, activity calendar and
  stat cards all read a shared set of size tokens that follow the view.
- **Replaced `vw`-based `clamp()` and the single media query with measured
  tiers.** A `ResizeObserver` measures the real viewport width and sets
  `body[data-size="xs|sm|md|lg|xl"]`; every density token hangs off that. The
  old approach scaled off `vw`, so the same dashboard looked different in a
  docked webview than in a full-screen browser tab at the same pixel width, and
  drifted under `window.zoomLevel`. Charts with baked-in SVG geometry are
  redrawn when the tier changes.
- **Honour the editor's UI font.** The dashboard now uses
  `var(--vscode-font-family, …)`, falling back to the system stack when the
  HTML is opened outside VS Code.

## [0.3.7] — 2026-07-27

### Fixed
- **Corrected the "only request counts" guidance.** Token/AIU data is *not*
  gated by a Trace log level (Info works fine). It comes from fields Copilot Chat
  writes into its own logs, which get trimmed/rotated — so a machine may retain
  only request counts. The onboarding banner and README no longer mention log
  level.

### Added
- **`GHCP Usage: Diagnostics`** command (also reachable from the banner): reports
  the scanned VS Code roots/variants and how many logs actually carry token/credit
  fields, so it's clear why data may be missing on a given machine.
- **Scans all VS Code variants** now (stable + Insiders / VSCodium / Exploration),
  so token data isn't missed when Copilot ran under a different install.

### Removed
- The incorrect *Enable Copilot Logging* command.

## [0.3.6] — 2026-07-27

### Changed
- **Faster, non-blocking open.** The panel now paints instantly: it shows the
  previous report right away (stale-while-revalidate) and rescans in the
  background, or shows a loading screen on the very first run instead of a blank
  window.
- **Faster cold scan.** Debug-log billing files are now parsed in parallel
  (process pool) before the sequential pass, cutting first-ever scan time
  (~54s → ~34s locally). Output is unchanged — only the cache is pre-filled.

## [0.3.5] — 2026-07-27

### Changed
- Summary pills now scale fluidly with the view (track size, padding and value
  font shrink together) so they stay compact in the narrow webview.
- The filters sidebar shrinks fluidly (`clamp(236px, 26vw, 320px)`) before it
  stacks; the stack/collapse breakpoint moved to 780px.

## [0.3.4] — 2026-07-27

### Added
- Collapsible filters sidebar with a **Filters** toolbar toggle; the layout now
  stacks and the sidebar auto-collapses in the narrow VS Code webview.
- Python preflight check: a clear "Python not found" prompt with an **Open
  Settings** action instead of a raw stderr dump.
- *GHCP Usage: Enable Copilot Logging* command and an in-dashboard onboarding
  banner shown when only request counts are available (no token/AIU data).

### Changed
- README documents the Python 3.8+ (stdlib-only) and Copilot Chat Trace-logging
  requirements.

## [0.3.3] — 2026-07-27

### Changed
- Version bump to produce a fresh `.vsix` for smoke-test distribution (no functional changes).

## [0.3.2] — 2026-07-25

### Changed
- Internal refactor (no behavior change; verified identical dashboard output): the Python extractor was split into a `ghcp/` package of pure helpers (`constants`, `naming`, `normalize`, `jsonl`, `model`) with the I/O scanners kept in `usage.py`; duplicated accumulation collapsed into an `_apply_billing` helper; magic strings replaced with named constants.

### Added
- `pytest` test suite (57 tests: pure-helper units, a synthetic golden-master end-to-end, and live-output invariants) plus a CI workflow.
- `.vscode/` tasks & launch configs (Launch dashboard, Run tests, Package/Install extension) and a `check-version` guard that fails packaging if `package.json` and this changelog disagree.
- `bundle.js` now also copies the `ghcp/` package into the packaged extension.

## [0.3.1] — 2026-07-25

### Changed
- Agents tab: the global "Priciest per request" signal card is now **"Priciest base agent / req"** (computed over base/harness agents only), so it no longer duplicates the **"Priciest subagent / req"** card. The two cards now cover disjoint pools (base vs. subagents).

### Added (Marketplace prep)
- Extension `icon` (`media/icon.png`, generated by `scripts/make_icon.py`).
- `repository`, `bugs`, and `homepage` metadata in `package.json`.
- This CHANGELOG.

### Pre-publish checklist (before `vsce publish`)
- [ ] Set `publisher` in `package.json` to your **registered** VS Marketplace publisher ID (currently `local`).
- [ ] Replace `OWNER` in the `repository`/`bugs`/`homepage` URLs with the real GitHub owner/repo.
- [ ] Run `npm run package` and verify the `.vsix`, then `vsce publish` (or upload via the Marketplace portal).

## [0.3.0] — 2026-07-25

### Added
- Agents tab (cost ranking, base vs. subagent grouping, per-agent × model expander).
- Skills tab (SKILL.md invocation counts + attributed AIU).
- Strengths tab (most-used model/agent, output tokens, edit/read tool-calls, turns/session).
- Forecast tab (EoM + 3/4/6-month horizons with optional budget cascade).

## [0.2.0] — 2026-07-25

### Added
- Initial VS Code extension: runs the bundled Python extractor (`usage.py`) and hosts the dashboard in a webview.
- Commands: **GHCP Usage: Open Dashboard**, **GHCP Usage: Refresh Data**.
- Settings: `ghcpUsage.pythonPath`, `ghcpUsage.repoPath`.
- Reproducible `.vsix` packaging that bundles the Python extractor (`py/`).
