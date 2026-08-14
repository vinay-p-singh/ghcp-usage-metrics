// Loads the real dashboard into a jsdom window so the interactive code can be
// tested without a browser.
//
// The page is assembled from web/ exactly as build_dashboard.py assembles it,
// so these tests run against the shipping markup and scripts -- not a copy.
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const ROOT = path.join(__dirname, "..", "..");
const WEB = path.join(ROOT, "web");

const CSS_MARK = "<!--@css-->";
const BOOT_MARK = "<!--@boot-js-->";
const MAIN_MARK = "<!--@main-js-->";

function read(...parts) {
  return fs.readFileSync(path.join(WEB, ...parts), "utf8");
}

function mainJs() {
  const dir = path.join(WEB, "js");
  return fs.readdirSync(dir)
    .filter(n => n.endsWith(".js") && n !== "boot.js")
    .sort()
    .map(n => read("js", n))
    .join("");
}

/** The complete page with placeholders still in place. */
function template() {
  return read("dashboard.html")
    .replace(CSS_MARK, read("dashboard.css"))
    .replace(BOOT_MARK, read("js", "boot.js"))
    .replace(MAIN_MARK, mainJs());
}

function bucket(o) {
  return Object.assign({ sessions: 0, requests: 0, in: 0, out: 0, aiu: 0,
                         cached: 0, cached_req: 0 }, o || {});
}

/** One client's metrics, shaped exactly as usage.py emits them. */
function client(days, extra) {
  const by_day = {};
  for (const d in (days || {})) by_day[d] = bucket(days[d]);
  return Object.assign({
    by_day, by_model: {}, by_agent: {}, by_am: {}, by_dm: {}, by_sdm: {},
    by_da: {}, by_dam: {}, by_skill: {}, by_ds: {}, by_tool: {}, by_dt: {},
    by_lang: {}, by_dl: {}, session_names: {}
  }, extra || {});
}

/** A project row. Any client left out is present but empty, as in real output. */
function project(name, parts) {
  const p = parts || {};
  return {
    name,
    vscode: p.vscode || client({}),
    cli: p.cli || client({}),
    claude: p.claude || client({})
  };
}

const FLAT = (o) => Object.assign({ requests: 0, in: 0, out: 0, aiu: 0,
                                    cached: 0, cached_req: 0 }, o);

/** Two projects across two days -- enough for filters, charts and tables. */
function sampleData() {
  return [
    project("acme/alpha", {
      vscode: client(
        { "2026-07-01": { sessions: 1, requests: 10, in: 1000, out: 100, aiu: 50 },
          "2026-07-02": { sessions: 1, requests: 5, in: 500, out: 50, aiu: 25 } },
        { by_model: { "gpt-x": FLAT({ requests: 15, in: 1500, out: 150, aiu: 75 }) },
          by_agent: { "GitHub Copilot Chat": FLAT({ requests: 15, in: 1500, out: 150, aiu: 75 }) },
          by_dm: { "2026-07-01\u001fgpt-x": FLAT({ requests: 10, in: 1000, out: 100, aiu: 50 }),
                   "2026-07-02\u001fgpt-x": FLAT({ requests: 5, in: 500, out: 50, aiu: 25 }) },
          by_sdm: { "vs1\u001f2026-07-01\u001fgpt-x": FLAT({ requests: 10, in: 1000, out: 100, aiu: 50 }),
                    "vs2\u001f2026-07-02\u001fgpt-x": FLAT({ requests: 5, in: 500, out: 50, aiu: 25 }) },
          by_am: { "GitHub Copilot Chat\u001fgpt-x": FLAT({ requests: 15, in: 1500, out: 150, aiu: 75 }) } })
    }),
    project("acme/beta", {
      cli: client(
        { "2026-07-02": { sessions: 2, requests: 4, in: 400, out: 40, aiu: 20 } },
        { by_model: { "gpt-cli": FLAT({ requests: 4, in: 400, out: 40, aiu: 20 }) },
          by_agent: { "Copilot CLI": FLAT({ requests: 4, in: 400, out: 40, aiu: 20 }) },
          by_dm: { "2026-07-02\u001fgpt-cli": FLAT({ requests: 4, in: 400, out: 40, aiu: 20 }) },
          by_sdm: { "cli1\u001f2026-07-02\u001fgpt-cli": FLAT({ requests: 2, in: 200, out: 20, aiu: 10 }),
                    "cli2\u001f2026-07-02\u001fgpt-cli": FLAT({ requests: 2, in: 200, out: 20, aiu: 10 }) },
          by_am: { "Copilot CLI\u001fgpt-cli": FLAT({ requests: 4, in: 400, out: 40, aiu: 20 }) } })
    })
  ];
}

function sampleDiag() {
  return {
    generated: "2026-07-30T12:00:00", platform: "test", python: "3.12",
    mode: "full", quick_days: 0, partial: false,
    elapsed: { total: 1.0 },
    sources: { vscode_debug: { label: "VS Code request logs", roots: [], files_found: 2,
                               files_parsed: 2, files_deferred: 0, files_failed: 0, bad_lines: 0 } },
    errors: [],
    coverage: { requests: 19, requests_no_tokens: 0, pct_no_tokens: 0,
                by_client: { vscode: { requests: 15, no_tokens: 0 },
                             cli: { requests: 4, no_tokens: 0 },
                             claude: { requests: 0, no_tokens: 0 } } },
    credit_floor: { floor: null, onsets: {}, never_reports: [],
                    first_day: "2026-07-01", days_before: 0 },
    no_token_rows: []
  };
}

/**
 * Boot the dashboard. Returns { dom, window, document }.
 * Pass `data` / `diag` to control the dataset the page loads with.
 */
function load(opts) {
  const o = opts || {};
  const html = template()
    .replace("__DATA__", JSON.stringify(o.data || sampleData()))
    .replace("__DIAG__", JSON.stringify(o.diag || sampleDiag()))
    .replace("__GENERATED__", "30/7/2026, 12:00:00 pm");

  const errors = [];
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    pretendToBeVisual: true,
    url: "https://localhost/dashboard.html",
    beforeParse(window) {
      // jsdom has no media queries; the theme boot asks for the OS preference.
      window.matchMedia = window.matchMedia || (q => ({
        matches: false, media: q,
        addEventListener() {}, removeEventListener() {},
        addListener() {}, removeListener() {}
      }));
      window.addEventListener("error", e => errors.push(String(e.error || e.message)));
    }
  });
  dom.window.__errors = errors;
  return { dom, window: dom.window, document: dom.window.document, errors };
}

module.exports = { load, template, sampleData, sampleDiag, project, client, bucket, FLAT };
