// Interaction tests: the parts of the dashboard that only exist once there is a DOM.
//
// Tab switching, filter re-scoping, the live data channel, day selection and
// config application are all behaviours no pure function can express. They run
// against the real assembled page (see harness.js), so a broken selector or a
// renamed element fails here rather than in a browser weeks later.
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const h = require(path.join(__dirname, "harness.js"));

const tick = (ms) => new Promise(r => setTimeout(r, ms || 0));

function boot(opts) {
  const ctx = h.load(opts);
  assert.deepEqual(ctx.errors, [], "page threw while loading");
  return ctx;
}

const text = (doc, id) => doc.getElementById(id).textContent;
const activeTab = doc => doc.querySelector("#tabs .tab.active").dataset.tab;
const activePanel = doc => doc.querySelector("#dashView .tabpanel.active").dataset.tabpanel;

// --------------------------------------------------------------------------
// first paint
// --------------------------------------------------------------------------

test("the page renders the injected dataset on load", () => {
  const { document: doc } = boot();
  assert.equal(text(doc, "pAiu"), "95");          // 75 vscode + 20 cli
  assert.equal(text(doc, "pReq"), "19");
  assert.equal(text(doc, "pProj"), "2");
  assert.equal(text(doc, "pDays"), "2");
  assert.equal(doc.querySelectorAll("#tblBody tr.prj").length, 2);
});

test("an empty dataset renders without throwing", () => {
  const { document: doc } = boot({ data: [] });
  assert.equal(text(doc, "pProj"), "0");
  assert.match(doc.getElementById("dailyChart").textContent, /No AI credits in range/);
});

test("the date inputs open on the full recorded span", () => {
  const { document: doc } = boot();
  assert.equal(doc.getElementById("dFrom").value, "2026-07-01");
  assert.equal(doc.getElementById("dTo").value, "2026-07-02");
});

test("the data source selector lives in Config, with the other settings", () => {
  const { document: doc } = boot({ vscode: true });
  const source = doc.getElementById("qsSource");
  // It sat in the sidebar, which is hidden the moment Config is opened -- so it
  // was invisible exactly when someone went looking for settings.
  assert.ok(doc.querySelector("#cfgView #qsSource"), "source selection is not where settings are");
  assert.equal(doc.querySelector("#dashView #qsSource"), null, "it must not be in both places");
  assert.deepEqual([...source.options].map(option => option.value), ["auto", "debug", "sessions"]);
});

// --------------------------------------------------------------------------
// tabs
// --------------------------------------------------------------------------

test("every tab activates its own panel", () => {
  const { window: win, document: doc } = boot();
  for (const t of ["overview", "calendar", "breakdown", "agents",
                   "skills", "strengths", "forecast", "diagnostics"]) {
    win.setTab(t);
    assert.equal(activeTab(doc), t);
    assert.equal(activePanel(doc), t);
  }
});

test("tabs report their state to assistive technology", () => {
  const { window: win, document: doc } = boot();
  win.setTab("calendar");
  const tabs = [...doc.querySelectorAll("#tabs .tab")];
  const selected = tabs.filter(t => t.getAttribute("aria-selected") === "true");
  assert.equal(selected.length, 1);
  assert.equal(selected[0].dataset.tab, "calendar");
});

test("config is a separate view, not a dashboard panel", () => {
  const { window: win, document: doc } = boot();
  win.setTab("config");
  assert.equal(doc.getElementById("cfgView").hidden, false);
  assert.equal(doc.getElementById("dashView").style.display, "none");
  win.setTab("overview");
  assert.equal(doc.getElementById("cfgView").hidden, true);
  assert.notEqual(doc.getElementById("dashView").style.display, "none");
});

test("an unknown tab falls back to overview instead of blanking the page", () => {
  const { window: win, document: doc } = boot();
  win.setTab("nonsense");
  assert.equal(activeTab(doc), "overview");
});

// --------------------------------------------------------------------------
// cost visibility
// --------------------------------------------------------------------------

test("no cost is shown until a rate is configured", () => {
  const { document: doc } = boot();
  assert.ok(doc.body.classList.contains("nocost"));
  assert.equal(text(doc, "pCost"), "\u2014");
});

test("setting a rate reveals cost everywhere it belongs", () => {
  const { document: doc } = boot();
  doc.getElementById("qsCost").value = "0.01";
  doc.getElementById("qsApply").click();
  assert.ok(!doc.body.classList.contains("nocost"));
  assert.equal(text(doc, "pCost"), "$0.950");     // 95 credits x $0.01
  assert.equal(doc.querySelectorAll("#tblBody td.cost").length, 2);
});

// --------------------------------------------------------------------------
// filters
// --------------------------------------------------------------------------

test("every project is counted until you say otherwise", () => {
  const { document: doc } = boot();
  const boxes = [...doc.querySelectorAll(".projcb")];
  assert.ok(boxes.length > 0);
  assert.ok(boxes.every(c => c.checked), "a project started out excluded");
  assert.equal(text(doc, "pProj"), "2");
});

test("unticking a project removes it from every headline number", () => {
  const { window: win, document: doc } = boot();
  const cb = [...doc.querySelectorAll(".projcb")].find(c => c.value === "acme/alpha");
  cb.checked = false;
  win.render();
  assert.equal(text(doc, "pProj"), "1");
  assert.equal(text(doc, "pAiu"), "20");
  assert.equal(doc.querySelectorAll("#tblBody tr.prj").length, 1);
});

test("clear puts back everything you unticked", () => {
  const { window: win, document: doc } = boot();
  doc.querySelectorAll(".projcb").forEach(c => { c.checked = false; });
  win.render();
  assert.equal(text(doc, "pAiu"), "0");
  doc.getElementById("projClear").click();
  assert.equal(text(doc, "pAiu"), "95");
});

test("unticking a harness removes only that harness's usage", () => {
  const { window: win, document: doc } = boot();
  doc.getElementById("cbCli").checked = false;
  win.render();
  assert.equal(text(doc, "pAiu"), "75");
  assert.equal(text(doc, "pProj"), "1");
});

test("narrowing the date range narrows the totals", () => {
  const { window: win, document: doc } = boot();
  doc.getElementById("dFrom").value = "2026-07-01";
  doc.getElementById("dTo").value = "2026-07-01";
  win.render();
  assert.equal(text(doc, "pAiu"), "50");
  assert.equal(text(doc, "pDays"), "1");
});

test("the project search box filters the sidebar without changing scope", () => {
  const { window: win, document: doc } = boot();
  doc.getElementById("projSearch").value = "beta";
  win.render();
  const visible = [...doc.querySelectorAll(".prow")].filter(r => !r.classList.contains("hidden"));
  assert.equal(visible.length, 1);
  assert.equal(visible[0].dataset.name, "acme/beta");
  assert.equal(text(doc, "pAiu"), "95", "searching quietly re-scoped the totals");
});

// --------------------------------------------------------------------------
// projects with nothing to say about spend
// --------------------------------------------------------------------------

// A project whose requests are real but carry no token payload: pre-telemetry
// CLI turns and trimmed chat sessions both land here. The extractor still files
// them under a date x model key, using the "(no token data)" placeholder, so the
// harness has to as well or the tests will not see what the dashboard sees.
function withQuietProject() {
  const data = h.sampleData();
  data.push(h.project("acme/quiet", {
    cli: h.client({ "2026-07-02": { sessions: 3, requests: 40 } }, {})
  }));
  return data;
}

// Model-less requests do not arrive in a project of their own -- they sit
// alongside real usage, which is why they survived the model filter unnoticed.
function withModelLessRequests() {
  const data = h.sampleData();
  const cli = data.find(p => p.name === "acme/beta").cli;
  cli.by_day["2026-07-02"].requests += 40;
  cli.by_model["(no token data)"] = h.FLAT({ requests: 40 });
  cli.by_dm["2026-07-02\u001f(no token data)"] = h.FLAT({ requests: 40 });
  cli.by_sdm["quiet1\u001f2026-07-02\u001f(no token data)"] = h.FLAT({ requests: 40 });
  return data;
}

test("a project with no recorded tokens is out of the totals by default", () => {
  const { document: doc } = boot({ data: withQuietProject() });
  assert.equal(text(doc, "pProj"), "2", "the token-less project was counted");
  assert.equal(text(doc, "pAiu"), "95");
  assert.equal(text(doc, "pReq"), "19", "its 40 requests leaked into the total");
});

test("it is hidden from the list but offered behind a count", () => {
  const { document: doc } = boot({ data: withQuietProject() });
  const row = [...doc.querySelectorAll(".prow")].find(r => r.dataset.name === "acme/quiet");
  assert.ok(row.classList.contains("hidden"), "row was not demoted");
  const reveal = doc.getElementById("projReveal");
  assert.equal(reveal.hidden, false);
  assert.match(reveal.textContent, /show 1 with no recorded tokens/);
});

test("revealing it shows the row, and ticking it counts it", () => {
  const { window: win, document: doc } = boot({ data: withQuietProject() });
  doc.getElementById("projReveal").click();
  const row = [...doc.querySelectorAll(".prow")].find(r => r.dataset.name === "acme/quiet");
  assert.equal(row.classList.contains("hidden"), false);
  assert.match(doc.getElementById("projReveal").textContent, /^hide 1/);

  row.querySelector(".projcb").checked = true;
  win.render();
  assert.equal(text(doc, "pProj"), "3");
  assert.equal(text(doc, "pReq"), "59");
  assert.equal(text(doc, "pAiu"), "95", "a token-less project must not invent credits");
});

test("turning the setting off counts them from the start", () => {
  const { window: win, document: doc } = boot({ data: withQuietProject() });
  doc.getElementById("qsHideEmpty").checked = false;
  doc.getElementById("qsApply").click();
  assert.equal(text(doc, "pProj"), "3");
  assert.equal(doc.getElementById("projReveal").hidden, true);
  const row = [...doc.querySelectorAll(".prow")].find(r => r.dataset.name === "acme/quiet");
  assert.equal(row.classList.contains("hidden"), false);
  assert.equal(row.querySelector(".projcb").checked, true);
  assert.equal(win.CFG === undefined, true, "CFG is script-scoped; drive it through the form");
});

test("no reveal link appears when every project has real usage", () => {
  const { document: doc } = boot();
  assert.equal(doc.getElementById("projReveal").hidden, true);
});

test("turning the setting back on re-demotes them", () => {
  const { document: doc } = boot({ data: withQuietProject() });
  const apply = (on) => { doc.getElementById("qsHideEmpty").checked = on; doc.getElementById("qsApply").click(); };
  apply(false);
  assert.equal(text(doc, "pProj"), "3");
  apply(true);
  assert.equal(text(doc, "pProj"), "2", "the demoted project stayed in scope");
  assert.equal(doc.getElementById("projReveal").hidden, false);
});

test("a project you unticked yourself stays unticked through a setting change", () => {
  const { document: doc } = boot({ data: withQuietProject() });
  const cb = [...doc.querySelectorAll(".projcb")].find(c => c.value === "acme/alpha");
  cb.checked = false;
  cb.dispatchEvent(new doc.defaultView.Event("change", { bubbles: true }));
  assert.equal(text(doc, "pAiu"), "20");

  doc.getElementById("qsHideEmpty").checked = false;
  doc.getElementById("qsApply").click();
  assert.equal([...doc.querySelectorAll(".projcb")].find(c => c.value === "acme/alpha").checked, false,
               "a deliberate choice was overwritten by the default");
  assert.equal(text(doc, "pAiu"), "20");
});

// --------------------------------------------------------------------------
// model filter
// --------------------------------------------------------------------------

const modelRows = doc => [...doc.querySelectorAll("#mList .mrow")];
const modelBox = (doc, name) => [...doc.querySelectorAll(".modelcb")].find(c => c.value === name);
const check = (doc, cb, on) => {
  cb.checked = on;
  cb.dispatchEvent(new doc.defaultView.Event("change", { bubbles: true }));
};

test("every model is listed and ticked to start with", () => {
  const { document: doc } = boot();
  const names = modelRows(doc).map(r => r.querySelector(".mn").textContent);
  assert.deepEqual(names.sort(), ["gpt-cli", "gpt-x"]);
  assert.ok([...doc.querySelectorAll(".modelcb")].every(c => c.checked));
});

test("unticking a model drops it from the model panels", () => {
  const { document: doc } = boot();
  check(doc, modelBox(doc, "gpt-x"), false);
  const legend = [...doc.querySelectorAll("#pieModel .lg")].map(l => l.textContent);
  assert.ok(!legend.some(t => t.includes("gpt-x")), "excluded model still in the pie");
  assert.ok(legend.some(t => t.includes("gpt-cli")), "the remaining model vanished too");
});

test("it stays listed so it can be brought back", () => {
  const { document: doc } = boot();
  const cb = modelBox(doc, "gpt-x");
  check(doc, cb, false);
  const row = [...doc.querySelectorAll("#mList .mrow")].find(r => r.querySelector(".mn").textContent === "gpt-x");
  assert.ok(row, "the unticked model disappeared from the sidebar");
  assert.ok(row.classList.contains("off"), "it is not shown as switched off");
  assert.equal(modelBox(doc, "gpt-x").checked, false);

  check(doc, modelBox(doc, "gpt-x"), true);
  assert.ok([...doc.querySelectorAll("#pieModel .lg")].some(t => t.textContent.includes("gpt-x")));
});

test("a model filter re-scopes every figure, like a project does", () => {
  // This used to assert the opposite. The logs record a model per request, so
  // once the extractor kept the date x model pairing the filter could reach the
  // headline too -- the old limit was ours, not GitHub's.
  const { document: doc } = boot();
  assert.equal(text(doc, "pAiu"), "95");
  assert.equal(text(doc, "pReq"), "19");

  check(doc, modelBox(doc, "gpt-x"), false);
  assert.equal(text(doc, "pAiu"), "20", "credits did not follow the model filter");
  assert.equal(text(doc, "pReq"), "4");
  assert.equal(text(doc, "pProj"), "1", "a project with no kept-model usage stayed in scope");

  doc.getElementById("modelAll").click();
  assert.equal(text(doc, "pAiu"), "95");
  assert.equal(text(doc, "pProj"), "2");
});

test("unticking every model empties the dashboard rather than ignoring you", () => {
  const { document: doc } = boot();
  doc.getElementById("modelNone").click();
  assert.equal(text(doc, "pAiu"), "0");
  assert.equal(text(doc, "pReq"), "0");
  assert.equal(text(doc, "pProj"), "0");
});

test("unattributed requests stay unfiltered but leave once a model filter is active", () => {
  // "(no token data)" is where requests land when their source never named a
  // model. It is not a model anyone chose, so listing it would invite you to
  // filter by something that was never a choice. Those requests remain in the
  // unfiltered totals and Diagnostics, but cannot match a selected model.
  const { document: doc } = boot({ data: withModelLessRequests() });
  const listed = [...doc.querySelectorAll(".modelcb")].map(c => c.value);
  assert.ok(!listed.includes("(no token data)"), "the placeholder is offered as if it were a model");

  assert.equal(text(doc, "pReq"), "59");
  check(doc, modelBox(doc, "gpt-x"), false);
  assert.equal(text(doc, "pReq"), "4", "unattributed requests survived a model filter");
  assert.equal(text(doc, "pProj"), "1");
  assert.equal(text(doc, "pAiu"), "20");
});

test("session counts follow selected-model activity instead of being withheld", () => {
  const { document: doc } = boot();
  const sessionCell = () => doc.querySelector("#tblBody tr.prj td:nth-child(2)").textContent.trim();
  assert.equal(sessionCell(), "2");

  check(doc, modelBox(doc, "gpt-x"), false);
  assert.equal(sessionCell(), "2");

  doc.getElementById("modelAll").click();
  assert.equal(sessionCell(), "2");
});

test("a mixed-model session is counted once for either selected model", () => {
  const data = h.sampleData();
  const vs = data[0].vscode;
  vs.by_model["gpt-y"] = h.FLAT({ requests: 1, in: 100, out: 10, aiu: 5 });
  vs.by_dm["2026-07-02\u001fgpt-y"] = h.FLAT({ requests: 1, in: 100, out: 10, aiu: 5 });
  vs.by_sdm["vs2\u001f2026-07-02\u001fgpt-y"] = h.FLAT({ requests: 1, in: 100, out: 10, aiu: 5 });
  vs.by_day["2026-07-02"].requests += 1;
  vs.by_day["2026-07-02"].in += 100;
  vs.by_day["2026-07-02"].out += 10;
  vs.by_day["2026-07-02"].aiu += 5;

  const { document: doc } = boot({ data });
  check(doc, modelBox(doc, "gpt-x"), false);
  const alpha = [...doc.querySelectorAll("#tblBody tr.prj")].find(r => r.textContent.includes("acme/alpha"));
  assert.equal(alpha.children[1].textContent.trim(), "1");
});

test("all and none sweep every listed model", () => {
  const { document: doc } = boot();
  doc.getElementById("modelNone").click();
  assert.ok([...doc.querySelectorAll(".modelcb")].every(c => !c.checked));
  doc.getElementById("modelAll").click();
  assert.ok([...doc.querySelectorAll(".modelcb")].every(c => c.checked));
  assert.equal([...doc.querySelectorAll("#pieModel .lg")].length, 2);
});

test("the sidebar reports what the filter is actually doing", () => {
  const { document: doc } = boot();
  const summary = doc.getElementById("mSummary");
  assert.match(summary.textContent, /^2 models · 95 AIU$/);
  assert.equal(summary.classList.contains("filtered"), false);

  check(doc, modelBox(doc, "gpt-x"), false);
  assert.match(summary.textContent, /^1 of 2 models · 20 of 95 AIU$/);
  assert.equal(summary.classList.contains("filtered"), true);

  check(doc, modelBox(doc, "gpt-x"), true);
  assert.match(summary.textContent, /^2 models · 95 AIU$/);
});

// --------------------------------------------------------------------------
// diagnostics visibility
// --------------------------------------------------------------------------

test("diagnostics is available by default", () => {
  const { window: win, document: doc } = boot();
  assert.equal(doc.querySelector('#tabs .tab[data-tab="diagnostics"]').hidden, false);
  win.setTab("diagnostics");
  assert.equal(activePanel(doc), "diagnostics");
});

test("turning diagnostics off retires the tab", () => {
  const { document: doc } = boot();
  doc.getElementById("qsDiag").checked = false;
  doc.getElementById("qsApply").click();
  assert.equal(doc.querySelector('#tabs .tab[data-tab="diagnostics"]').hidden, true);
});

test("a reader sitting on diagnostics is moved off it, never left on a blank panel", () => {
  const { window: win, document: doc } = boot();
  win.setTab("diagnostics");
  assert.equal(activeTab(doc), "diagnostics");
  doc.getElementById("qsDiag").checked = false;
  doc.getElementById("qsApply").click();
  assert.equal(activeTab(doc), "overview");
  assert.equal(activePanel(doc), "overview");
});

test("the tab cannot be reached once it is off", () => {
  const { window: win, document: doc } = boot();
  doc.getElementById("qsDiag").checked = false;
  doc.getElementById("qsApply").click();
  win.setTab("diagnostics");
  assert.equal(activeTab(doc), "overview");
});

// --------------------------------------------------------------------------
// day selection
// --------------------------------------------------------------------------

test("choosing a day filters to it and says so", () => {
  const { window: win, document: doc } = boot();
  win.applyDayFilter("2026-07-01", "2026-07-01");
  assert.equal(doc.getElementById("dFrom").value, "2026-07-01");
  assert.equal(doc.getElementById("dTo").value, "2026-07-01");
  assert.equal(text(doc, "pAiu"), "50");
  assert.equal(activeTab(doc), "overview");
  assert.match(text(doc, "dayChip"), /Showing 2026-07-01/);
});

test("a dragged range reads as a range, in order", () => {
  const { window: win, document: doc } = boot();
  win.applyDayFilter("2026-07-02", "2026-07-01");   // dragged right-to-left
  assert.match(text(doc, "dayChip"), /2026-07-01 \u2192 2026-07-02/);
  assert.equal(doc.getElementById("dFrom").value, "2026-07-01");
});

test("clearing the day filter restores the previous range", () => {
  const { window: win, document: doc } = boot();
  win.applyDayFilter("2026-07-01", "2026-07-01");
  win.clearDayFilter();
  assert.equal(doc.getElementById("dFrom").value, "2026-07-01");
  assert.equal(doc.getElementById("dTo").value, "2026-07-02");
  assert.equal(doc.getElementById("dayChip").hidden, true);
  assert.equal(text(doc, "pAiu"), "95");
});

test("the chip retires when the range is changed another way", () => {
  const { window: win, document: doc } = boot();
  win.applyDayFilter("2026-07-01", "2026-07-01");
  assert.equal(doc.getElementById("dayChip").hidden, false);
  win.rangeChanged();
  assert.equal(doc.getElementById("dayChip").hidden, true);
});

test("a hidden element is genuinely hidden", () => {
  const { document: doc } = boot();
  assert.equal(doc.getElementById("dayChip").hidden, true);
  assert.equal(doc.getElementById("partialNotice").hidden, true);
});

test("no class rule can outrank the hidden attribute", () => {
  // This regressed twice: `.notice{display:flex}` and `.daychip{display:inline-flex}`
  // each beat the browser's own [hidden] rule, leaving dead banners on screen.
  // jsdom does not apply author attribute-selector rules, so the guard is
  // asserted on the stylesheet itself; the rendered result is covered by the
  // Playwright pass.
  const css = require("node:fs")
    .readFileSync(path.join(__dirname, "..", "..", "web", "dashboard.css"), "utf8");
  assert.match(css, /\[hidden\]\s*\{[^}]*display:\s*none\s*!important/,
               "global [hidden] guard is missing from dashboard.css");
});

// --------------------------------------------------------------------------
// reloading data in place
// --------------------------------------------------------------------------

test("pushed data re-renders without losing the reader's place", async () => {
  const { window: win, document: doc } = boot();
  win.setTab("agents");
  const cb = [...doc.querySelectorAll(".projcb")].find(c => c.value === "acme/alpha");
  cb.checked = false;
  cb.dispatchEvent(new win.Event("change", { bubbles: true }));

  const grown = h.sampleData();
  grown[1].cli.by_day["2026-07-03"] = h.bucket({ sessions: 1, requests: 6, aiu: 30 });
  win.postMessage({ type: "data", phase: "full", projects: grown,
                    diag: h.sampleDiag(), generated: "later" }, "*");
  await tick(30);

  assert.equal(activeTab(doc), "agents", "active tab was lost");
  const unchecked = [...doc.querySelectorAll(".projcb")].filter(c => !c.checked).map(c => c.value);
  assert.deepEqual(unchecked, ["acme/alpha"], "project exclusion was lost");
  assert.equal(text(doc, "pAiu"), "50", "new day not included in the re-scoped total");
});

test("a message that is not data is ignored", async () => {
  const { window: win, document: doc } = boot();
  const before = text(doc, "pAiu");
  win.postMessage({ type: "somethingelse" }, "*");
  win.postMessage({ type: "data" }, "*");            // no projects array
  await tick(20);
  assert.equal(text(doc, "pAiu"), before);
});

test("a partial scan says so, and a full one does not", async () => {
  const partial = Object.assign(h.sampleDiag(), { partial: true, quick_days: 10 });
  partial.sources.vscode_debug.files_deferred = 7;
  const { window: win, document: doc } = boot({ diag: partial });
  assert.equal(doc.getElementById("partialNotice").hidden, false);
  assert.match(text(doc, "partialBody"), /last 10 days only/);
  assert.match(text(doc, "partialBody"), /7 older log files/);

  win.postMessage({ type: "data", phase: "full", projects: h.sampleData(),
                    diag: h.sampleDiag() }, "*");
  await tick(30);
  assert.equal(doc.getElementById("partialNotice").hidden, true);
});

// --------------------------------------------------------------------------
// config
// --------------------------------------------------------------------------

test("an excluded project disappears from every surface", () => {
  const { window: win, document: doc } = boot();
  doc.getElementById("cfgJson").value = JSON.stringify({ exclude: { projects: ["beta"] } });
  doc.getElementById("cfgApply").click();
  assert.equal(text(doc, "pProj"), "1");
  assert.equal(text(doc, "pAiu"), "75");
  const row = [...doc.querySelectorAll(".prow")].find(r => r.dataset.name === "acme/beta");
  assert.ok(row.classList.contains("excluded"), "excluded project still offered in the sidebar");
});

test("invalid config is refused with a reason, changing nothing", () => {
  const { document: doc } = boot();
  const before = text(doc, "pAiu");
  doc.getElementById("cfgJson").value = "{ not json";
  doc.getElementById("cfgApply").click();
  assert.match(text(doc, "cfgStatus"), /Invalid JSON/);
  assert.equal(text(doc, "pAiu"), before);
});

test("a confirmation clears itself instead of lingering", () => {
  const { window: win, document: doc } = boot();
  let fire = null;
  win.setTimeout = fn => { fire = fn; return 1; };

  doc.getElementById("qsApply").click();
  assert.equal(text(doc, "qsStatus"), "Saved \u2713");

  fire();
  assert.equal(text(doc, "qsStatus"), "", "the confirmation is still on screen long after the save");
});

test("returning to the config tab does not show a stale confirmation", () => {
  const { document: doc } = boot();

  doc.getElementById("qsApply").click();
  assert.equal(text(doc, "qsStatus"), "Saved \u2713");

  doc.querySelector('#tabs .tab[data-tab="overview"]').click();
  doc.getElementById("cfgBtn").click();
  assert.equal(text(doc, "qsStatus"), "", "a save from an earlier visit is being reported as if it just happened");
});

test("a configured start date becomes the earliest selectable day", () => {
  const { document: doc } = boot();
  doc.getElementById("qsSince").value = "2026-07-02";
  doc.getElementById("qsApply").click();
  assert.equal(doc.getElementById("dFrom").min, "2026-07-02");
  assert.equal(doc.getElementById("dFrom").value, "2026-07-02");
  assert.equal(text(doc, "pAiu"), "45");           // 25 vscode + 20 cli
});

test("quick settings and the JSON editor stay in step", () => {
  const { document: doc } = boot();
  doc.getElementById("qsCost").value = "0.02";
  doc.getElementById("qsApply").click();
  assert.equal(JSON.parse(doc.getElementById("cfgJson").value).cost.usdPerAiu, 0.02);
  assert.ok(!doc.body.classList.contains("nocost"));
});

test("reset clears filters and reopens the full span", () => {
  const { document: doc } = boot();
  doc.getElementById("cfgJson").value = JSON.stringify({
    since: "2026-07-02", exclude: { projects: ["beta"] } });
  doc.getElementById("cfgApply").click();
  assert.equal(text(doc, "pProj"), "1");

  doc.getElementById("cfgReset").click();
  assert.equal(text(doc, "pProj"), "2");
  assert.equal(text(doc, "pAiu"), "95");
  assert.equal(doc.getElementById("dFrom").value, "2026-07-01");
});

// --------------------------------------------------------------------------
// diagnostics
// --------------------------------------------------------------------------

test("a clean scan reports no problems", () => {
  const { document: doc } = boot();
  assert.equal(doc.getElementById("diagBadge").hidden, true);
  assert.match(doc.getElementById("diagErrors").textContent, /No read or parse failures/);
  assert.match(doc.getElementById("diagCoverage").textContent, /Every recorded request carries token data/);
});

test("failures surface as a badge and a listed cause", () => {
  const diag = h.sampleDiag();
  diag.sources.vscode_debug.files_failed = 2;
  diag.sources.vscode_debug.bad_lines = 3;
  diag.errors = [{ source: "vscode_debug", path: "C:/x/main.jsonl", error: "OSError: denied" }];
  const { document: doc } = boot({ diag });
  assert.equal(doc.getElementById("diagBadge").hidden, false);
  assert.equal(doc.getElementById("diagBadge").textContent, "5");   // 2 files + 3 lines
  assert.match(doc.getElementById("diagErrors").textContent, /OSError: denied/);
});

test("requests without tokens are attributed, not hidden", () => {
  const diag = h.sampleDiag();
  diag.coverage.requests_no_tokens = 4;
  diag.coverage.pct_no_tokens = 21.05;
  diag.coverage.by_client.cli.no_tokens = 4;
  diag.no_token_rows = [{ project: "acme/beta", client: "cli", requests: 4, no_tokens: 4,
                          reason: "Copilot CLI stored no per-request tokens." }];
  const { document: doc } = boot({ diag });
  const cov = doc.getElementById("diagCoverage").textContent;
  assert.match(cov, /4 of 19 requests/);
  assert.match(cov, /acme\/beta/);
  assert.match(cov, /Copilot CLI stored no per-request tokens/);
});

// --------------------------------------------------------------------------
// safety
// --------------------------------------------------------------------------

test("a project name containing markup cannot inject HTML", () => {
  const evil = "<img src=x onerror=alert(1)>";
  const data = [h.project(evil, {
    vscode: h.client({ "2026-07-01": { sessions: 1, requests: 1, aiu: 1 } })
  })];
  const { document: doc } = boot({ data });
  assert.equal(doc.querySelectorAll("#tblBody img").length, 0);
  assert.equal(doc.querySelector("#tblBody tr.prj").dataset.name, evil);
});

// ---- credit-coverage cutoff ------------------------------------------------
// The cutoff changes which dates the page opens on. It must not change what is
// reachable: the earlier months are incomplete, not unwanted.
//
// The fixture deliberately holds data in the month BEFORE the floor, otherwise
// rounding back to the first of the month would be indistinguishable from
// opening on the earliest day and the assertions would prove nothing.

function withFloor() {
  const diag = h.sampleDiag();
  diag.credit_floor = {
    floor: "2026-07-09", onsets: { vscode: "2026-05-17", cli: "2026-07-09" },
    never_reports: ["claude"], first_day: "2026-06-15", days_before: 3
  };
  return diag;
}

function withEarlierMonth() {
  const data = h.sampleData();
  const vs = data[0].vscode;
  vs.by_day["2026-06-15"] = { sessions: 1, requests: 2, in: 200, out: 20,
                              aiu: 0, cached: 0, cached_req: 0 };
  vs.by_dm["2026-06-15\u001fgpt-x"] = h.FLAT({ requests: 2, in: 200, out: 20 });
  vs.by_sdm["vs0\u001f2026-06-15\u001fgpt-x"] = h.FLAT({ requests: 2, in: 200, out: 20 });
  return data;
}

test("the page opens at the start of the cutoff month, not the earliest day", () => {
  const { document: doc } = boot({ diag: withFloor(), data: withEarlierMonth() });
  assert.equal(doc.getElementById("dFrom").value, "2026-07-01",
               "a mid-month floor opens on the whole month it falls in");
  assert.equal(doc.getElementById("dFrom").min, "2026-06-15",
               "the earlier data must still be selectable");
});

test("the cutoff notice explains itself and names when each harness started", () => {
  const { document: doc } = boot({ diag: withFloor(), data: withEarlierMonth() });
  const notice = doc.getElementById("floorNotice");
  assert.equal(notice.hidden, false);
  const text = doc.getElementById("floorBody").textContent;
  assert.match(text, /2026-07-09/);
  assert.match(text, /VS Code from 2026-05-17/);
  assert.match(text, /Copilot CLI from 2026-07-09/);
  assert.match(text, /Claude Code publishes no credit figure/);
});

test("including the earlier data widens the range and retires the notice", () => {
  const { window: win, document: doc } = boot({ diag: withFloor(), data: withEarlierMonth() });
  doc.getElementById("floorShowAll").dispatchEvent(
    new win.MouseEvent("click", { bubbles: true }));
  assert.equal(doc.getElementById("dFrom").value, "2026-06-15");
  assert.equal(doc.getElementById("floorNotice").hidden, true);
});

test("a background refresh does not drag the reader back to the floor", () => {
  const { window: win, document: doc } = boot({ diag: withFloor() });
  doc.getElementById("floorShowAll").dispatchEvent(
    new win.MouseEvent("click", { bubbles: true }));
  win.postMessage({ type: "data", projects: h.sampleData(), diag: withFloor(),
                    phase: "full" }, "*");
  return new Promise(resolve => win.setTimeout(() => {
    assert.equal(doc.getElementById("dFrom").value, "2026-07-01",
                 "the reader chose the full span; a refresh must respect it");
    resolve();
  }, 0));
});

test("no floor means the page opens on everything, as it always did", () => {
  const { document: doc } = boot({});
  assert.equal(doc.getElementById("dFrom").value, doc.getElementById("dFrom").min);
  assert.equal(doc.getElementById("floorNotice").hidden, true);
});

test("diagnostics states when each harness began reporting credits", () => {
  const { document: doc } = boot({ diag: withFloor(), data: withEarlierMonth() });
  const html = doc.getElementById("diagFloor").textContent;
  assert.match(html, /2026-07-09/, "the floor itself must be stated");
  assert.match(html, /VS Code/);
  assert.match(html, /2026-05-17/, "each harness onset must be listed");
  assert.match(html, /Claude Code/, "a harness that never reports must be named");
  assert.match(html, /3 earlier active days/, "how much sits below the floor");
});

test("with no floor the diagnostics panel says so rather than rendering blank", () => {
  const { document: doc } = boot({});
  const html = doc.getElementById("diagFloor").textContent;
  assert.ok(html.trim().length > 0, "an empty panel reads as a rendering bug");
  assert.match(html, /No AI credits/i);
});

test("config shows the computed cutoff date as a fixed, non-editable value", () => {
  const { document: doc } = boot({ diag: withFloor(), data: withEarlierMonth() });
  const el = doc.getElementById("qsFloor");
  assert.match(el.value, /2026-07-01/, "the date the view opens on");
  assert.match(el.value, /2026-07-09/, "and the measured floor behind it");
  assert.ok(el.readOnly, "it is derived from the logs, so it is not editable");
});

test("turning the cutoff off in config opens the view on everything", () => {
  const { window: win, document: doc } = boot({ diag: withFloor(), data: withEarlierMonth() });
  assert.equal(doc.getElementById("dFrom").value, "2026-07-01");
  const box = doc.getElementById("qsFloorOn");
  assert.equal(box.checked, true, "the cutoff is on by default");
  box.checked = false;
  doc.getElementById("qsApply").dispatchEvent(
    new win.MouseEvent("click", { bubbles: true }));
  assert.equal(doc.getElementById("dFrom").value, doc.getElementById("dFrom").min,
               "with the cutoff off the view opens on all recorded history");
});

test("with no floor computed the config field says so rather than sitting blank", () => {
  const { document: doc } = boot({});
  assert.match(doc.getElementById("qsFloor").value, /not|none|—/i);
});

// ---- sessions and cache surfaces -------------------------------------------
// Both were extracted for several turns before anything showed them. A figure
// that exists only in the JSON is not an answer to anybody.

test("the sessions tab lists sessions ranked by what they cost", () => {
  const { document: doc } = boot({});
  doc.querySelector('#tabs .tab[data-tab="sessions"]').click();
  const rows = [...doc.querySelectorAll("#sessionBody tr")];
  assert.ok(rows.length >= 2, "the fixture's sessions must be listed");
  const credits = rows.map(r => parseFloat(r.children[4].textContent.replace(/,/g, "")));
  assert.deepEqual([...credits].sort((a, b) => b - a), credits,
                   "rows must be ordered by credits, most expensive first");
});

test("an unnamed session shows its id and says so, rather than being blank", () => {
  const { document: doc } = boot({});
  doc.querySelector('#tabs .tab[data-tab="sessions"]').click();
  const first = doc.querySelector("#sessionBody tr td");
  assert.ok(first.textContent.trim().length > 0);
  assert.match(first.textContent, /unnamed/,
               "the harness fixture has no session names, so it must say so");
});

test("switching a harness off removes its sessions from the tab", () => {
  const { window: win, document: doc } = boot({});
  doc.querySelector('#tabs .tab[data-tab="sessions"]').click();
  const before = doc.querySelectorAll("#sessionBody tr").length;
  const cb = doc.getElementById("cbVs");
  cb.checked = false;
  cb.dispatchEvent(new win.Event("change", { bubbles: true }));
  const after = doc.querySelectorAll("#sessionBody tr").length;
  assert.ok(after < before, `sessions should drop from ${before}, got ${after}`);
});

test("the cache split reports how much input came from cache", () => {
  const { document: doc } = boot({});
  const el = doc.getElementById("cacheSplit");
  assert.ok(el.querySelectorAll(".seg").length === 2, "cached and fresh segments");
  assert.match(el.textContent, /From cache/);
  assert.match(el.textContent, /Fresh/);
});

test("a partial cache answer says it is a floor rather than the whole picture", () => {
  const data = h.sampleData();
  const vs = data[0].vscode;
  for (const d in vs.by_day) { vs.by_day[d].cached = 10; vs.by_day[d].cached_req = 0; }
  const { document: doc } = boot({ data });
  assert.match(doc.getElementById("cacheSplit").textContent, /floor/i);
});

test("a near-complete cache answer is stated, not warned about", () => {
  // 99% coverage triggering a warning is the same wallpaper problem the day
  // markers had: a caveat that fires everywhere stops being read.
  const data = h.sampleData();
  for (const p of data) {
    for (const k of ["vscode", "cli", "claude"]) {
      for (const d in p[k].by_day) {
        p[k].by_day[d].cached = Math.round(p[k].by_day[d].in * 0.9);
        p[k].by_day[d].cached_req = p[k].by_day[d].requests;
      }
    }
  }
  const { document: doc } = boot({ data });
  const txt = doc.getElementById("cacheSplit").textContent;
  assert.doesNotMatch(txt, /floor/i, "a complete answer must not be hedged");
  assert.match(txt, /reported a cache figure/);
});

// ---- token-less sessions are noise in a "what did this cost" view ----------
// Hidden by default, counted, and one click away -- the same treatment projects
// with no recorded tokens already get. Removing them outright would be the
// discarding the rest of this tool exists to avoid.

function withQuietSession() {
  const data = h.sampleData();
  const vs = data[0].vscode;
  vs.by_sdm["quietS\u001f2026-07-01\u001f(no token data)"] = h.FLAT({ requests: 3 });
  vs.by_day["2026-07-01"].requests += 3;
  vs.by_dm["2026-07-01\u001f(no token data)"] = h.FLAT({ requests: 3 });
  return data;
}

test("a session with requests but no tokens is kept out of the ranking", () => {
  const { document: doc } = boot({ data: withQuietSession() });
  doc.querySelector('#tabs .tab[data-tab="sessions"]').click();
  const labels = [...doc.querySelectorAll("#sessionBody tr td:first-child")]
    .map(td => td.textContent);
  assert.ok(!labels.some(l => /quietS/.test(l)),
            "a session that cost nothing recordable is noise in a cost ranking");
});

test("the hidden sessions are counted and offered, never silently dropped", () => {
  const { document: doc } = boot({ data: withQuietSession() });
  doc.querySelector('#tabs .tab[data-tab="sessions"]').click();
  const reveal = doc.getElementById("sessReveal");
  assert.equal(reveal.hidden, false);
  assert.match(reveal.textContent, /1/, "it must say how many are hidden");
});

test("revealing them brings them back into the table", () => {
  const { window: win, document: doc } = boot({ data: withQuietSession() });
  doc.querySelector('#tabs .tab[data-tab="sessions"]').click();
  const before = doc.querySelectorAll("#sessionBody tr").length;
  doc.getElementById("sessReveal").dispatchEvent(
    new win.MouseEvent("click", { bubbles: true }));
  const after = doc.querySelectorAll("#sessionBody tr").length;
  assert.equal(after, before + 1);
  assert.match(doc.getElementById("sessReveal").textContent, /hide/i);
});

test("with nothing to hide the reveal control stays out of the way", () => {
  const { document: doc } = boot({});
  doc.querySelector('#tabs .tab[data-tab="sessions"]').click();
  assert.equal(doc.getElementById("sessReveal").hidden, true);
});

test("clicking a session column header sorts by it", () => {
  const { window: win, document: doc } = boot({});
  doc.querySelector('#tabs .tab[data-tab="sessions"]').click();
  const th = doc.querySelector('[data-tabpanel="sessions"] th[data-sort="requests"]');
  th.dispatchEvent(new win.MouseEvent("click", { bubbles: true }));
  const reqs = [...doc.querySelectorAll("#sessionBody tr")]
    .map(r => parseFloat(r.children[3].textContent.replace(/,/g, "")));
  assert.deepEqual(reqs, [...reqs].sort((a, b) => b - a),
                   "a measure column opens on biggest-first");
  assert.equal(th.getAttribute("aria-sort"), "descending");
});

test("clicking the same header again reverses it", () => {
  const { window: win, document: doc } = boot({});
  doc.querySelector('#tabs .tab[data-tab="sessions"]').click();
  const th = doc.querySelector('[data-tabpanel="sessions"] th[data-sort="requests"]');
  th.dispatchEvent(new win.MouseEvent("click", { bubbles: true }));
  th.dispatchEvent(new win.MouseEvent("click", { bubbles: true }));
  const reqs = [...doc.querySelectorAll("#sessionBody tr")]
    .map(r => parseFloat(r.children[3].textContent.replace(/,/g, "")));
  assert.deepEqual(reqs, [...reqs].sort((a, b) => a - b));
  assert.equal(th.getAttribute("aria-sort"), "ascending");
});

test("the sorted column is the only one marked, so the header cannot lie", () => {
  const { window: win, document: doc } = boot({});
  doc.querySelector('#tabs .tab[data-tab="sessions"]').click();
  doc.querySelector('[data-tabpanel="sessions"] th[data-sort="in"]')
    .dispatchEvent(new win.MouseEvent("click", { bubbles: true }));
  const marked = [...doc.querySelectorAll('[data-tabpanel="sessions"] th.sortable')]
    .filter(t => t.getAttribute("aria-sort") !== "none");
  assert.equal(marked.length, 1);
  assert.equal(marked[0].dataset.sort, "in");
});

test("the chosen sort survives a filter change", () => {
  const { window: win, document: doc } = boot({});
  doc.querySelector('#tabs .tab[data-tab="sessions"]').click();
  doc.querySelector('[data-tabpanel="sessions"] th[data-sort="project"]')
    .dispatchEvent(new win.MouseEvent("click", { bubbles: true }));
  const cb = doc.getElementById("cbCli");
  cb.checked = false;
  cb.dispatchEvent(new win.Event("change", { bubbles: true }));
  const th = doc.querySelector('[data-tabpanel="sessions"] th[data-sort="project"]');
  assert.equal(th.getAttribute("aria-sort"), "ascending",
               "re-rendering must not silently reset the reader's choice");
});

// --------------------------------------------------------------------------
// which store produced the numbers
// --------------------------------------------------------------------------

function withSource(source) {
  const diag = h.sampleDiag();
  diag.source = Object.assign({ requested: "auto", effective: "auto",
                                debug_sessions: 2, chat_credit_first: null }, source);
  return diag;
}

test("a normal run shows no source banner", () => {
  const { document: doc } = boot({ diag: withSource({}) });
  assert.equal(doc.getElementById("sourceNotice").hidden, true);
});

test("a report built from saved sessions says so on the first screen", () => {
  const { document: doc } = boot({ diag: withSource({
    effective: "sessions", debug_sessions: 0, chat_credit_first: "2026-06-26" }) });
  const notice = doc.getElementById("sourceNotice");
  assert.equal(notice.hidden, false, "the fallback has to be visible without opening a tab");
  assert.match(notice.textContent, /saved sessions/i);
  assert.match(notice.textContent, /2026-06-26/);
  assert.ok(notice.classList.contains("partial"), "an unrequested fallback is a warning");
});

test("a sessions-only calendar replaces repetitive day warnings with one coverage note", () => {
  const data = [h.project("acme/saved", {
    vscode: h.client(
      { "2026-07-01": { sessions: 1, requests: 1, in: 100, out: 10, aiu: 0 } },
      { by_model: { "gpt-x": h.FLAT({ requests: 1, in: 100, out: 10 }) },
        by_dm: { "2026-07-01\u001fgpt-x": h.FLAT({ requests: 1, in: 100, out: 10 }) },
        by_sdm: { "s1\u001f2026-07-01\u001fgpt-x": h.FLAT({ requests: 1, in: 100, out: 10 }) } })
  })];
  const { document: doc } = boot({ data, diag: withSource({
    requested: "sessions", effective: "sessions", debug_sessions: 0,
    chat_credit_first: "2026-06-26"
  }) });

  const note = doc.getElementById("calSourceNote");
  assert.equal(note.hidden, false);
  assert.match(note.textContent, /saved session/i);
  assert.equal(doc.querySelectorAll("#calChart .calwarn").length, 0);
});

test("missing debug logs show setup steps even when saved sessions contain token data", () => {
  const { document: doc } = boot({ diag: withSource({
    effective: "sessions", debug_sessions: 0, chat_credit_first: "2026-06-26" }) });
  const notice = doc.getElementById("logNotice");
  assert.equal(notice.hidden, false);
  assert.match(notice.textContent, /agent debug file logging/i);
  assert.match(notice.textContent, /github\.copilot\.chat\.agentDebugLog\.fileLogging\.enabled/);
});

test("the extension can enable agent debug file logging from the notice", () => {
  const { document: doc, window: win } = boot({
    diag: withSource({ effective: "sessions", debug_sessions: 0 }), vscode: true
  });
  doc.getElementById("logEnableBtn").click();
  assert.ok(win.__posted.some(message => message.type === "enableDebugLogs"));
});

test("deliberately choosing a store is not styled as a warning", () => {
  const { document: doc } = boot({ diag: withSource({
    requested: "sessions", effective: "sessions", chat_credit_first: "2026-06-26" }) });
  const notice = doc.getElementById("sourceNotice");
  assert.equal(notice.hidden, false);
  assert.equal(notice.classList.contains("partial"), false);
});

test("the source banner can be dismissed and stays dismissed", () => {
  const { document: doc, window: win } = boot({ diag: withSource({
    effective: "sessions", debug_sessions: 0 }) });
  doc.getElementById("sourceDismiss").click();
  assert.equal(doc.getElementById("sourceNotice").hidden, true);
  assert.equal(win.localStorage.getItem("cpSourceNotice"), "off");
});

test("a project name is escaped in the source banner path too", () => {
  const { document: doc } = boot({ diag: withSource({
    effective: "sessions", debug_sessions: 0, chat_credit_first: "<img src=x>" }) });
  const notice = doc.getElementById("sourceNotice");
  assert.equal(notice.querySelectorAll("img").length, 0, "diagnostics text must not inject HTML");
});

// --------------------------------------------------------------------------
// choosing the store from Config
// --------------------------------------------------------------------------

test("the store dropdown shows what the last scan actually used", () => {
  const diag = h.sampleDiag();
  diag.source = { requested: "sessions", effective: "sessions",
                  debug_sessions: 0, chat_credit_first: "2026-06-26",
                  sessions_from_saved: 0 };
  const { document: doc } = boot({ diag, vscode: true });
  assert.equal(doc.getElementById("qsSource").value, "sessions");
});

test("all three stores are offered, so the automatic mode can be returned to", () => {
  const { document: doc } = boot({ vscode: true });
  const values = [...doc.getElementById("qsSource").options].map(o => o.value);
  assert.deepEqual(values, ["auto", "debug", "sessions"]);
});

test("choosing a store asks the extension to rescan with it", () => {
  const { document: doc, window: win } = boot({ vscode: true });
  const sel = doc.getElementById("qsSource");
  sel.value = "debug";
  sel.dispatchEvent(new win.Event("change", { bubbles: true }));
  const msg = win.__posted.find(m => m.type === "setSource");
  assert.ok(msg, "nothing was sent, so the choice would not have changed the data");
  assert.equal(msg.source, "debug");
});

test("without the extension the store cannot be changed, and says so", () => {
  const { document: doc } = boot();          // plain file:// dashboard
  const sel = doc.getElementById("qsSource");
  assert.equal(sel.disabled, true, "a control that cannot work must not look usable");
  assert.match(doc.getElementById("qsSourceNote").textContent, /--source/);
});

test("the store dropdown survives saving the rest of the config", async () => {
  // Saving redraws the quick-settings form from the report the page was built
  // from. The rescan the dropdown triggered has not landed yet, so re-reading
  // it there snaps the control back to the previous store while the numbers
  // beside it are already changing -- the disagreement it exists to prevent.
  const { window: win, document: doc } = boot({
    vscode: true, diag: withSource({ requested: "debug", effective: "debug", debug_sessions: 5 })
  });
  const sel = doc.getElementById("qsSource");
  sel.value = "sessions";
  sel.dispatchEvent(new win.Event("change", { bubbles: true }));
  assert.ok(win.__posted.some(m => m.type === "setSource" && m.source === "sessions"));

  doc.getElementById("qsApply").click();
  await tick(20);

  assert.equal(sel.value, "sessions",
               "saving reverted the store while the rescan for it was still running");
});

test("once the rescan lands the dropdown reports the run again", async () => {
  // The pending choice must not outlive the report it was waiting for, or a
  // scan that settled somewhere else would be hidden behind the reader's pick.
  const { window: win, document: doc } = boot({
    vscode: true, diag: withSource({ requested: "debug", effective: "debug", debug_sessions: 5 })
  });
  const sel = doc.getElementById("qsSource");
  sel.value = "sessions";
  sel.dispatchEvent(new win.Event("change", { bubbles: true }));

  win.postMessage({ type: "data", phase: "full", projects: h.sampleData(),
                    diag: withSource({ requested: "auto", effective: "sessions",
                                       debug_sessions: 0 }) }, "*");
  await tick(30);
  doc.getElementById("qsApply").click();
  await tick(20);

  assert.equal(sel.value, "auto", "the control still shows a choice the report did not use");
});

// --------------------------------------------------------------------------
// the permanent account of agent debug logging
// --------------------------------------------------------------------------

test("Diagnostics names the debug-log setting when nothing was written", () => {
  const { document: doc } = boot({ diag: withSource({
    effective: "sessions", debug_sessions: 0, chat_credit_first: "2026-06-26" }) });
  const panel = doc.getElementById("diagDebugLog");
  assert.match(panel.textContent, /not writing agent debug logs/i);
  assert.match(panel.textContent, /github\.copilot\.chat\.agentDebugLog\.fileLogging\.enabled/);
  assert.match(panel.textContent, /cannot be recovered/i,
               "enabling it must not read as a promise to recover the past");
});

test("Diagnostics still explains debug logging when it is switched on", () => {
  // A panel that only appears in the bad case leaves a reader who dismissed the
  // banner with nowhere to check, and an empty one reads as a rendering fault.
  const { document: doc } = boot({ diag: withSource({ debug_sessions: 7 }) });
  const panel = doc.getElementById("diagDebugLog");
  assert.match(panel.textContent, /logging is on/i);
  assert.match(panel.textContent, /7 sessions/);
  assert.match(panel.textContent, /rotate/i, "rotation is why an old day looks thin");
});

test("Diagnostics reports sessions taken from the saved copy instead", () => {
  const { document: doc } = boot({ diag: withSource({ debug_sessions: 40, sessions_from_saved: 6 }) });
  const panel = doc.getElementById("diagDebugLog");
  assert.match(panel.textContent, /6 of those sessions/);
  assert.match(panel.textContent, /turns rather than model calls/);
});

test("a sessions-only run says it did not look, rather than that there was nothing", () => {
  const diag = withSource({ requested: "sessions", effective: "sessions", debug_sessions: 0 });
  const { document: doc } = boot({ diag });
  const panel = doc.getElementById("diagDebugLog");
  assert.match(panel.textContent, /not read/i);
  assert.doesNotMatch(panel.textContent, /is not writing|disabled/i,
                      "a store that was excluded is not evidence that logging is off");
  assert.match(panel.textContent, /Automatic|request logs/,
               "a reader told nothing was read needs to know how to find out");
  assert.equal(doc.getElementById("logNotice").hidden, true,
               "offering to enable a setting that may already be on");
});

test("Diagnostics explains why the two stores report different totals", () => {
  // Switching the store moves every headline, and the largest gap -- requests --
  // is a change of unit rather than a change in usage. A reader who is not told
  // that reads the two runs as two different amounts of spend.
  const { document: doc } = boot();
  const panel = doc.getElementById("diagStores");
  assert.ok(panel, "there is no permanent account of the difference between the stores");
  assert.match(panel.textContent, /one model call/i);
  assert.match(panel.textContent, /one turn/i);
  assert.match(panel.textContent, /neither is a subset of the other/i,
               "neither store is the complete one, and neither total is the wrong one");
  assert.match(panel.textContent, /copilotCredits/,
               "the missing credit field is why the saved-session total is lower");
});
