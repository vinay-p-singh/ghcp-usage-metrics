const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");
const { sourceNotice, debugLogSetup, calendarWarningPolicy } = require("../../web/js/00-lib.js");

test("a normal run says nothing", () => {
  assert.equal(sourceNotice({ requested: "auto", effective: "auto", debug_sessions: 12 }), null);
});

test("a missing record says nothing rather than throwing", () => {
  assert.equal(sourceNotice(null), null);
  assert.equal(sourceNotice(undefined), null);
  assert.equal(sourceNotice({}), null);
});

test("falling back explains why the totals are lower than a bill", () => {
  const n = sourceNotice({
    requested: "auto", effective: "sessions",
    debug_sessions: 0, chat_credit_first: "2026-06-26"
  });
  assert.ok(n, "a fallback that is not announced reads as missing data");
  assert.match(n.title, /saved session/i);
  // The reader has to learn three things: which store, that it is partial, and
  // the date before which no credit figure exists at all.
  assert.match(n.body, /request log/i);
  assert.match(n.body, /2026-06-26/);
  assert.match(n.body, /most recent/i);
  assert.equal(n.level, "warn");
});

test("a fallback with no credit-bearing session does not invent a date", () => {
  const n = sourceNotice({
    requested: "auto", effective: "sessions",
    debug_sessions: 0, chat_credit_first: null
  });
  assert.ok(n);
  assert.doesNotMatch(n.body, /\d{4}-\d{2}-\d{2}/);
  assert.match(n.body, /no AI credits/i);
});

test("choosing a store deliberately is reported as a choice, not a fault", () => {
  const chosen = sourceNotice({
    requested: "sessions", effective: "sessions",
    debug_sessions: 4, chat_credit_first: "2026-06-26"
  });
  assert.equal(chosen.level, "info");
  assert.match(chosen.body, /you asked/i);

  const dbg = sourceNotice({ requested: "debug", effective: "debug", debug_sessions: 4 });
  assert.equal(dbg.level, "info");
  assert.match(dbg.title, /request log/i);
});

test("the notice never claims the numbers are complete", () => {
  for (const eff of ["sessions", "debug"]) {
    const n = sourceNotice({ requested: eff, effective: eff, debug_sessions: 4,
                             chat_credit_first: "2026-06-26" });
    assert.doesNotMatch(n.body, /complete|accurate|total spend/i);
  }
});

const { sourceChoice } = require("../../web/js/00-lib.js");

test("the control reports the store the data was actually built from", () => {
  assert.equal(sourceChoice({ source: { requested: "sessions" } }), "sessions");
  assert.equal(sourceChoice({ source: { requested: "debug" } }), "debug");
  assert.equal(sourceChoice({ source: { requested: "auto" } }), "auto");
});

test("an unknown or missing record falls back to auto rather than guessing", () => {
  assert.equal(sourceChoice(null), "auto");
  assert.equal(sourceChoice({}), "auto");
  assert.equal(sourceChoice({ source: {} }), "auto");
  assert.equal(sourceChoice({ source: { requested: "nonsense" } }), "auto");
});

test("saved-session reports use one calendar coverage note instead of warning every day", () => {
  const policy = calendarWarningPolicy({
    requested: "sessions", effective: "sessions", chat_credit_first: "2026-06-26"
  });
  assert.equal(policy.perDay, false);
  assert.match(policy.note, /2026-06-26/);
  assert.match(policy.note, /saved session/i);
});

test("request-log and merged reports keep exceptional per-day warnings", () => {
  assert.equal(calendarWarningPolicy({ effective: "debug" }).perDay, true);
  assert.equal(calendarWarningPolicy({ effective: "auto" }).perDay, true);
  assert.equal(calendarWarningPolicy(null).perDay, true);
});

test("missing agent debug logs produce exact enablement guidance", () => {
  const setup = debugLogSetup({ debug_sessions: 0 });
  assert.ok(setup, "a sessions-only report must explain how to improve future coverage");
  assert.match(setup.body, /github\.copilot\.chat\.agentDebugLog\.fileLogging\.enabled/);
  assert.match(setup.body, /reload/i);
  assert.match(setup.body, /new chat/i);
});

test("an absent source record does not claim logging is disabled", () => {
  assert.equal(debugLogSetup(null), null);
  assert.equal(debugLogSetup({}), null);
  assert.equal(debugLogSetup({ debug_sessions: 2 }), null);
});

test("a sessions-only run never reports on logs it was told not to read", () => {
  // The count is zero because the store was excluded, not because Copilot
  // wrote nothing. Reading it as evidence accuses the machine of a setting it
  // may well have on, and offers to enable what is already enabled.
  assert.equal(debugLogSetup({ requested: "sessions", effective: "sessions",
                               debug_sessions: 0 }), null);
  // Falling back to saved sessions after looking IS evidence, and still counts.
  assert.ok(debugLogSetup({ requested: "auto", effective: "sessions", debug_sessions: 0 }));
});

test("opening the raw web source points to the generated dashboard", () => {
  const html = fs.readFileSync(path.join(__dirname, "..", "..", "web", "dashboard.html"), "utf8");
  const dom = new JSDOM(html, { runScripts: "dangerously", url: "file:///web/dashboard.html" });
  const notice = dom.window.document.getElementById("rawSourceNotice");
  assert.ok(notice, "the raw assembly source still looks like a broken dashboard");
  assert.notEqual(notice.style.display, "none");
  assert.match(notice.textContent, /generated dashboard/i);
  assert.equal(notice.querySelector("a").getAttribute("href"), "../out/dashboard.html");
});
