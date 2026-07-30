// Unit tests for the "does this project tell us anything about spend?" gate
// and the two config flags that control the default view.
//
// Run with:  node --test "tests/js/*.test.js"
//
// The gate decides what a first-time reader sees, so the edge it has to get
// right is the difference between a project that is genuinely idle and one that
// simply had its token payloads trimmed away.
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const lib = require(path.join(__dirname, "..", "..", "web", "js", "00-lib.js"));

// Build a project whose clients carry exactly the day buckets given.
function proj(clients) {
  const empty = () => ({ by_day: {} });
  const p = { name: "p", vscode: empty(), cli: empty(), claude: empty() };
  for (const [client, days] of Object.entries(clients)) {
    for (const [date, b] of Object.entries(days)) {
      p[client].by_day[date] = Object.assign({ sessions: 0, requests: 0, in: 0, out: 0, aiu: 0 }, b);
    }
  }
  return p;
}

test("a project with recorded credits qualifies", () => {
  assert.equal(lib.hasRecordedUsage(proj({ vscode: { "2026-01-01": { requests: 3, aiu: 12.5 } } })), true);
});

test("tokens alone qualify, even with no credits", () => {
  // Claude Code never reports credits, but its token counts are real.
  assert.equal(lib.hasRecordedUsage(proj({ claude: { "2026-01-01": { requests: 2, in: 900, out: 40 } } })), true);
  assert.equal(lib.hasRecordedUsage(proj({ cli: { "2026-01-01": { out: 1 } } })), true);
});

test("requests with no token payload do not qualify", () => {
  // The pre-telemetry CLI turns and the trimmed chatSession activity floors:
  // real calls, but they say nothing about how much was spent.
  const p = proj({ cli: { "2026-01-01": { requests: 40, sessions: 3 } } });
  assert.equal(lib.hasRecordedUsage(p), false);
});

test("sessions that never reached a model do not qualify", () => {
  assert.equal(lib.hasRecordedUsage(proj({ vscode: { "2026-01-01": { sessions: 5 } } })), false);
  assert.equal(lib.hasRecordedUsage(proj({})), false);
});

test("one qualifying day anywhere is enough", () => {
  const p = proj({
    vscode: { "2026-01-01": { requests: 9 }, "2026-01-02": { requests: 1, aiu: 0.4 } },
    cli: { "2026-01-01": { requests: 100 } }
  });
  assert.equal(lib.hasRecordedUsage(p), true);
});

test("a malformed project is treated as not qualifying rather than throwing", () => {
  // This runs against whatever the extractor last wrote; a shape surprise must
  // demote a row, never blank the dashboard.
  assert.equal(lib.hasRecordedUsage(null), false);
  assert.equal(lib.hasRecordedUsage({}), false);
  assert.equal(lib.hasRecordedUsage({ vscode: null, cli: {}, claude: { by_day: null } }), false);
});

test("both new flags default to on", () => {
  const c = lib.normCfg({});
  assert.equal(c.hideEmptyProjects, true);
  assert.equal(c.show.diagnostics, true);
});

test("both new flags can be turned off", () => {
  const c = lib.normCfg({ hideEmptyProjects: false, show: { diagnostics: false } });
  assert.equal(c.hideEmptyProjects, false);
  assert.equal(c.show.diagnostics, false);
});

test("only a real boolean flips a flag, so a typo cannot half-hide the UI", () => {
  for (const bad of ["false", 0, null, [], {}]) {
    const c = lib.normCfg({ hideEmptyProjects: bad, show: { diagnostics: bad } });
    assert.equal(c.hideEmptyProjects, true, `hideEmptyProjects: ${JSON.stringify(bad)}`);
    assert.equal(c.show.diagnostics, true, `show.diagnostics: ${JSON.stringify(bad)}`);
  }
  assert.equal(lib.normCfg({ show: "nope" }).show.diagnostics, true);
});

test("the verdict is lifetime, so narrowing the dates cannot reshuffle the sidebar", () => {
  // INV-18. A sidebar that reorders itself while you drag the calendar is worse
  // than one that stays put, so the gate deliberately ignores the date range.
  // Nothing about this project falls inside July, yet it still qualifies.
  const p = proj({ vscode: { "2026-01-01": { requests: 3, aiu: 12.5 } } });
  assert.equal(lib.hasRecordedUsage(p), true);

  // The gate takes no range argument at all -- the strongest form the rule can
  // take, since there is no window for a caller to accidentally pass.
  assert.equal(lib.hasRecordedUsage.length, 1);
});
