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
  assert.match(doc.getElementById("dailyChart").textContent, /No AIU in range/);
});

test("the date inputs open on the full recorded span", () => {
  const { document: doc } = boot();
  assert.equal(doc.getElementById("dFrom").value, "2026-07-01");
  assert.equal(doc.getElementById("dTo").value, "2026-07-02");
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
  cli.by_sdm["quiet1\u001f2026-07-02\u001f(no token data)"] = 1;
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
  vs.by_sdm["vs2\u001f2026-07-02\u001fgpt-y"] = 1;
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
