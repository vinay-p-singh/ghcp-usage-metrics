"""Dashboard template for ghcp-usage.

Pure presentation: HTML + CSS + JS. `usage.py` injects the project data by
replacing ``__DATA__`` with a JSON array of project objects
``{"name", "vscode": {...metrics}, "cli": {...metrics}}`` (each metrics bucket
has sessions/requests/in/out/aiu/days), and ``__GENERATED__`` with the build
timestamp. Keep all UI/markup changes in THIS file.
"""
from __future__ import annotations

DASHBOARD_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GitHub Copilot — Token &amp; AI-Credit Usage</title>
<style>
  :root {
    color-scheme: light;
    /* --- mode surfaces (light = default) --- */
    --bg: #fbfbfc; --fg: #1f2328; --fg-muted: #59636e; --fg-subtle: #6a737d;
    --border: #e3e6ea; --border-subtle: #eef0f2;
    --surface: #ffffff; --surface-2: #f6f8fa; --surface-3: #eef1f4;
    --shadow: 0 1px 2px rgba(27, 31, 36, .05);
    --scroll: #d3d8de; --scroll-hover: #bcc3cb;
    --cal-0: #eef1f4;
    /* --- accent (blue = default) --- */
    --accent: #3b82f6; --accent-hover: #2563eb; --accent-fg: #ffffff;
    --radius: 10px; --radius-sm: 7px;
    --fs-label: .64rem; --fs-sm: .78rem; --fs-base: .85rem; --fs-lg: 1.3rem; --fs-xl: 1.15rem;
    --sp-1: 4px; --sp-2: 8px; --sp-3: 12px; --sp-4: 16px; --sp-5: 24px;
    /* --- size tokens (defaults = the "md" tier; JS sets body[data-size]) ---
       Every density-sensitive value in the sheet reads one of these, so a tier
       switch is a single attribute change rather than a pile of media queries. */
    --pad-y: 1.25rem; --pad-x: 2rem; --gap: 1.25rem; --sbw: 268px;
    --pill-min: 132px; --pill-pad-y: 9px; --pill-pad-x: 12px; --pill-v: 1.18rem;
    --tab-fs: .78rem; --tab-pad-y: 6px; --tab-pad-x: 13px;
    --btn-fs: 12px; --btn-pad-y: 6px; --btn-pad-x: 12px;
    --panel-pad-y: 14px; --panel-pad-x: 16px;
    --tbl-fs: 12.5px; --tbl-pad-y: 5px; --tbl-pad-x: 8px;
    --legend-min: 150px; --name-max: 240px; --pie: 150px;
    --cal-cell: 21; --chart-h: 84;
    --card-v: 17px; --card-v-sm: 14px;
  }
  /* ===== modes (surfaces only) ===== */
  /* "auto" adopts the host editor's palette instead of imposing ours, so a
     panel docked in a Light+ window stops looking like a foreign dark island.
     Every token keeps a literal fallback: the exact same file is also opened
     straight from disk in a browser, where no --vscode-* variable exists. */
  body[data-theme="auto"] {
    --bg: var(--vscode-editor-background, #fbfbfc);
    --fg: var(--vscode-editor-foreground, var(--vscode-foreground, #1f2328));
    --fg-muted: var(--vscode-descriptionForeground, #59636e);
    --fg-subtle: var(--vscode-disabledForeground, #6a737d);
    --border: var(--vscode-widget-border, var(--vscode-panel-border, #e3e6ea));
    --border-subtle: var(--vscode-panel-border, #eef0f2);
    --surface: var(--vscode-editorWidget-background, var(--vscode-editor-background, #ffffff));
    --surface-2: var(--vscode-sideBar-background, var(--vscode-editor-background, #f6f8fa));
    --surface-3: var(--vscode-input-background, #eef1f4);
    --shadow: 0 1px 2px rgba(0, 0, 0, .18);
    --scroll: var(--vscode-scrollbarSlider-background, #d3d8de);
    --scroll-hover: var(--vscode-scrollbarSlider-hoverBackground, #bcc3cb);
    --cal-0: var(--vscode-input-background, #eef1f4);
  }
  /* the host palette carries no light/dark flag of its own, so JS stamps one
     (theme-kind marker if present, luminance probe otherwise) purely to get
     `color-scheme` right for native form controls and scrollbars */
  body[data-theme="auto"][data-host-kind="dark"] { color-scheme: dark; }
  body[data-theme="auto"][data-host-kind="light"] { color-scheme: light; }
  body[data-theme="dim"] {
    color-scheme: dark;
    --bg: #1a1b26; --fg: #c0caf5; --fg-muted: #9aa5ce; --fg-subtle: #7982a9;
    --border: #2a2e42; --border-subtle: #222436;
    --surface: #1f2335; --surface-2: #222639; --surface-3: #2a2e42;
    --shadow: 0 1px 2px rgba(0, 0, 0, .4);
    --scroll: #2a2e42; --scroll-hover: #3b4261;
    --cal-0: #222436;
  }
  body[data-theme="dark"] {
    color-scheme: dark;
    --bg: #0d1117; --fg: #c9d1d9; --fg-muted: #8b949e; --fg-subtle: #7d8590;
    --border: #30363d; --border-subtle: #21262d;
    --surface: #161b22; --surface-2: #161b22; --surface-3: #1c2128;
    --shadow: 0 1px 2px rgba(1, 4, 9, .4);
    --scroll: #30363d; --scroll-hover: #3f4650;
    --cal-0: #161b22;
  }
  body[data-theme="contrast"] {
    color-scheme: dark;
    --bg: #000000; --fg: #ffffff; --fg-muted: #d0d7de; --fg-subtle: #aeb6bf;
    --border: #8b949e; --border-subtle: #57606a;
    --surface: #0a0c10; --surface-2: #11151b; --surface-3: #1a1f26;
    --shadow: 0 0 0 1px rgba(255, 255, 255, .05);
    --scroll: #57606a; --scroll-hover: #8b949e;
    --cal-0: #11151b;
  }
  /* ===== accents (hue only) ===== */
  body[data-accent="violet"] { --accent: #8b5cf6; --accent-hover: #7c3aed; --accent-fg: #ffffff; }
  body[data-accent="teal"]   { --accent: #14b8a6; --accent-hover: #0d9488; --accent-fg: #ffffff; }
  body[data-accent="amber"]  { --accent: #f59e0b; --accent-hover: #d97706; --accent-fg: #241a02; }
  body[data-accent="rose"]   { --accent: #f43f5e; --accent-hover: #e11d48; --accent-fg: #ffffff; }

  /* ===== responsive tiers =====
     Driven by a JS-measured viewport width, not by `vw` and not by media
     queries. The same file is consumed two ways -- inside a narrow docked
     VS Code webview and as a standalone page in a full-screen browser -- and
     only a measured pixel width behaves identically in both. It is also
     stable under VS Code's `window.zoomLevel`, which changes how many CSS
     pixels the panel reports without changing the density we want. */
  body[data-size="xs"] {
    --pad-y: .7rem; --pad-x: .8rem; --gap: .75rem; --sbw: 100%;
    --pill-min: 96px; --pill-pad-y: 6px; --pill-pad-x: 8px; --pill-v: .98rem;
    --tab-fs: .68rem; --tab-pad-y: 5px; --tab-pad-x: 9px;
    --btn-fs: 11px; --btn-pad-y: 5px; --btn-pad-x: 8px;
    --panel-pad-y: 9px; --panel-pad-x: 10px;
    --tbl-fs: 11px; --tbl-pad-y: 4px; --tbl-pad-x: 5px;
    --legend-min: 112px; --name-max: 120px; --pie: 112px;
    --cal-cell: 15; --chart-h: 60;
    --card-v: 13.5px; --card-v-sm: 12px;
    --fs-label: .58rem; --fs-sm: .7rem; --fs-lg: 1rem; --fs-xl: .98rem;
    --radius: 8px; --radius-sm: 6px;
  }
  body[data-size="sm"] {
    --pad-y: .9rem; --pad-x: 1.1rem; --gap: .95rem; --sbw: 100%;
    --pill-min: 112px; --pill-pad-y: 7px; --pill-pad-x: 10px; --pill-v: 1.06rem;
    --tab-fs: .72rem; --tab-pad-y: 5px; --tab-pad-x: 11px;
    --btn-fs: 11.5px; --btn-pad-y: 5px; --btn-pad-x: 10px;
    --panel-pad-y: 11px; --panel-pad-x: 13px;
    --tbl-fs: 12px; --tbl-pad-y: 4px; --tbl-pad-x: 6px;
    --legend-min: 128px; --name-max: 170px; --pie: 128px;
    --cal-cell: 18; --chart-h: 72;
    --card-v: 15px; --card-v-sm: 13px;
    --fs-lg: 1.12rem; --fs-xl: 1.05rem;
  }
  body[data-size="lg"] {
    --pad-y: 1.4rem; --pad-x: 2.25rem; --gap: 1.5rem; --sbw: 300px;
    --pill-min: 150px; --pill-pad-y: 11px; --pill-pad-x: 14px; --pill-v: 1.3rem;
    --tab-fs: .82rem; --tab-pad-y: 7px; --tab-pad-x: 16px;
    --btn-fs: 12.5px; --btn-pad-y: 7px; --btn-pad-x: 14px;
    --panel-pad-y: 16px; --panel-pad-x: 18px;
    --tbl-fs: 13px; --tbl-pad-y: 6px; --tbl-pad-x: 9px;
    --legend-min: 168px; --name-max: 300px; --pie: 164px;
    --cal-cell: 24; --chart-h: 96;
    --card-v: 18px; --card-v-sm: 15px;
    --fs-lg: 1.4rem; --fs-xl: 1.22rem;
  }
  body[data-size="xl"] {
    --pad-y: 1.6rem; --pad-x: 2.75rem; --gap: 1.75rem; --sbw: 330px;
    --pill-min: 168px; --pill-pad-y: 13px; --pill-pad-x: 17px; --pill-v: 1.45rem;
    --tab-fs: .86rem; --tab-pad-y: 8px; --tab-pad-x: 19px;
    --btn-fs: 13px; --btn-pad-y: 8px; --btn-pad-x: 16px;
    --panel-pad-y: 19px; --panel-pad-x: 22px;
    --tbl-fs: 13.5px; --tbl-pad-y: 7px; --tbl-pad-x: 11px;
    --legend-min: 190px; --name-max: 380px; --pie: 180px;
    --cal-cell: 27; --chart-h: 110;
    --card-v: 20px; --card-v-sm: 16px;
    --fs-lg: 1.55rem; --fs-xl: 1.3rem;
  }
  * { box-sizing: border-box; }
  /* derived tokens resolve against the FINAL mode+accent on <body> */
  /* honour the editor's configured UI font when hosted in a VS Code webview,
     fall back to the system stack when the file is opened directly */
  body { font: 14px/1.5 var(--vscode-font-family, system-ui, "Segoe UI", sans-serif);
         margin: 0; padding: var(--pad-y) var(--pad-x);
         background: var(--bg); color: var(--fg); height: 100vh; display: flex; flex-direction: column; overflow: hidden;
         --accent-soft: color-mix(in srgb, var(--accent) 10%, var(--surface));
         --accent-soft-border: color-mix(in srgb, var(--accent) 24%, var(--surface));
         --cal-1: color-mix(in srgb, var(--accent) 20%, var(--cal-0));
         --cal-2: color-mix(in srgb, var(--accent) 44%, var(--cal-0));
         --cal-3: color-mix(in srgb, var(--accent) 68%, var(--cal-0));
         --cal-4: var(--accent); }
  h1 { font-size: var(--fs-xl); margin: 0 0 2px; letter-spacing: -.01em; }
  .sub { color: var(--fg-muted); margin: 0; font-size: var(--fs-sm); white-space: nowrap;
         overflow: hidden; text-overflow: ellipsis; }
  .sub code { background: var(--surface-3); padding: 1px 5px; border-radius: 4px; }

  /* unified thin scrollbars */
  * { scrollbar-width: thin; scrollbar-color: var(--scroll) transparent; }
  *::-webkit-scrollbar { width: 10px; height: 10px; }
  *::-webkit-scrollbar-track { background: transparent; }
  *::-webkit-scrollbar-thumb { background: var(--scroll); border-radius: 8px;
                               border: 2px solid transparent; background-clip: padding-box; }
  *::-webkit-scrollbar-thumb:hover { background: var(--scroll-hover); }

  #dashView { flex: 1; min-height: 0; display: flex; flex-direction: column; }
  .layout { display: flex; gap: var(--gap); align-items: stretch; flex: 1; min-height: 0; }
  /* sidebar shrinks with the tier, then stacks + collapses when too narrow */
  .sidebar { flex: 0 0 var(--sbw); width: var(--sbw); overflow-y: auto; padding-right: 8px; }
  .main { flex: 1; min-width: 0; overflow-y: auto; padding-right: 8px; }
  body.sidebar-collapsed .sidebar { display: none; }
  body.sidebar-collapsed .main { padding-right: 0; }
  #filtersBtn { display: none; }
  body[data-size="xs"] #filtersBtn, body[data-size="sm"] #filtersBtn { display: inline-flex; }
  body[data-size="xs"] .layout, body[data-size="sm"] .layout { flex-direction: column; }
  body[data-size="xs"] .sidebar, body[data-size="sm"] .sidebar {
    flex: 0 0 auto; width: 100%; max-height: 48vh; padding-right: 0; }
  body[data-size="xs"] .main, body[data-size="sm"] .main { padding-right: 0; }
  body[data-size="xs"] .topbar { flex-wrap: wrap; }

  /* sidebar sections */
  .section { border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden;
             margin-bottom: 1rem; background: var(--surface); }
  .section > header { display: flex; align-items: center; justify-content: space-between;
                      padding: 9px 13px; background: var(--surface-2); border-bottom: 1px solid var(--border-subtle); }
  .section > header h2 { font-size: var(--fs-label); text-transform: uppercase; letter-spacing: .06em;
                         color: var(--fg-muted); margin: 0; font-weight: 600; }
  .section > header .act { font-size: .7rem; color: var(--accent); cursor: pointer; user-select: none; }
  .section > header .act:hover { color: var(--accent-hover); text-decoration: underline; }
  .section > header .acts { display: flex; gap: 10px; }
  .section-body { padding: 11px 13px; }

  .opt { display: flex; align-items: center; gap: 8px; padding: 3px 0; cursor: pointer; user-select: none; }
  .opt input { margin: 0; accent-color: var(--accent); }
  .opt .badge { margin-left: auto; color: var(--fg-subtle); font-variant-numeric: tabular-nums; font-size: 12px; }

  #projSearch { width: 100%; padding: 6px 10px; font-size: 13px; border: 1px solid var(--border);
                border-radius: var(--radius-sm); margin-bottom: 8px; background: var(--surface); color: var(--fg); }
  #projSearch:focus { outline: none; border-color: var(--accent); }
  .proj-hint { margin: 0 0 8px; font-size: 11px; color: var(--fg-subtle); line-height: 1.4; }
  .proj-scroll { max-height: 42vh; overflow: auto; }
  .proj-list { display: flex; flex-direction: column; }
  .prow label { display: flex; align-items: flex-start; gap: 7px; width: 100%; cursor: pointer;
                user-select: none; padding: 4px 5px; border-radius: var(--radius-sm); }
  .prow label:hover { background: var(--surface-2); }
  .prow .projcb { margin-top: 2px; accent-color: var(--accent); flex: 0 0 auto; }
  .prow .pname { overflow-wrap: anywhere; word-break: break-word; line-height: 1.3; font-size: 13px; }
  .prow.hidden { display: none; }
  .proj-empty { color: var(--fg-subtle); font-size: 13px; padding: 4px 0; }

  /* date range */
  .presets { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
  .presets button { font: inherit; font-size: 12px; padding: 3px 11px; border: 1px solid var(--border);
                    background: var(--surface); border-radius: 15px; cursor: pointer; color: var(--fg); }
  .presets button:hover { border-color: var(--accent); color: var(--accent); }
  .presets button.active { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }
  .drow { display: flex; align-items: center; gap: 6px; }
  .drow input[type=date] { flex: 1; min-width: 0; padding: 4px 6px; font: inherit; font-size: 12px;
                           border: 1px solid var(--border); border-radius: var(--radius-sm);
                           background: var(--surface); color: var(--fg); }
  .drow span { color: var(--fg-subtle); }

  /* summary pills — track size + padding + value font all follow the tier */
  .pills { display: grid; grid-template-columns: repeat(auto-fit, minmax(var(--pill-min), 1fr));
           gap: var(--sp-2); margin-bottom: 1rem; flex: 0 0 auto; }
  .pill { border: 1px solid var(--border); border-radius: var(--radius);
          padding: var(--pill-pad-y) var(--pill-pad-x);
          background: var(--surface); box-shadow: var(--shadow); }
  .pill .k { font-size: var(--fs-label); text-transform: uppercase; letter-spacing: .05em; color: var(--fg-muted); }
  .pill .v { font-size: var(--pill-v); font-weight: 650; margin-top: 3px; font-variant-numeric: tabular-nums; letter-spacing: -.01em; }
  .pill .s { font-size: .62rem; color: var(--fg-subtle); margin-top: 2px; }
  .pill.hero { background: var(--accent-soft); border-color: var(--accent-soft-border); border-left: 3px solid var(--accent); }
  .pill.hero .v { color: var(--accent); }

  /* chart + table panels */
  .panel { border: 1px solid var(--border); border-radius: var(--radius);
           padding: var(--panel-pad-y) var(--panel-pad-x);
           margin-top: 14px; background: var(--surface); box-shadow: var(--shadow); }
  .panel h3 { margin: 0 0 12px; font-size: .74rem; text-transform: uppercase; letter-spacing: .05em; color: var(--fg-muted); font-weight: 600; }
  .panel h3 .hint { font-weight: 400; text-transform: none; letter-spacing: 0; color: var(--fg-subtle); }
  .muted { color: var(--fg-subtle); font-size: var(--tbl-fs); padding: 6px 0; }
  .chart svg { display: block; }
  .cal-wrap { overflow-x: auto; }
  .cal-legend { display: flex; align-items: center; gap: 4px; margin-top: 10px; color: var(--fg-muted); font-size: 11px; }
  .cal-legend .cell { width: 11px; height: 11px; border-radius: 2px; display: inline-block; }
  .tabs { display: inline-flex; gap: 2px; background: var(--surface-2); border: 1px solid var(--border);
          border-radius: 999px; padding: 3px; margin: 10px 0 16px; max-width: 100%; overflow-x: auto;
          scrollbar-width: none; }
  .tabs::-webkit-scrollbar { display: none; }
  .tab { font: inherit; font-size: var(--tab-fs); padding: var(--tab-pad-y) var(--tab-pad-x); border: none; background: none; cursor: pointer;
         color: var(--fg-muted); border-radius: 999px; white-space: nowrap; transition: background .12s, color .12s; }
  .tab:hover { color: var(--fg); }
  .tab.active { background: var(--surface); color: var(--accent); font-weight: 600; box-shadow: var(--shadow); }
  /* at the narrowest tier the strip fills the row and scrolls instead of clipping */
  body[data-size="xs"] .tabs { display: flex; width: 100%; }
  .tabpanel { display: none; }
  .tabpanel.active { display: block; }
  .cfgview { flex: 1; min-height: 0; overflow: auto; padding-right: 8px; max-width: 920px; }
  .cfg-json { width: 100%; box-sizing: border-box; min-height: 340px; resize: vertical;
              font: 12px/1.5 ui-monospace, Consolas, "Courier New", monospace;
              border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px;
              background: var(--surface); color: var(--fg); }
  .cfg-json:focus { outline: none; border-color: var(--accent); }
  .cfg-status { font-size: 12px; align-self: center; }
  .cfg-status.ok { color: #1a7f37; }
  .cfg-status.err { color: #cf222e; }
  .cfg-note { color: var(--fg-subtle); font-size: 11px; line-height: 1.55; margin: 12px 0 0; }
  .cfg-note code { background: var(--surface-3); padding: 1px 5px; border-radius: 4px; }
  .pie-row { display: flex; gap: 18px; align-items: center; flex-wrap: wrap; }
  .pie-row .legend { flex: 1; min-width: min(200px, 100%); margin-top: 0; }
  .pie { width: var(--pie); height: var(--pie); flex: 0 0 auto; }
  .hbar { margin: 8px 0; }
  .stack { display: flex; width: 100%; height: 22px; border-radius: 6px; overflow: hidden; background: var(--surface-3); }
  .stack .seg { display: block; height: 100%; }
  .legend { display: grid; grid-template-columns: repeat(auto-fill, minmax(var(--legend-min), 1fr)); gap: 3px 14px; margin-top: 10px; }
  .lg { display: flex; align-items: center; gap: 6px; font-size: var(--tbl-fs); }
  .lg .sw { width: 10px; height: 10px; border-radius: 3px; flex: 0 0 auto; }
  .lg .ln { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .lg .lp { margin-left: auto; color: var(--fg-muted); font-variant-numeric: tabular-nums; }
  .ptable { width: 100%; border-collapse: collapse; }
  .ptable th, .ptable td { padding: var(--tbl-pad-y) var(--tbl-pad-x); border-bottom: 1px solid var(--border-subtle); text-align: left; font-size: var(--tbl-fs); }
  .ptable th { color: var(--fg-subtle); font-size: var(--fs-label); text-transform: uppercase; letter-spacing: .03em; }
  .ptable .num { text-align: right; font-variant-numeric: tabular-nums; }
  .ptable .pn { max-width: var(--name-max); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ptable-scroll { max-height: 50vh; overflow: auto; }
  .ptable-scroll thead th { position: sticky; top: 0; background: var(--surface); z-index: 1; }

  /* models sidebar list */
  .mlist { max-height: 34vh; overflow: auto; }
  .mrow { display: flex; align-items: center; gap: 8px; padding: 4px 6px; font-size: var(--tbl-fs); border-radius: 5px; }
  .mrow .sw { width: 9px; height: 9px; border-radius: 2px; flex: 0 0 auto; }
  .mrow .mn { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .mrow .mv { margin-left: auto; color: var(--fg-muted); font-variant-numeric: tabular-nums; white-space: nowrap; }

  /* expandable project rows */
  .ptable tr.prj { cursor: pointer; }
  .ptable tr.prj:hover td { background: var(--accent-soft); }
  .ptable td.pn .caret { display: inline-block; width: 12px; color: var(--fg-subtle); transition: transform .12s; }
  .ptable tr.prj.open td.pn .caret { transform: rotate(90deg); }
  .exp td { background: var(--surface-2); border-bottom: 2px solid var(--border); padding: 10px 14px; }
  .exp h4 { margin: 8px 0 4px; font-size: .66rem; text-transform: uppercase; letter-spacing: .04em; color: var(--fg-subtle); }
  .exp h4:first-child { margin-top: 0; }
  .subtab { width: 100%; border-collapse: collapse; margin-bottom: 4px; }
  .subtab td, .subtab th { padding: 2px var(--tbl-pad-x); font-size: calc(var(--tbl-fs) - .5px); border-bottom: 1px solid var(--border-subtle); text-align: left; }
  .subtab th { color: var(--fg-subtle); font-size: .6rem; text-transform: uppercase; }
  .subtab .num { text-align: right; font-variant-numeric: tabular-nums; }
  .subtab .dn { max-width: var(--name-max); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .subtab .grp td { background: var(--surface-3); font-weight: 600; color: var(--fg-muted); font-size: .6rem;
                    text-transform: uppercase; letter-spacing: .04em; padding: 5px 8px; }
  .ptable .agrp td { background: var(--surface-3); font-weight: 600; color: var(--fg-muted); font-size: .62rem;
                     text-transform: uppercase; letter-spacing: .04em; padding: 6px 10px; }
  .agnote { color: var(--fg-subtle); font-size: 11px; margin: 2px 0 0; }

  /* header toolbar */
  .topbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: var(--sp-3); }
  .topbar > div:first-child { min-width: 0; }
  /* onboarding notice (shown when only request counts are available) */
  .notice { display: flex; align-items: center; gap: 10px; padding: 9px 12px; margin-bottom: var(--sp-3);
            border: 1px solid var(--accent-soft-border); background: var(--accent-soft); border-radius: var(--radius-sm); }
  .notice-ico { color: var(--accent); font-size: 16px; flex: 0 0 auto; }
  .notice-body { flex: 1; min-width: 0; font-size: var(--fs-sm); color: var(--fg); }
  .notice-x { background: none; border: none; color: var(--fg-muted); font-size: 18px; cursor: pointer;
              line-height: 1; padding: 0 4px; flex: 0 0 auto; }
  .notice-x:hover { color: var(--fg); }
  .toolbar { display: flex; gap: 8px; flex: 0 0 auto; flex-wrap: wrap; }
  .tbtn { font: inherit; font-size: var(--btn-fs); padding: var(--btn-pad-y) var(--btn-pad-x); border: 1px solid var(--border); background: var(--surface);
          border-radius: var(--radius-sm); cursor: pointer; color: var(--fg); white-space: nowrap; }
  .tbtn:hover { border-color: var(--accent); color: var(--accent); }
  .tbtn.active { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }
  .tbtn.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }
  .tbtn.primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); color: var(--accent-fg); }
  .themewrap { position: relative; }
  .theme-pop { position: absolute; right: 0; top: calc(100% + 6px); z-index: 30; width: 214px;
               background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
               box-shadow: 0 8px 26px rgba(0, 0, 0, .18); padding: 12px; }
  .tp-label { font-size: .62rem; text-transform: uppercase; letter-spacing: .06em; font-weight: 600;
              color: var(--fg-muted); margin: 0 0 6px; }
  .tp-modes { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 12px; }
  /* Auto is the default, so give it the full row and leave the four explicit
     palettes paired below it -- five buttons otherwise orphan one cell */
  .tp-modes button[data-mode="auto"] { grid-column: 1 / -1; }
  .tp-modes button { font: inherit; font-size: 12px; padding: 6px 8px; border: 1px solid var(--border);
                     background: var(--surface-2); color: var(--fg); border-radius: var(--radius-sm); cursor: pointer; }
  .tp-modes button:hover { border-color: var(--accent); }
  .tp-modes button.active { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }
  .tp-accents { display: flex; gap: 9px; }
  .tp-accents .sw { width: 24px; height: 24px; border-radius: 50%; background: var(--sw); cursor: pointer;
                    padding: 0; border: 2px solid transparent; box-shadow: 0 0 0 1px var(--border) inset; }
  .tp-accents .sw:hover { transform: scale(1.08); }
  .tp-accents .sw.active { border-color: var(--fg); }

  /* config / hard-filter */
  .prow.excluded { display: none; }
  .cfg-help { color: var(--fg-subtle); font-size: 11px; margin: 0 0 6px; line-height: 1.4; }
  .cfg-text { width: 100%; box-sizing: border-box; min-height: 60px; resize: vertical;
              font: 11px/1.4 ui-monospace, Consolas, "Courier New", monospace;
              border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 6px;
              background: var(--surface); color: var(--fg); }
  .cfg-text:focus { outline: none; border-color: var(--accent); }
  .cfg-actions { display: flex; gap: 6px; margin-top: 6px; flex-wrap: wrap; }
</style>
</head>
<body>
<script>
/* Boot. Runs as the first child of <body> -- before any content paints -- so
   the opening frame already carries the right size tier and theme. Doing this
   at the end of the page instead would flash the desktop layout in a narrow
   panel, and the light palette inside a dark editor. The main script below
   reuses these globals rather than duplicating the logic. */
var SIZE_STEPS = [["xs", 560], ["sm", 820], ["md", 1280], ["lg", 1680]];
var THEME_MODES = ["auto", "light", "dim", "dark", "contrast"];
var THEME_ACCENTS = ["blue", "violet", "teal", "amber", "rose"];
var _modePref = "auto";
function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
function measuredWidth() {
  // documentElement, not body: body padding is itself tier-driven, so
  // measuring body would let the layout oscillate around a boundary.
  return document.documentElement.clientWidth || window.innerWidth || 1024;
}
function sizeTier(w) {
  for (var i = 0; i < SIZE_STEPS.length; i++) if (w < SIZE_STEPS[i][1]) return SIZE_STEPS[i][0];
  return "xl";
}
function isNarrow() { var t = document.body.dataset.size; return t === "xs" || t === "sm"; }
function applySize() {
  var t = sizeTier(measuredWidth());
  if (document.body.dataset.size === t) return false;
  document.body.dataset.size = t;
  return true;
}
// VS Code stamps its theme kind onto the webview body; absence of that marker
// AND of the --vscode-* palette means we are a standalone page in a browser.
function hostKind() {
  var k = document.body.dataset.vscodeThemeKind || "";
  if (k) return k;
  var m = /vscode-(high-contrast-light|high-contrast|dark|light)/.exec(document.body.className || "");
  return m ? "vscode-" + m[1] : "";
}
function hasHostPalette() {
  try { return !!getComputedStyle(document.body).getPropertyValue("--vscode-editor-background").trim(); }
  catch (e) { return false; }
}
// fallback when the palette exists but the kind marker does not: resolve the
// editor background through a throwaway element so we always read plain rgb()
function paletteIsDark() {
  try {
    var p = document.createElement("span");
    p.style.cssText = "position:absolute;visibility:hidden;background:var(--vscode-editor-background,#fff)";
    document.body.appendChild(p);
    var c = getComputedStyle(p).backgroundColor || "";
    p.remove();
    var n = c.match(/\d+(?:\.\d+)?/g);
    if (!n || n.length < 3) return false;
    return (0.299 * n[0] + 0.587 * n[1] + 0.114 * n[2]) < 128;
  } catch (e) { return false; }
}
function resolveMode(m) {
  if (m !== "auto") return m;
  if (hasHostPalette()) return "auto";
  // standalone browser: nothing to inherit, so mirror the OS preference with
  // our own surfaces rather than pinning everyone to the light default
  try { return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"; }
  catch (e) { return "light"; }
}
function applyModeTokens(m) {
  if (THEME_MODES.indexOf(m) < 0) m = "auto";
  _modePref = m;
  var eff = resolveMode(m);
  document.body.dataset.theme = eff;
  if (eff === "auto") {
    var k = hostKind();
    var dark = k ? /dark|high-contrast$/.test(k) : paletteIsDark();
    document.body.dataset.hostKind = dark ? "dark" : "light";
  } else {
    delete document.body.dataset.hostKind;
  }
  return m;
}
function applyAccentTokens(a) {
  if (THEME_ACCENTS.indexOf(a) < 0) a = "blue";
  document.body.dataset.accent = a;
  return a;
}
applySize();
applyModeTokens(lsGet("cpTheme") || "auto");
applyAccentTokens(lsGet("cpAccent") || "blue");
</script>

<div class="topbar">
  <div>
    <h1>GitHub Copilot — Token &amp; AI-Credit Usage</h1>
    <p class="sub" id="refState" data-gen="__GENERATED__"></p>
  </div>
  <div class="toolbar">
    <button class="tbtn" id="filtersBtn" aria-pressed="true" title="Show or hide the filters sidebar">&#9776; Filters</button>
    <button class="tbtn primary" id="refreshBtn">&#8635; Refresh data</button>
    <button class="tbtn" id="csvBtn">Export CSV</button>
    <button class="tbtn" id="cfgBtn">&#9881; Config</button>
    <div class="themewrap">
      <button class="tbtn" id="themeBtn" aria-haspopup="true" aria-expanded="false">&#9681; Theme</button>
      <div class="theme-pop" id="themePop" hidden>
        <p class="tp-label">Mode</p>
        <div class="tp-modes" id="tpModes">
          <button data-mode="auto" title="Follow the editor theme">Auto</button>
          <button data-mode="light">Light</button>
          <button data-mode="dim">Dim</button>
          <button data-mode="dark">Dark</button>
          <button data-mode="contrast">Contrast</button>
        </div>
        <p class="tp-label">Accent</p>
        <div class="tp-accents" id="tpAccents">
          <button class="sw" data-accent="blue"   style="--sw:#3b82f6" title="Blue" aria-label="Blue"></button>
          <button class="sw" data-accent="violet" style="--sw:#8b5cf6" title="Violet" aria-label="Violet"></button>
          <button class="sw" data-accent="teal"   style="--sw:#14b8a6" title="Teal" aria-label="Teal"></button>
          <button class="sw" data-accent="amber"  style="--sw:#f59e0b" title="Amber" aria-label="Amber"></button>
          <button class="sw" data-accent="rose"   style="--sw:#f43f5e" title="Rose" aria-label="Rose"></button>
        </div>
      </div>
    </div>
  </div>
</div>

<div class="notice" id="logNotice" hidden>
  <span class="notice-ico">&#9432;</span>
  <div class="notice-body"><b>Only request counts were found for these sessions.</b> Token, AI-credit (AIU)
    &amp; model figures come from fields Copilot Chat writes into its own logs; older sessions get
    trimmed and debug logs rotate, so only request counts survived. New activity will fill them in.</div>
  <button class="tbtn" id="logEnableBtn">Diagnostics</button>
  <button class="notice-x" id="logDismiss" title="Dismiss" aria-label="Dismiss">&times;</button>
</div>

<nav class="tabs" id="tabs" role="tablist" aria-label="Dashboard views">
  <button class="tab active" role="tab" aria-selected="true" data-tab="overview">Overview</button>
  <button class="tab" role="tab" aria-selected="false" data-tab="calendar">Calendar</button>
  <button class="tab" role="tab" aria-selected="false" data-tab="breakdown">Breakdown</button>
  <button class="tab" role="tab" aria-selected="false" data-tab="agents">Agents</button>
  <button class="tab" role="tab" aria-selected="false" data-tab="skills">Skills</button>
  <button class="tab" role="tab" aria-selected="false" data-tab="strengths">Strengths</button>
  <button class="tab" role="tab" aria-selected="false" data-tab="forecast">Forecast</button>
</nav>

<div id="dashView">
  <div class="pills">
    <div class="pill hero"><div class="k">AI Credits (AIU)</div><div class="v" id="pAiu">0</div><div class="s" id="pAiuSub">nano-AIU / 1e9</div></div>
    <div class="pill"><div class="k">Requests</div><div class="v" id="pReq">0</div><div class="s">LLM calls</div></div>
    <div class="pill"><div class="k">Input tokens</div><div class="v" id="pIn">0</div><div class="s" id="pInSub"></div></div>
    <div class="pill"><div class="k">Output tokens</div><div class="v" id="pOut">0</div><div class="s" id="pOutSub"></div></div>
    <div class="pill"><div class="k">Projects</div><div class="v" id="pProj">0</div></div>
    <div class="pill"><div class="k">Active days</div><div class="v" id="pDays">0</div></div>
  </div>
  <div class="layout">
  <aside class="sidebar">

    <section class="section">
      <header><h2>Date range</h2></header>
      <div class="section-body">
        <div class="presets" id="presets">
          <button data-days="7">7d</button>
          <button data-days="30">30d</button>
          <button data-days="90">90d</button>
          <button data-days="all" class="active">All</button>
        </div>
        <div class="drow">
          <input type="date" id="dFrom"><span>→</span><input type="date" id="dTo">
        </div>
      </div>
    </section>

    <section class="section">
      <header><h2>Harness</h2>
        <span class="acts"><span class="act" id="cliAll">all</span><span class="act" id="cliNone">none</span></span>
      </header>
      <div class="section-body" id="clientList">
        <label class="opt"><input type="checkbox" id="cbVs" checked> VS Code
          <span class="badge" id="badgeVs"></span></label>
        <label class="opt"><input type="checkbox" id="cbCli" checked> CLI
          <span class="badge" id="badgeCli"></span></label>
        <label class="opt"><input type="checkbox" id="cbClaude" checked> Claude Code
          <span class="badge" id="badgeCla"></span></label>
      </div>
    </section>

    <section class="section">
      <header><h2>Models used</h2></header>
      <div class="section-body">
        <div class="mlist" id="mList"></div>
      </div>
    </section>

    <section class="section">
      <header>
        <h2>Projects</h2>
        <span class="acts"><span class="act" id="projAll">all</span><span class="act" id="projNone">none</span><span class="act" id="projClear">clear</span></span>
      </header>
      <div class="section-body">
        <input id="projSearch" type="search" placeholder="Filter projects…" autocomplete="off">
        <p class="proj-hint">Tick projects to focus every metric &amp; chart on them. None ticked = all shown.</p>
        <div class="proj-scroll">
          <div class="proj-list" id="projBody"></div>
        </div>
        <div class="proj-empty" id="projEmpty" hidden>No projects match.</div>
      </div>
    </section>

  </aside>

  <div class="main">

    <section class="tabpanel active" data-tabpanel="overview">
      <div class="panel">
        <h3>AIU credits per day</h3>
        <div id="dailyChart" class="chart"></div>
      </div>
      <div class="panel">
        <h3>Top projects by AIU</h3>
        <div id="topChart"></div>
      </div>
      <div class="panel">
        <h3>Per-project breakdown <span class="hint">— click a row for models, agents &amp; tools</span></h3>
        <div class="ptable-scroll">
          <table class="ptable">
            <thead><tr><th>Project</th><th class="num">Sessions</th><th class="num">Requests</th>
              <th class="num">AIU</th><th class="num">Input</th><th class="num">Output</th></tr></thead>
            <tbody id="tblBody"></tbody>
          </table>
        </div>
      </div>
    </section>

    <section class="tabpanel" data-tabpanel="calendar">
      <div class="panel">
        <h3>Activity calendar — requests per day</h3>
        <div id="calChart" class="cal-wrap"></div>
      </div>
    </section>

    <section class="tabpanel" data-tabpanel="breakdown">
      <div class="panel">
        <h3>Requests by harness</h3>
        <div id="pieClient"></div>
      </div>
      <div class="panel">
        <h3>AIU by model</h3>
        <div id="pieModel"></div>
      </div>
      <div class="panel">
        <h3>Top projects by requests</h3>
        <div id="pieProj"></div>
      </div>
      <div class="panel">
        <h3>Code output by language</h3>
        <div id="pieLang"></div>
      </div>
    </section>

    <section class="tabpanel" data-tabpanel="agents">
      <div class="panel">
        <h3>Cost signals <span class="hint">&mdash; biggest AIU spenders to target for reduction</span></h3>
        <div id="agentSignal"></div>
      </div>
      <div class="panel">
        <h3>Most expensive agents <span class="hint">&mdash; ranked by total AIU within each group: <b>base</b> chat/CLI/Claude agents vs <b>subagents</b> launched via <code>runSubagent</code>. Click a row for its model breakdown. An invocation = one LLM request.</span></h3>
        <div class="ptable-scroll">
          <table class="ptable">
            <thead><tr><th>Agent</th><th class="num">Requests</th><th class="num">Total AIU</th>
              <th class="num">AIU / request</th><th class="num">Input</th><th class="num">Output</th></tr></thead>
            <tbody id="agentBody"></tbody>
          </table>
        </div>
      </div>
      <div class="panel">
        <h3>AIU by agent</h3>
        <div id="pieAgent"></div>
      </div>
    </section>

    <section class="tabpanel" data-tabpanel="skills">
      <div class="panel">
        <h3>Skills used <span class="hint">&mdash; SKILL.md reads in VS Code; each read = one invocation. AIU/tokens are the summed totals of every session that invoked the skill (a session counts toward each skill it used). Recent VS Code sessions only.</span></h3>
        <div class="ptable-scroll">
          <table class="ptable">
            <thead><tr><th>Skill</th><th class="num">Invocations</th><th class="num">Sessions</th>
              <th class="num">AIU</th><th class="num">AIU / session</th><th class="num">Input</th><th class="num">Output</th></tr></thead>
            <tbody id="skillBody"></tbody>
          </table>
        </div>
      </div>
      <div class="panel">
        <h3>Invocations by skill</h3>
        <div id="pieSkill"></div>
      </div>
    </section>

    <section class="tabpanel" data-tabpanel="strengths">
      <div class="panel">
        <h3>Your strengths <span class="hint">&mdash; productivity signals from recorded activity in scope: most-used model/agent, output volume, editing effort and turns-to-completion.</span></h3>
        <div id="stView"></div>
      </div>
    </section>

    <section class="tabpanel" data-tabpanel="forecast">
      <div class="panel">
        <h3>Usage forecast <span class="hint">&mdash; linear projection from recorded AIU in the selected range; labelled estimates, not recorded values. Set <code>budget.monthlyAiu</code> in Config to compare.</span></h3>
        <div id="fcView"></div>
      </div>
    </section>
    </div>
  </div>
</div>

<section class="cfgview" id="cfgView" hidden>
  <div class="panel">
    <h3>Config &amp; hard filters</h3>
    <p class="cfg-help">These exclusions are a <b>hard filter</b>: matching data is removed from the dashboard entirely and disappears from the sidebar &mdash; the sidebar checkboxes only narrow whatever is left. Saved in this browser (localStorage), so it survives reloads. Edit the JSON and click <b>Apply</b>, or <b>Download config.json</b> to bake defaults into the Python generator.</p>
    <textarea id="cfgJson" class="cfg-json" spellcheck="false"></textarea>
    <div class="cfg-actions">
      <button class="tbtn" id="cfgApply">Apply</button>
      <button class="tbtn" id="cfgReset">Reset</button>
      <button class="tbtn" id="cfgDownload">Download config.json</button>
      <span class="cfg-status" id="cfgStatus"></span>
    </div>
    <p class="cfg-note"><b>Fully honoured</b> (re-scopes every number): <code>since</code>, <code>until</code> (YYYY-MM-DD), <code>exclude.projects</code> (case-insensitive substring), <code>exclude.project_prefixes</code> (starts-with), <code>exclude.clients</code> (<code>vscode</code> / <code>cli</code> / <code>claude</code>).<br><b>Breakdown-only</b>: GitHub's per-day telemetry has no model/agent dimension, so <code>exclude.models</code> and <code>exclude.agents</code> filter the model/agent panels but cannot re-scope the daily totals.<br><b>Auto-refresh</b>: <code>autoRefreshMinutes</code> (0 = off). Inside the VS Code extension this re-scans your logs live on that interval; in a plain browser it reloads the report.<br><b>Forecast budget</b>: <code>budget.monthlyAiu</code> (0 / omitted = no budget) drives the Forecast tab's budget comparison; with no budget it shows projected charges only.</p>
  </div>
</section>

<script>
const DATA = __DATA__;
const byName = {};
for (const d of DATA) byName[d.name] = d;

// ---- hard filter (Config tab) — JSON config mirroring config.json ----
const CFG_KEY = "cpConfig";
const DEFAULT_CFG = { since: null, until: null, autoRefreshMinutes: 0,
  budget: { monthlyAiu: null },
  exclude: { projects: [], project_prefixes: [], clients: [], models: [], agents: [] } };
function _arr(a) { return Array.isArray(a) ? a.filter(x => typeof x === "string") : []; }
function normCfg(c) {
  c = (c && typeof c === "object") ? c : {};
  const ex = (c.exclude && typeof c.exclude === "object") ? c.exclude : {};
  return {
    since: (typeof c.since === "string" && c.since) ? c.since : null,
    until: (typeof c.until === "string" && c.until) ? c.until : null,
    autoRefreshMinutes: (typeof c.autoRefreshMinutes === "number" && c.autoRefreshMinutes >= 0) ? c.autoRefreshMinutes : 0,
    budget: { monthlyAiu: (c.budget && typeof c.budget.monthlyAiu === "number" && c.budget.monthlyAiu > 0) ? c.budget.monthlyAiu : null },
    exclude: {
      projects: _arr(ex.projects), project_prefixes: _arr(ex.project_prefixes),
      clients: _arr(ex.clients), models: _arr(ex.models), agents: _arr(ex.agents)
    }
  };
}
function loadCfg() {
  try {
    const raw = localStorage.getItem(CFG_KEY);
    if (raw) return normCfg(JSON.parse(raw));
    const old = JSON.parse(localStorage.getItem("cpExclude") || "[]");
    if (Array.isArray(old) && old.length) return normCfg({ exclude: { projects: old } });
  } catch (e) {}
  return normCfg(DEFAULT_CFG);
}
function saveCfg() { try { localStorage.setItem(CFG_KEY, JSON.stringify(CFG)); } catch (e) {} }
let CFG = loadCfg();
const _lc = s => String(s).toLowerCase();
const CLIENT_ALIAS = { "vscode": "vs", "vs code": "vs", "vs": "vs",
  "cli": "cli", "copilot cli": "cli", "claude": "cla", "claude code": "cla", "cla": "cla" };
function excludedClients() { return new Set(CFG.exclude.clients.map(c => CLIENT_ALIAS[_lc(c).trim()]).filter(Boolean)); }
function isExcluded(name) {
  const n = _lc(name);
  return CFG.exclude.projects.some(x => x && n.includes(_lc(x)))
      || CFG.exclude.project_prefixes.some(x => x && n.startsWith(_lc(x)));
}
function isModelExcluded(name) { const n = _lc(name); return CFG.exclude.models.some(x => x && n === _lc(x)); }
function isAgentExcluded(name) { const n = _lc(name); return CFG.exclude.agents.some(x => x && n === _lc(x)); }
function applyCfgToControls() {
  const ex = excludedClients();
  cbVs.disabled = ex.has("vs"); if (ex.has("vs")) cbVs.checked = false;
  cbCli.disabled = ex.has("cli"); if (ex.has("cli")) cbCli.checked = false;
  cbClaude.disabled = ex.has("cla"); if (ex.has("cla")) cbClaude.checked = false;
}

const cbVs       = document.getElementById("cbVs");
const cbCli      = document.getElementById("cbCli");
const cbClaude   = document.getElementById("cbClaude");
const badgeVs    = document.getElementById("badgeVs");
const badgeCli   = document.getElementById("badgeCli");
const badgeCla   = document.getElementById("badgeCla");
const projSearch = document.getElementById("projSearch");
const projBody   = document.getElementById("projBody");
const projEmpty  = document.getElementById("projEmpty");
const projClear  = document.getElementById("projClear");
const presets    = document.getElementById("presets");
const dFrom      = document.getElementById("dFrom");
const dTo        = document.getElementById("dTo");
const pAiu  = document.getElementById("pAiu");
const pReq  = document.getElementById("pReq");
const pIn   = document.getElementById("pIn");
const pInSub = document.getElementById("pInSub");
const pOut  = document.getElementById("pOut");
const pOutSub = document.getElementById("pOutSub");
const pProj = document.getElementById("pProj");
const pDays = document.getElementById("pDays");
const dailyChart = document.getElementById("dailyChart");
const calChart   = document.getElementById("calChart");
const pieClient  = document.getElementById("pieClient");
const pieModel   = document.getElementById("pieModel");
const pieProj    = document.getElementById("pieProj");
const pieLang    = document.getElementById("pieLang");
const topChart   = document.getElementById("topChart");
const tblBody    = document.getElementById("tblBody");
const mList      = document.getElementById("mList");
const agentBody   = document.getElementById("agentBody");
const agentSignal = document.getElementById("agentSignal");
const pieAgent    = document.getElementById("pieAgent");
const skillBody   = document.getElementById("skillBody");
const pieSkill    = document.getElementById("pieSkill");
const fcView      = document.getElementById("fcView");
const stView      = document.getElementById("stView");
let AGENT_MODELS = {};
let CUR = { vs: true, cli: true, cla: true, from: "0000", to: "9999" };
let curPerProj = [];

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
const fmt = n => n.toLocaleString();
const fmtAiu = n => n.toLocaleString(undefined, { maximumFractionDigits: 2 });
// compact K/M/B for large token counts so they never overflow their box
const fmtK = n => {
  n = Math.round(n || 0);
  if (n >= 1e9) return (n / 1e9).toFixed(2) + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return n.toLocaleString();
};

// ---- date span ----
const allDays = [...new Set(DATA.filter(d => !isExcluded(d.name)).flatMap(d =>
  [...Object.keys(d.vscode.by_day), ...Object.keys(d.cli.by_day), ...Object.keys(d.claude.by_day)]))].sort();
const MIN = allDays[0] || "1970-01-01";
const MAX = allDays[allDays.length - 1] || "1970-01-01";
dFrom.min = dTo.min = MIN;
dFrom.max = dTo.max = MAX;
dFrom.value = MIN;
dTo.value = MAX;

function addDays(iso, n) {
  const t = new Date(iso + "T00:00:00Z");
  t.setUTCDate(t.getUTCDate() + n);
  return t.toISOString().slice(0, 10);
}
function presetFrom(days) {
  const f = addDays(MAX, -(Number(days) - 1));
  return f < MIN ? MIN : f;
}
function setPreset(days) {
  if (days === "all") { dFrom.value = MIN; dTo.value = MAX; }
  else { dTo.value = MAX; dFrom.value = presetFrom(days); }
}
function markActivePreset() {
  let match = "custom";
  if (dFrom.value === MIN && dTo.value === MAX) match = "all";
  else if (dTo.value === MAX) {
    for (const days of [7, 30, 90]) if (dFrom.value === presetFrom(days)) match = String(days);
  }
  for (const btn of presets.querySelectorAll("button"))
    btn.classList.toggle("active", btn.dataset.days === match);
}

// sum one client's metrics within [from, to]
function windowSum(cl, from, to) {
  let s = 0, r = 0, i = 0, o = 0, a = 0;
  for (const date in cl.by_day) {
    if (date >= from && date <= to) {
      const b = cl.by_day[date];
      s += b.sessions; r += b.requests; i += b.in; o += b.out; a += b.aiu;
    }
  }
  return { sessions: s, requests: r, in: i, out: o, aiu: a };
}
function sessTotal(cl) { let s = 0; for (const k in cl.by_day) s += cl.by_day[k].sessions; return s; }

function renderDaily(daily) {
  // one solid bar per active day; contiguous "active days" strip (no gaps).
  const dates = Object.keys(daily).filter(d => (daily[d] || 0) > 0.0001).sort();
  if (!dates.length) { dailyChart.innerHTML = '<div class="muted">No AIU in range.</div>'; return; }
  const max = Math.max(...dates.map(d => daily[d])) || 1;
  const W = 600, H = cssNum("--chart-h", 84), padT = 6, padB = 4, MINH = 2.5;
  const bw = W / dates.length;
  const plot = H - padT - padB;
  let bars = "";
  dates.forEach((d, i) => {
    const val = daily[d];
    const h = Math.max((val / max) * plot, MINH);
    const x = i * bw + 0.5, w = Math.max(bw - 1, 0.8);
    const y = H - padB - h;
    bars += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" ` +
      `height="${h.toFixed(1)}" style="fill:var(--accent)"><title>${d}: ${fmtAiu(val)} AIU</title></rect>`;
  });
  dailyChart.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:${H}px">${bars}</svg>`;
}

// GitHub-style contribution calendar coloured by requests/day (fully recorded).
function renderHeatmap(dailyReq, from, to) {
  const start = new Date(from + "T00:00:00Z");
  start.setUTCDate(start.getUTCDate() - start.getUTCDay());   // back to Sunday
  const end = new Date(to + "T00:00:00Z");
  const vals = Object.values(dailyReq).filter(v => v > 0).sort((a, b) => a - b);
  if (end < start || !vals.length) {
    calChart.innerHTML = '<div class="muted">No activity in range.</div>'; return;
  }
  const q = p => vals[Math.min(vals.length - 1, Math.floor(p * vals.length))];
  const t1 = q(0.25), t2 = q(0.5), t3 = q(0.75);
  const CO = ["var(--cal-0)", "var(--cal-1)", "var(--cal-2)", "var(--cal-3)", "var(--cal-4)"];
  const bucket = n => n <= 0 ? 0 : n <= t1 ? 1 : n <= t2 ? 2 : n <= t3 ? 3 : 4;
  const color = n => CO[bucket(n)];
  const MN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const cell = cssNum("--cal-cell", 24), gap = 5, step = cell + gap, padL = 36, padT = 20;
  let cols = 0, cells = "", months = "", lastMonth = -1;
  const cur = new Date(start);
  while (cur <= end) {
    const col = Math.floor((cur - start) / (7 * 86400000));
    const row = cur.getUTCDay();
    cols = Math.max(cols, col);
    const iso = cur.toISOString().slice(0, 10);
    const x = padL + col * step, y = padT + row * step;
    if (iso >= from && iso <= to) {
      const n = dailyReq[iso] || 0;
      const idx = bucket(n);
      cells += `<rect x="${x}" y="${y}" width="${cell}" height="${cell}" rx="3" style="fill:${CO[idx]}">` +
        `<title>${iso}: ${n} request${n === 1 ? "" : "s"}</title></rect>` +
        `<text x="${x + cell / 2}" y="${y + cell / 2 + 3.5}" text-anchor="middle" font-size="10" ` +
        `style="fill:${idx >= 3 ? "#ffffff" : "var(--fg-muted)"}" pointer-events="none">${cur.getUTCDate()}</text>`;
    }
    const mo = cur.getUTCMonth();
    if (row === 0 && mo !== lastMonth) {
      months += `<text x="${x}" y="${padT - 4}" font-size="10" style="fill:var(--fg-subtle)">${MN[mo]}</text>`;
      lastMonth = mo;
    }
    cur.setUTCDate(cur.getUTCDate() + 1);
  }
  const W = padL + (cols + 1) * step, H = padT + 7 * step;
  const wd = [[1, "Mon"], [3, "Wed"], [5, "Fri"]]
    .map(([r, l]) => `<text x="0" y="${padT + r * step + cell - 1}" font-size="9" style="fill:var(--fg-subtle)">${l}</text>`).join("");
  const legend = `<div class="cal-legend">Less ${CO.map(c => `<span class="cell" style="background:${c}"></span>`).join("")} More</div>`;
  calChart.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${months}${wd}${cells}</svg>${legend}`;
}

const PALETTE = ["#4e79a7", "#f28e2b", "#59a14f", "#b07aa1", "#e15759", "#76b7b2",
                 "#edc948", "#ff9da7", "#9c755f", "#86bcb6", "#d4a6c8", "#bab0ac"];

function renderTop(perProj) {
  const items = [...perProj].filter(p => p.aiu > 0).sort((a, b) => b.aiu - a.aiu);
  const total = items.reduce((s, p) => s + p.aiu, 0);
  if (!total) { topChart.innerHTML = '<div class="muted">No AIU in range.</div>'; return; }
  const N = 8;
  const top = items.slice(0, N);
  const rest = items.slice(N);
  const restSum = rest.reduce((s, p) => s + p.aiu, 0);
  const segs = top.map((p, i) => ({ name: p.name, aiu: p.aiu, color: PALETTE[i % PALETTE.length] }));
  if (restSum > 0) segs.push({ name: `Other (${rest.length})`, aiu: restSum, color: "#adb5bd" });
  const bar = segs.map(s => {
    const pct = s.aiu / total * 100;
    return `<span class="seg" style="width:${pct.toFixed(2)}%;background:${s.color}" ` +
      `title="${esc(s.name)}: ${fmtAiu(s.aiu)} AIU (${pct.toFixed(1)}%)"></span>`;
  }).join("");
  const legend = segs.map(s => {
    const pct = s.aiu / total * 100;
    return `<div class="lg"><span class="sw" style="background:${s.color}"></span>` +
      `<span class="ln" title="${esc(s.name)}">${esc(s.name)}</span>` +
      `<span class="lp">${pct.toFixed(1)}%</span></div>`;
  }).join("");
  topChart.innerHTML = `<div class="stack">${bar}</div><div class="legend">${legend}</div>`;
}

function renderTable(perProj) {
  const rows = [...perProj].sort((a, b) => b.aiu - a.aiu);
  tblBody.innerHTML = rows.map(p =>
    `<tr class="prj" data-name="${esc(p.name)}">` +
      `<td class="pn" title="${esc(p.name)}"><span class="caret">\u25b8</span> ${esc(p.name)}</td>` +
      `<td class="num">${fmt(p.sessions)}</td>` +
      `<td class="num">${fmt(p.requests)}</td>` +
      `<td class="num">${fmtAiu(p.aiu)}</td>` +
      `<td class="num">${fmtK(p.in)}</td>` +
      `<td class="num">${fmtK(p.out)}</td></tr>`
  ).join("") ||
    '<tr><td colspan="6" class="muted">No projects in range.</td></tr>';
}

// ---- models sidebar + agents panel + expandable project detail ----
function renderModels(agg) {
  const items = Object.entries(agg).filter(([name, v]) => v.aiu > 0.01 && name !== "(no token data)" && !isModelExcluded(name))
    .sort((a, b) => b[1].aiu - a[1].aiu);
  if (!items.length) { mList.innerHTML = '<div class="muted">No models in range.</div>'; return; }
  const mMax = items[0][1].aiu || 1;
  mList.innerHTML = items.map(([name, v], i) => {
    const pct = Math.max(3, v.aiu / mMax * 100);
    return `<div class="mrow" style="background:linear-gradient(to right, var(--accent-soft) ${pct}%, transparent ${pct}%)">` +
      `<span class="sw" style="background:${PALETTE[i % PALETTE.length]}"></span>` +
      `<span class="mn" title="${esc(name)}">${esc(name)}</span>` +
      `<span class="mv">${fmtAiu(v.aiu)}</span></div>`;
  }).join("");
}

function arcPath(cx, cy, r, a0, a1) {
  const p = a => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  const [x0, y0] = p(a0), [x1, y1] = p(a1);
  const large = (a1 - a0) > Math.PI ? 1 : 0;
  return `M ${cx} ${cy} L ${x0.toFixed(2)} ${y0.toFixed(2)} ` +
    `A ${r} ${r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} Z`;
}

// donut pie + legend. items = [{name, value}]; fmtFn formats the value tooltip.
function renderPie(el, items, fmtFn) {
  const arr = items.filter(i => i.value > 0).sort((a, b) => b.value - a.value);
  const total = arr.reduce((s, i) => s + i.value, 0);
  if (!total) { el.innerHTML = '<div class="muted">No data in range.</div>'; return; }
  const N = 8;
  const top = arr.slice(0, N);
  const restSum = arr.slice(N).reduce((s, i) => s + i.value, 0);
  const segs = top.map((it, i) => ({ name: it.name, value: it.value, color: PALETTE[i % PALETTE.length] }));
  if (restSum > 0) segs.push({ name: `Other (${arr.length - N})`, value: restSum, color: "#adb5bd" });
  const cx = 80, cy = 80, R = 72;
  let a = -Math.PI / 2, paths = "";
  if (segs.length === 1) {
    paths = `<circle cx="${cx}" cy="${cy}" r="${R}" fill="${segs[0].color}">` +
      `<title>${esc(segs[0].name)}: ${fmtFn(segs[0].value)} (100%)</title></circle>`;
  } else {
    for (const s of segs) {
      const a1 = a + (s.value / total) * 2 * Math.PI;
      const pct = s.value / total * 100;
      paths += `<path d="${arcPath(cx, cy, R, a, a1)}" fill="${s.color}">` +
        `<title>${esc(s.name)}: ${fmtFn(s.value)} (${pct.toFixed(1)}%)</title></path>`;
      a = a1;
    }
  }
  const hole = `<circle cx="${cx}" cy="${cy}" r="40" style="fill:var(--surface)"/>` +
    `<text x="${cx}" y="${cy - 1}" text-anchor="middle" style="fill:var(--fg);font-size:16px;font-weight:650">${fmtK(total)}</text>` +
    `<text x="${cx}" y="${cy + 13}" text-anchor="middle" style="fill:var(--fg-subtle);font-size:8.5px;letter-spacing:.08em">TOTAL</text>`;
  const legend = segs.map(s => {
    const pct = s.value / total * 100;
    return `<div class="lg"><span class="sw" style="background:${s.color}"></span>` +
      `<span class="ln" title="${esc(s.name)}">${esc(s.name)}</span>` +
      `<span class="lp">${pct.toFixed(1)}%</span></div>`;
  }).join("");
  el.innerHTML = `<div class="pie-row"><svg class="pie" viewBox="0 0 160 160">${paths}${hole}</svg>` +
    `<div class="legend">${legend}</div></div>`;
}

function projectDetailHTML(name) {
  const d = byName[name];
  if (!d) return "";
  const model = {}, agent = {}, day = {}, langC = {};
  const acc = (o, k, b) => { const t = o[k] || (o[k] = { req: 0, in: 0, out: 0, aiu: 0 });
    t.req += b.requests; t.in += b.in; t.out += b.out; t.aiu += b.aiu; };
  for (const [clm, on] of [[d.vscode, CUR.vs], [d.cli, CUR.cli], [d.claude, CUR.cla]]) {
    if (!on) continue;
    for (const k in (clm.by_model || {})) acc(model, k, clm.by_model[k]);
    for (const k in (clm.by_agent || {})) acc(agent, k, clm.by_agent[k]);
    for (const dt in clm.by_day) if (dt >= CUR.from && dt <= CUR.to) acc(day, dt, clm.by_day[dt]);
    for (const k in (clm.by_lang || {})) langC[k] = (langC[k] || 0) + clm.by_lang[k];
  }
  const row = (k, v) => `<tr><td class="dn" title="${esc(k)}">${esc(k)}</td>` +
    `<td class="num">${fmt(v.req)}</td>` +
    `<td class="num">${fmtAiu(v.aiu)}</td>` +
    `<td class="num">${fmtK(v.in)}</td><td class="num">${fmtK(v.out)}</td></tr>`;
  const crow = (k, n) => `<tr><td class="dn" title="${esc(k)}">${esc(k)}</td>` +
    `<td class="num">${fmt(n)}</td><td class="num" colspan="3"></td></tr>`;
  const grp = label => `<tr class="grp"><td colspan="5">${label}</td></tr>`;
  const sect = obj => Object.entries(obj).sort((a, b) => b[1].aiu - a[1].aiu).map(([k, v]) => row(k, v)).join("");
  const csect = obj => Object.entries(obj).sort((a, b) => b[1] - a[1]).slice(0, 20).map(([k, n]) => crow(k, n)).join("");
  const none = '<tr><td colspan="5" class="muted">none</td></tr>';
  const modelRows = Object.entries(model).filter(([k]) => k !== "(no token data)" && !isModelExcluded(k))
    .sort((a, b) => b[1].aiu - a[1].aiu).map(([k, v]) => row(k, v)).join("") || none;
  const agentF = Object.fromEntries(Object.entries(agent).filter(([k]) => !isAgentExcluded(k)));
  const agentRows = sect(agentF) || none;
  const dayRows = Object.keys(day).sort().map(dt => row(dt, day[dt])).join("")
    || '<tr><td colspan="5" class="muted">none in range</td></tr>';
  return `<table class="subtab"><thead><tr><th></th><th class="num">Req</th><th class="num">AIU</th>` +
    `<th class="num">In</th><th class="num">Out</th></tr></thead><tbody>` +
    grp("By model") + modelRows +
    grp("By agent") + agentRows +
    grp("By day (selected range)") + dayRows +
    `</tbody></table>`;
}

tblBody.addEventListener("click", e => {
  const tr = e.target.closest("tr.prj");
  if (!tr) return;
  const nxt = tr.nextElementSibling;
  if (nxt && nxt.classList.contains("exp")) { nxt.remove(); tr.classList.remove("open"); return; }
  tr.classList.add("open");
  const exp = document.createElement("tr");
  exp.className = "exp";
  exp.innerHTML = `<td colspan="6">${projectDetailHTML(tr.dataset.name)}</td>`;
  tr.after(exp);
});

// ---- sidebar grid rows (sorted by lifetime sessions) ----
const order = [...DATA].sort((a, b) =>
  (sessTotal(b.vscode) + sessTotal(b.cli) + sessTotal(b.claude)) - (sessTotal(a.vscode) + sessTotal(a.cli) + sessTotal(a.claude))
  || a.name.localeCompare(b.name));

projBody.innerHTML = order.map(d =>
  `<div class="prow" data-name="${esc(d.name)}">` +
  `<label><input type="checkbox" class="projcb" value="${esc(d.name)}">` +
  `<span class="pname" title="${esc(d.name)}">${esc(d.name)}</span></label></div>`
).join("");

const projRows = [...projBody.querySelectorAll(".prow")];
const projCbs  = [...projBody.querySelectorAll(".projcb")];

// ---- agent cost ranking (FR-006) + cost-reduction signals (FR-010) ----
// Ranks named agents/subagents by total attributed AIU (most expensive first) so the
// biggest spenders can be targeted for reduction. AIU/request exposes per-call cost.
// Agents with aiu=0 (Claude Code, pre-telemetry CLI) still list their real request
// counts; only real GitHub-recorded AIU drives the ranking — nothing is estimated.
function renderAgents(agg, am) {
  const items = Object.entries(agg)
    .filter(([name, v]) => !isAgentExcluded(name) && (v.aiu > 0 || v.req > 0))
    .map(([name, v]) => ({ name, req: v.req, aiu: v.aiu, in: v.in, out: v.out, per: v.req ? v.aiu / v.req : 0 }))
    .sort((a, b) => b.aiu - a.aiu || b.req - a.req);
  AGENT_MODELS = {};
  for (const k in (am || {})) {
    const ix = k.indexOf("\u001f");
    const ag = ix >= 0 ? k.slice(0, ix) : k;
    const model = ix >= 0 ? k.slice(ix + 1) : "?";
    if (isAgentExcluded(ag)) continue;
    (AGENT_MODELS[ag] || (AGENT_MODELS[ag] = [])).push({ model, req: am[k].req, aiu: am[k].aiu, in: am[k].in, out: am[k].out });
  }
  if (!items.length) {
    agentSignal.innerHTML = '<div class="muted">No agent activity in range.</div>';
    agentBody.innerHTML = '<tr><td colspan="6" class="muted">No agents in range.</td></tr>';
    renderPie(pieAgent, [], fmtAiu);
    return;
  }
  const BASE = new Set(["GitHub Copilot Chat", "Copilot CLI", "Claude Code"]);
  const base = items.filter(i => BASE.has(i.name));
  const subs = items.filter(i => !BASE.has(i.name));
  const total = items.reduce((s, i) => s + i.aiu, 0);
  const top = items[0];
  const top3 = items.slice(0, 3);
  const top3sum = top3.reduce((s, i) => s + i.aiu, 0);
  const share = total ? top3sum / total * 100 : 0;
  const priciest = base.filter(i => i.req >= 5).sort((a, b) => b.per - a.per)[0];
  const card = (k, v, s) => `<div class="pill"><div class="k">${k}</div>` +
    `<div class="v" style="font-size:var(--card-v-sm);font-weight:600;line-height:1.3;white-space:normal" title="${esc(v)}">${esc(v)}</div>` +
    `<div class="s">${s}</div></div>`;
  const cards = [
    card("Biggest spender", top.name, `${fmtAiu(top.aiu)} AIU · ${total ? (top.aiu / total * 100).toFixed(1) : 0}% of AIU`),
    card("Top 3 agents", top3.map(i => i.name).join(", "), `${share.toFixed(1)}% of AIU (${fmtAiu(top3sum)})`),
  ];
  if (priciest) cards.push(card("Priciest base agent / req", priciest.name, `${fmtAiu(priciest.per)} AIU/req · ${fmt(priciest.req)} req`));
  const subTotal = subs.reduce((s, i) => s + i.aiu, 0);
  if (subs.length) {
    const subTop = subs[0];
    cards.push(card("Top subagent", subTop.name, `${fmtAiu(subTop.aiu)} AIU · ${subTotal ? (subTop.aiu / subTotal * 100).toFixed(1) : 0}% of subagent AIU`));
    const subPri = subs.filter(i => i.req >= 5).sort((a, b) => b.per - a.per)[0];
    if (subPri) cards.push(card("Priciest subagent / req", subPri.name, `${fmtAiu(subPri.per)} AIU/req · ${fmt(subPri.req)} req`));
  }
  agentSignal.innerHTML = `<div class="pills">${cards.join("")}</div>`;
  const rowH = i =>
    `<tr class="prj" data-agent="${esc(i.name)}"><td class="pn" title="${esc(i.name)}"><span class="caret">\u25b8</span> ${esc(i.name)}</td>` +
    `<td class="num">${fmt(i.req)}</td>` +
    `<td class="num">${fmtAiu(i.aiu)}</td>` +
    `<td class="num">${fmtAiu(i.per)}</td>` +
    `<td class="num">${fmtK(i.in)}</td>` +
    `<td class="num">${fmtK(i.out)}</td></tr>`;
  const grpH = (label, n) => `<tr class="agrp"><td colspan="6">${label} (${n})</td></tr>`;
  let body = "";
  if (base.length) body += grpH("Base / harness agents", base.length) + base.map(rowH).join("");
  if (subs.length) body += grpH("Subagents \u00b7 runSubagent", subs.length) + subs.map(rowH).join("");
  agentBody.innerHTML = body || '<tr><td colspan="6" class="muted">No agents in range.</td></tr>';
  renderPie(pieAgent, items.map(i => ({ name: i.name, value: i.aiu })), fmtAiu);
}

agentBody.addEventListener("click", e => {
  const tr = e.target.closest("tr.prj");
  if (!tr) return;
  const nxt = tr.nextElementSibling;
  if (nxt && nxt.classList.contains("exp")) { nxt.remove(); tr.classList.remove("open"); return; }
  tr.classList.add("open");
  const models = (AGENT_MODELS[tr.dataset.agent] || [])
    .filter(x => x.model !== "(no token data)").sort((a, b) => b.aiu - a.aiu);
  const rows = models.map(x =>
    `<tr><td class="dn" title="${esc(x.model)}">${esc(x.model)}</td>` +
    `<td class="num">${fmt(x.req)}</td><td class="num">${fmtAiu(x.aiu)}</td>` +
    `<td class="num">${fmtK(x.in)}</td><td class="num">${fmtK(x.out)}</td></tr>`).join("")
    || '<tr><td colspan="5" class="muted">no model breakdown</td></tr>';
  const exp = document.createElement("tr");
  exp.className = "exp";
  exp.innerHTML = `<td colspan="6"><table class="subtab"><thead><tr><th></th><th class="num">Req</th>` +
    `<th class="num">AIU</th><th class="num">In</th><th class="num">Out</th></tr></thead><tbody>` +
    `<tr class="grp"><td colspan="5">By model</td></tr>${rows}</tbody></table></td>`;
  tr.after(exp);
});

// ---- skills efficiency (FR-007) ----
// Skills are detected from SKILL.md reads (session_files) — each read is a real
// invocation. A session's tokens/AIU are attributed to every skill it invoked
// (honest attribution, documented overlap; nothing estimated). VS Code only.
function renderSkills(agg) {
  const items = Object.entries(agg)
    .map(([name, v]) => ({ name, reads: v.reads, sessions: v.sessions, aiu: v.aiu, in: v.in, out: v.out,
      per: v.sessions ? v.aiu / v.sessions : 0 }))
    .sort((a, b) => b.reads - a.reads || b.aiu - a.aiu);
  if (!items.length) {
    skillBody.innerHTML = '<tr><td colspan="7" class="muted">No SKILL.md reads in range (VS Code only; recent sessions).</td></tr>';
    renderPie(pieSkill, [], fmt);
    return;
  }
  skillBody.innerHTML = items.map(i =>
    `<tr><td class="pn" title="${esc(i.name)}">${esc(i.name)}</td>` +
    `<td class="num">${fmt(i.reads)}</td>` +
    `<td class="num">${fmt(i.sessions)}</td>` +
    `<td class="num">${fmtAiu(i.aiu)}</td>` +
    `<td class="num">${fmtAiu(i.per)}</td>` +
    `<td class="num">${fmtK(i.in)}</td>` +
    `<td class="num">${fmtK(i.out)}</td></tr>`
  ).join("");
  renderPie(pieSkill, items.map(i => ({ name: i.name, value: i.reads })), fmt);
}

// ---- usage forecast (FR-009) — multi-horizon projection + budget cascade ----
// Linear projection from REAL recorded daily AIU. Everything here is an explicit
// projection (labelled), never presented as a recorded value. Budget cascade:
// plan allowance (not locally detectable) -> config budget.monthlyAiu -> none.
function renderForecast(daily, from, to) {
  const dates = Object.keys(daily).filter(d => daily[d] > 0).sort();
  if (!dates.length) { fcView.innerHTML = '<div class="muted">No AIU in range to project from.</div>'; return; }
  const consumed = dates.reduce((s, d) => s + daily[d], 0);
  const activeDays = dates.length;
  const first = dates[0], last = dates[dates.length - 1];
  const spanDays = Math.max(1, Math.round((Date.parse(last) - Date.parse(first)) / 864e5) + 1);
  const dailyCal = consumed / spanDays;
  const t28 = new Date(Date.parse(last)); t28.setUTCDate(t28.getUTCDate() - 27);
  const s28 = t28.toISOString().slice(0, 10);
  let sum28 = 0; for (const d of dates) if (d >= s28) sum28 += daily[d];
  const rate28 = sum28 / 28;
  const useT28 = spanDays >= 28;
  const rate = useT28 ? rate28 : dailyCal;
  const rateLabel = useT28 ? "trailing 28-day avg" : "range average";
  const now = new Date();
  const y = now.getUTCFullYear(), mo = now.getUTCMonth();
  const monthStart = new Date(Date.UTC(y, mo, 1)).toISOString().slice(0, 10);
  const daysInMonth = new Date(Date.UTC(y, mo + 1, 0)).getUTCDate();
  const daysRemaining = Math.max(0, daysInMonth - now.getUTCDate());
  let mtd = 0; for (const d of dates) if (d >= monthStart) mtd += daily[d];
  const projMonth = mtd + rate * daysRemaining;
  const budget = (CFG.budget && typeof CFG.budget.monthlyAiu === "number" && CFG.budget.monthlyAiu > 0) ? CFG.budget.monthlyAiu : null;
  const card = (k, v, s) => `<div class="pill"><div class="k">${k}</div>` +
    `<div class="v" style="font-size:var(--card-v);font-weight:600;line-height:1.3">${v}</div><div class="s">${s}</div></div>`;
  const cards = [
    card("Consumed (in range)", fmtAiu(consumed) + " AIU", `${fmt(activeDays)} active days \u00b7 ${fmt(spanDays)} calendar days`),
    card("Daily rate", fmtAiu(rate) + " AIU/day", rateLabel),
    card("Projected end of month", fmtAiu(projMonth) + " AIU", `MTD ${fmtAiu(mtd)} \u00b7 ${daysRemaining}d left`),
  ];
  if (budget) {
    const pct = projMonth / budget * 100;
    cards.push(card("Monthly budget", fmtAiu(budget) + " AIU", `EoM projection ${pct.toFixed(0)}% of budget`));
  }
  const horizons = [["End of month", projMonth, 1], ["Next 3 months", rate * 90, 3], ["Next 4 months", rate * 120, 4], ["Next 6 months", rate * 180, 6]];
  const rows = horizons.map(([label, proj, months]) => {
    let budgetCell = '<td class="num muted">\u2014</td>', statusCell = '<td class="num muted">\u2014</td>';
    if (budget) {
      const b = budget * months;
      const pct = proj / b * 100;
      const over = proj > b;
      budgetCell = `<td class="num">${fmtAiu(b)}</td>`;
      statusCell = `<td class="num" style="color:${over ? '#d1242f' : '#1a7f37'}">${pct.toFixed(0)}% ${over ? 'over' : 'under'}</td>`;
    }
    return `<tr><td>${label}</td><td class="num">${fmtAiu(proj)}</td>${budgetCell}${statusCell}</tr>`;
  }).join("");
  const note = budget
    ? `Comparing projections against a monthly budget of ${fmtAiu(budget)} AIU (Config \u2192 budget.monthlyAiu).`
    : `No monthly budget set \u2014 showing projected charges only. Add <code>budget.monthlyAiu</code> in Config to compare (plan allowance isn't locally detectable for this account).`;
  fcView.innerHTML = `<div class="pills">${cards.join("")}</div>` +
    `<div class="ptable-scroll" style="margin-top:14px"><table class="ptable"><thead><tr><th>Horizon</th>` +
    `<th class="num">Projected AIU</th><th class="num">Budget</th><th class="num">vs budget</th></tr></thead>` +
    `<tbody>${rows}</tbody></table></div>` +
    `<p class="cfg-note" style="margin-top:10px">Projections are linear estimates from recorded AIU (rate = ${rateLabel}); real usage is bursty. ${note}</p>`;
}

// ---- user-strength stats (FR-008) — productivity cluster ----
// Derived entirely from recorded values: most-used model/agent (by requests),
// output-token volume, edit/read tool-calls (exact from by_tool), and
// turns-to-completion (requests per session). No estimation, no LoC.
function renderStrengths(models, agents, tools, perProj, tot) {
  const topBy = (obj) => Object.entries(obj).filter(([k]) => k !== "(no token data)")
    .sort((a, b) => (b[1].req || 0) - (a[1].req || 0))[0];
  const mm = topBy(models), ma = topBy(agents);
  const editRx = /edit|replace_string|apply_patch|create_file|insert|multi_replace/i;
  let editCalls = 0;
  for (const k in tools) if (editRx.test(k)) editCalls += tools[k];
  const fileReads = tools["read_file"] || 0;
  const tps = tot.sessions ? tot.req / tot.sessions : 0;
  const card = (k, v, s) => `<div class="pill"><div class="k">${k}</div>` +
    `<div class="v" style="font-size:var(--card-v);font-weight:600;line-height:1.3" title="${esc(String(v))}">${esc(String(v))}</div><div class="s">${s}</div></div>`;
  const cards = [
    card("Most-used model", mm ? mm[0] : "\u2014", mm ? fmt(mm[1].req) + " requests" : ""),
    card("Most-used agent", ma ? ma[0] : "\u2014", ma ? fmt(ma[1].req) + " requests" : ""),
    card("Output tokens", fmtK(tot.out), "generated in scope"),
    card("Edit tool-calls", fmt(editCalls), "files edited / created"),
    card("File reads", fmt(fileReads), "read_file calls"),
    card("Turns / session", tps.toFixed(1), fmt(tot.req) + " reqs \u00b7 " + fmt(tot.sessions) + " sessions"),
  ];
  const topProj = [...perProj].filter(p => p.out > 0).sort((a, b) => b.out - a.out).slice(0, 5);
  const projRows = topProj.map(p =>
    `<tr><td class="pn" title="${esc(p.name)}">${esc(p.name)}</td>` +
    `<td class="num">${fmtK(p.out)}</td><td class="num">${fmtK(p.in)}</td>` +
    `<td class="num">${fmt(p.requests)}</td><td class="num">${fmtAiu(p.aiu)}</td></tr>`).join("")
    || '<tr><td colspan="5" class="muted">No output in range.</td></tr>';
  stView.innerHTML = `<div class="pills">${cards.join("")}</div>` +
    `<div class="ptable-scroll" style="margin-top:14px"><table class="ptable"><thead><tr>` +
    `<th>Most productive projects (by output)</th><th class="num">Output</th><th class="num">Input</th>` +
    `<th class="num">Requests</th><th class="num">AIU</th></tr></thead><tbody>${projRows}</tbody></table></div>`;
}

// Resolve the current filter scope (harness toggles, search, project selection,
// clamped date window) and publish it to the module-level CUR + preset UI.
function computeScope() {
  const exCl = excludedClients();
  const vs  = cbVs.checked && !exCl.has("vs");
  const cli = cbCli.checked && !exCl.has("cli");
  const cla = cbClaude.checked && !exCl.has("cla");
  const q   = projSearch.value.trim().toLowerCase();
  const selected = new Set(projCbs.filter(c => c.checked).map(c => c.value));
  let from = dFrom.value || MIN;
  let to   = dTo.value || MAX;
  if (CFG.since && CFG.since > from) from = CFG.since;
  if (CFG.until && CFG.until < to)   to   = CFG.until;
  CUR = { vs, cli, cla, from, to };
  markActivePreset();
  return { vs, cli, cla, q, selected, from, to };
}

// Sidebar harness badges: sessions within the range across all projects.
function renderBadges(scope) {
  const { from, to } = scope;
  let allVs = 0, allCli = 0, allCla = 0;
  for (const d of DATA) {
    if (isExcluded(d.name)) continue;
    allVs += windowSum(d.vscode, from, to).sessions;
    allCli += windowSum(d.cli, from, to).sessions;
    allCla += windowSum(d.claude, from, to).sessions;
  }
  badgeVs.textContent = allVs;
  badgeCli.textContent = allCli;
  badgeCla.textContent = allCla;
}

// Project checkbox grid: mark excluded, hide 0-request/out-of-search rows.
function renderGrid(scope) {
  const { vs, cli, cla, q, from, to } = scope;
  let shown = 0;
  for (const row of projRows) {
    if (isExcluded(row.dataset.name)) { row.classList.add("excluded"); continue; }
    row.classList.remove("excluded");
    const d = byName[row.dataset.name];
    const wv = windowSum(d.vscode, from, to);
    const wc = windowSum(d.cli, from, to);
    const wl = windowSum(d.claude, from, to);
    // only show projects that actually made requests (hide empty 0-request sessions)
    const act = (vs ? wv.requests : 0) + (cli ? wc.requests : 0) + (cla ? wl.requests : 0);
    const visible = act > 0 && row.dataset.name.toLowerCase().includes(q);
    row.classList.toggle("hidden", !visible);
    if (visible) shown++;
  }
  projEmpty.hidden = shown > 0;
}

// Accumulate one client's flat bucket (by_model / by_agent / by_am) into an agg.
function _accDim(o, k, b) {
  const t = o[k] || (o[k] = { req: 0, in: 0, out: 0, aiu: 0 });
  t.req += b.requests; t.in += b.in; t.out += b.out; t.aiu += b.aiu;
}

// Aggregate every in-scope project × enabled client × date-window bucket into the
// totals + per-dimension breakdowns the pills and charts consume.
function aggregate(scope) {
  const { vs, cli, cla, q, selected, from, to } = scope;
  const agg = {
    aiu: 0, req: 0, inTok: 0, outTok: 0, projCount: 0,
    reqVs: 0, reqCli: 0, reqCla: 0, sessTot: 0,
    days: new Set(), daily: {}, dailyReq: {}, perProj: [],
    modelAgg: {}, agentAgg: {}, amAgg: {}, skillAgg: {}, toolAgg: {}, langAgg: {}
  };
  for (const d of DATA) {
    if (isExcluded(d.name)) continue;
    const wv = windowSum(d.vscode, from, to);
    const wc = windowSum(d.cli, from, to);
    const wl = windowSum(d.claude, from, to);
    // only projects that made requests in range (hide empty 0-request sessions)
    const act = (vs ? wv.requests : 0) + (cli ? wc.requests : 0) + (cla ? wl.requests : 0);
    const inScope = act > 0 &&
      (selected.size ? selected.has(d.name) : d.name.toLowerCase().includes(q));
    if (!inScope) continue;
    agg.projCount++;
    let ps = 0, pr = 0, pi = 0, po = 0, pa = 0;
    for (const [clm, on, hk] of [[d.vscode, vs, "vs"], [d.cli, cli, "cli"], [d.claude, cla, "cla"]]) {
      if (!on) continue;
      for (const date in clm.by_day) {
        if (date >= from && date <= to) {
          const b = clm.by_day[date];
          ps += b.sessions; pr += b.requests; pi += b.in; po += b.out; pa += b.aiu;
          agg.daily[date] = (agg.daily[date] || 0) + b.aiu;
          agg.dailyReq[date] = (agg.dailyReq[date] || 0) + b.requests;
          if (hk === "vs") agg.reqVs += b.requests; else if (hk === "cli") agg.reqCli += b.requests; else agg.reqCla += b.requests;
          agg.days.add(date);
        }
      }
      for (const k in (clm.by_model || {})) _accDim(agg.modelAgg, k, clm.by_model[k]);
      for (const k in (clm.by_agent || {})) _accDim(agg.agentAgg, k, clm.by_agent[k]);
      for (const k in (clm.by_am || {})) _accDim(agg.amAgg, k, clm.by_am[k]);
      for (const k in (clm.by_skill || {})) {
        const s = agg.skillAgg[k] || (agg.skillAgg[k] = { reads: 0, sessions: 0, req: 0, in: 0, out: 0, aiu: 0 });
        const b = clm.by_skill[k];
        s.reads += b.reads; s.sessions += b.sessions; s.req += b.requests; s.in += b.in; s.out += b.out; s.aiu += b.aiu;
      }
      for (const k in (clm.by_lang || {})) agg.langAgg[k] = (agg.langAgg[k] || 0) + clm.by_lang[k];
      for (const k in (clm.by_tool || {})) agg.toolAgg[k] = (agg.toolAgg[k] || 0) + clm.by_tool[k];
    }
    agg.perProj.push({ name: d.name, sessions: ps, requests: pr, in: pi, out: po, aiu: pa });
    agg.aiu += pa; agg.req += pr; agg.inTok += pi; agg.outTok += po; agg.sessTot += ps;
  }
  return agg;
}

function render() {
  const scope = computeScope();
  renderBadges(scope);
  renderGrid(scope);
  const a = aggregate(scope);
  _lastAgg = a; _lastScope = scope;

  pAiu.textContent  = fmtAiu(a.aiu);
  pReq.textContent  = fmt(a.req);
  pIn.textContent   = fmtK(a.inTok);
  pOut.textContent  = fmtK(a.outTok);
  pProj.textContent = fmt(a.projCount);
  pDays.textContent = fmt(a.days.size);
  curPerProj = a.perProj;

  renderDaily(a.daily);
  renderHeatmap(a.dailyReq, scope.from, scope.to);
  renderTop(a.perProj);
  renderTable(a.perProj);
  renderModels(a.modelAgg);
  renderAgents(a.agentAgg, a.amAgg);
  renderSkills(a.skillAgg);
  renderStrengths(a.modelAgg, a.agentAgg, a.toolAgg, a.perProj, { out: a.outTok, req: a.req, sessions: a.sessTot });
  renderForecast(a.daily, scope.from, scope.to);
  renderPie(pieClient, [{ name: "VS Code", value: a.reqVs }, { name: "CLI", value: a.reqCli }, { name: "Claude Code", value: a.reqCla }], fmt);
  renderPie(pieModel, Object.entries(a.modelAgg).filter(([name, v]) => v.aiu > 0 && name !== "(no token data)" && !isModelExcluded(name)).map(([name, v]) => ({ name, value: v.aiu })), fmtAiu);
  renderPie(pieProj, a.perProj.map(p => ({ name: p.name, value: p.requests })), fmt);
  renderPie(pieLang, Object.entries(a.langAgg).map(([name, v]) => ({ name, value: v })), fmt);
}

// A tier change only needs the two charts that bake pixel geometry into SVG
// coordinates -- the bar chart's height and the heat-map's cell grid. Every
// other surface is CSS-driven and reflows on its own, so re-aggregating the
// whole dataset on every resize step would be pure waste.
function redrawScaled() {
  if (!_lastAgg) return;
  renderDaily(_lastAgg.daily);
  renderHeatmap(_lastAgg.dailyReq, _lastScope.from, _lastScope.to);
}

cbVs.addEventListener("change", render);
cbCli.addEventListener("change", render);
cbClaude.addEventListener("change", render);
projSearch.addEventListener("input", render);
projBody.addEventListener("change", render);
dFrom.addEventListener("change", render);
dTo.addEventListener("change", render);
presets.addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  setPreset(b.dataset.days);
  render();
});
projClear.addEventListener("click", () => {
  projCbs.forEach(c => c.checked = false);
  projSearch.value = "";
  render();
});
document.getElementById("cliAll").addEventListener("click", () => {
  cbVs.checked = true; cbCli.checked = true; cbClaude.checked = true; render();
});
document.getElementById("cliNone").addEventListener("click", () => {
  cbVs.checked = false; cbCli.checked = false; cbClaude.checked = false; render();
});
document.getElementById("projAll").addEventListener("click", () => {
  projCbs.forEach(c => { if (!c.closest(".prow").classList.contains("hidden")) c.checked = true; });
  render();
});
document.getElementById("projNone").addEventListener("click", () => {
  projCbs.forEach(c => c.checked = false);
  render();
});
const cfgView = document.getElementById("cfgView");
const dashView = document.getElementById("dashView");
const cfgBtn = document.getElementById("cfgBtn");
function setTab(t) {
  const valid = ["overview", "calendar", "breakdown", "agents", "skills", "strengths", "forecast", "config"];
  if (!valid.includes(t)) t = "overview";
  for (const x of document.querySelectorAll("#tabs .tab")) {
    const on = x.dataset.tab === t;
    x.classList.toggle("active", on);
    x.setAttribute("aria-selected", String(on));
  }
  const isCfg = t === "config";
  cfgBtn.classList.toggle("active", isCfg);
  dashView.style.display = isCfg ? "none" : "";
  cfgView.hidden = !isCfg;
  if (!isCfg) for (const p of dashView.querySelectorAll(".tabpanel")) p.classList.toggle("active", p.dataset.tabpanel === t);
  try { localStorage.setItem("cpTab", t); } catch (e) {}
}
document.getElementById("tabs").addEventListener("click", e => {
  const b = e.target.closest(".tab");
  if (!b) return;
  setTab(b.dataset.tab);
});
document.getElementById("tabs").addEventListener("keydown", e => {
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  const tabs = [...document.querySelectorAll("#tabs .tab")];
  const i = tabs.findIndex(x => x.classList.contains("active"));
  if (i < 0) return;
  const j = e.key === "ArrowRight" ? (i + 1) % tabs.length : (i - 1 + tabs.length) % tabs.length;
  setTab(tabs[j].dataset.tab); tabs[j].focus(); e.preventDefault();
});
cfgBtn.addEventListener("click", () => setTab("config"));

// ---- responsive tiers -------------------------------------------------
// Size tiers are bootstrapped by the inline script at the top of <body>, which
// is where `applySize` / `isNarrow` / `sizeTier` live. Only the pieces the
// renderers need are declared here.
let _ready = false, _sizeRaf = 0;
// last render's inputs, kept so a tier change can redraw just the SVG charts
let _lastAgg = null, _lastScope = null;
function cssNum(name, dflt) {
  const v = parseFloat(getComputedStyle(document.body).getPropertyValue(name));
  return Number.isFinite(v) ? v : dflt;
}

// ---- collapsible filters sidebar (usable in the narrow VS Code webview) ----
// Manual toggle wins and persists; with no saved preference the sidebar
// auto-collapses below the responsive breakpoint and re-opens when widened.
const filtersBtn = document.getElementById("filtersBtn");
const SIDEBAR_KEY = "cpSidebar";
function applySidebar(collapsed) {
  document.body.classList.toggle("sidebar-collapsed", collapsed);
  filtersBtn.setAttribute("aria-pressed", String(!collapsed));
  filtersBtn.classList.toggle("active", !collapsed);
}
function sidebarPref() { try { return localStorage.getItem(SIDEBAR_KEY); } catch (e) { return null; } }
function initSidebar() {
  const pref = sidebarPref();
  if (pref === "collapsed") applySidebar(true);
  else if (pref === "open") applySidebar(false);
  else applySidebar(isNarrow());
}
filtersBtn.addEventListener("click", () => {
  const collapsed = !document.body.classList.contains("sidebar-collapsed");
  applySidebar(collapsed);
  try { localStorage.setItem(SIDEBAR_KEY, collapsed ? "collapsed" : "open"); } catch (e) {}
});
function onViewportResize() {
  cancelAnimationFrame(_sizeRaf);
  _sizeRaf = requestAnimationFrame(() => {
    const changed = applySize();
    if (!sidebarPref()) applySidebar(isNarrow());
    if (changed && _ready) redrawScaled();
  });
}
if (window.ResizeObserver) new ResizeObserver(onViewportResize).observe(document.documentElement);
window.addEventListener("resize", onViewportResize);
initSidebar();

applyCfgToControls();
setTab(localStorage.getItem("cpTab") || "overview");
render();
_ready = true;

// ---- theme (mode + accent) ----
const themeBtn = document.getElementById("themeBtn");
const themePop = document.getElementById("themePop");
const tpModes = document.getElementById("tpModes");
const tpAccents = document.getElementById("tpAccents");
function applyMode(m) {
  const pref = applyModeTokens(m);
  for (const b of tpModes.children) b.classList.toggle("active", b.dataset.mode === pref);
}
function applyAccent(a) {
  const pref = applyAccentTokens(a);
  for (const b of tpAccents.children) b.classList.toggle("active", b.dataset.accent === pref);
}
applyMode(lsGet("cpTheme") || "auto");
applyAccent(lsGet("cpAccent") || "blue");
// Colours track the host live because they are var() references, but the
// light/dark stamp that drives `color-scheme` has to be recomputed when the
// user switches editor theme (or OS appearance, when opened standalone).
if (window.MutationObserver) {
  new MutationObserver(() => { if (_modePref === "auto") applyMode("auto"); })
    .observe(document.body, { attributes: true, attributeFilter: ["class", "data-vscode-theme-kind"] });
}
try {
  matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () => { if (_modePref === "auto") applyMode("auto"); });
} catch (e) {}
themeBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  const open = themePop.hidden;
  themePop.hidden = !open;
  themeBtn.setAttribute("aria-expanded", String(open));
});
tpModes.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-mode]"); if (!b) return;
  localStorage.setItem("cpTheme", b.dataset.mode); applyMode(b.dataset.mode);
});
tpAccents.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-accent]"); if (!b) return;
  localStorage.setItem("cpAccent", b.dataset.accent); applyAccent(b.dataset.accent);
});
document.addEventListener("click", (e) => {
  if (!themePop.hidden && !e.target.closest(".themewrap")) {
    themePop.hidden = true; themeBtn.setAttribute("aria-expanded", "false");
  }
});

// ---- export CSV (current in-scope per-project rows) ----
document.getElementById("csvBtn").addEventListener("click", () => {
  const rows = [["Project", "Sessions", "Requests", "AIU", "Input", "Output"]];
  for (const p of [...curPerProj].sort((a, b) => b.aiu - a.aiu))
    rows.push([p.name, p.sessions, p.requests, p.aiu, p.in, p.out]);
  const csv = rows.map(r => r.map(c => {
    const s = String(c);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }).join(",")).join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = "ghcp-usage.csv";
  a.click();
  URL.revokeObjectURL(a.href);
});

// ---- config tab (JSON hard filter) + live refresh ----
const cfgJson = document.getElementById("cfgJson");
const cfgStatus = document.getElementById("cfgStatus");
const cfgTextFromCfg = () => JSON.stringify(CFG, null, 2);
function setCfgStatus(cls, msg) { cfgStatus.className = "cfg-status " + cls; cfgStatus.textContent = msg; }
cfgJson.value = cfgTextFromCfg();
document.getElementById("cfgApply").addEventListener("click", () => {
  let parsed;
  try { parsed = JSON.parse(cfgJson.value); }
  catch (e) { setCfgStatus("err", "Invalid JSON: " + e.message); return; }
  CFG = normCfg(parsed);
  cfgJson.value = cfgTextFromCfg();
  saveCfg();
  applyCfgToControls();
  render();
  setupAutoRefresh();
  setCfgStatus("ok", "Applied \u2713 saved to this browser");
});
document.getElementById("cfgReset").addEventListener("click", () => {
  CFG = normCfg(DEFAULT_CFG);
  cfgJson.value = cfgTextFromCfg();
  saveCfg();
  applyCfgToControls();
  render();
  setupAutoRefresh();
  setCfgStatus("ok", "Reset \u2713 all filters cleared");
});
document.getElementById("cfgDownload").addEventListener("click", () => {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([cfgTextFromCfg()], { type: "application/json" }));
  a.download = "config.json";
  a.click();
  URL.revokeObjectURL(a.href);
  setCfgStatus("ok", "Downloaded config.json \u2713 drop it in the repo root");
});

// refresh: re-extract live inside the VS Code panel, else reload the static report
const vscodeApi = (typeof acquireVsCodeApi !== "undefined") ? acquireVsCodeApi() : null;
const refreshBtn = document.getElementById("refreshBtn");
const refState = document.getElementById("refState");
refreshBtn.title = vscodeApi
  ? "Re-scan your Copilot logs and reload with fresh data"
  : "Reload this report (re-run  python usage.py  first to regenerate the data)";
function triggerRefresh() {
  refreshBtn.disabled = true;
  refreshBtn.textContent = "Refreshing\u2026";
  if (vscodeApi) vscodeApi.postMessage({ type: "refresh" });
  else location.reload();
}
refreshBtn.addEventListener("click", triggerRefresh);

// header status line + configurable auto-refresh ("motor refresh")
let autoTimer = null;
function updateRefState() {
  const gen = refState.dataset.gen || "";
  const n = Number(CFG.autoRefreshMinutes) || 0;
  const parts = [];
  if (gen) parts.push("Updated " + gen);
  parts.push(n > 0 ? "auto-refresh every " + n + " min" : "auto-refresh off");
  refState.textContent = parts.join(" \u00b7 ");
}
function setupAutoRefresh() {
  if (autoTimer) { clearInterval(autoTimer); autoTimer = null; }
  const n = Number(CFG.autoRefreshMinutes) || 0;
  if (n > 0) autoTimer = setInterval(triggerRefresh, n * 60000);
  updateRefState();
}
setupAutoRefresh();

// ---- onboarding notice: no token/AIU data means Copilot Chat logging is off ----
(function () {
  const notice = document.getElementById("logNotice");
  const enableBtn = document.getElementById("logEnableBtn");
  const dismiss = document.getElementById("logDismiss");
  if (!notice) return;
  let hasTokens = false;
  for (const d of DATA) {
    for (const cl of [d.vscode, d.cli, d.claude]) {
      for (const k in (cl.by_day || {})) {
        const b = cl.by_day[k];
        if ((b.aiu || 0) > 0 || (b.in || 0) > 0) { hasTokens = true; break; }
      }
      if (hasTokens) break;
    }
    if (hasTokens) break;
  }
  let dismissed = false;
  try { dismissed = localStorage.getItem("cpLogNotice") === "off"; } catch (e) {}
  if (DATA.length && !hasTokens && !dismissed) {
    notice.hidden = false;
    if (!vscodeApi) enableBtn.hidden = true;   // only actionable inside the extension
  }
  enableBtn.addEventListener("click", () => { if (vscodeApi) vscodeApi.postMessage({ type: "diagnostics" }); });
  dismiss.addEventListener("click", () => {
    notice.hidden = true;
    try { localStorage.setItem("cpLogNotice", "off"); } catch (e) {}
  });
})();
</script>
</body>
</html>
"""
