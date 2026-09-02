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

// ---- credit-coverage floor -------------------------------------------------
// Credit telemetry started at different times per harness. Opening on the full
// span silently averages complete months together with months that recorded
// requests and no credits, which reads as "my spend fell" when nothing of the
// sort happened.

test("the view opens at the floor's month when earlier data predates credit reporting", () => {
  const diag = { credit_floor: { floor: "2026-07-09" } };
  assert.equal(lib.creditFloorStart(diag, "2026-01-08", "", true), "2026-07-01");
});

test("an explicit configured start always wins over the floor", () => {
  const diag = { credit_floor: { floor: "2026-07-09" } };
  assert.equal(lib.creditFloorStart(diag, "2026-01-08", "2026-02-01", true),
               "2026-02-01");
});

test("turning the floor off opens on everything recorded", () => {
  const diag = { credit_floor: { floor: "2026-07-09" } };
  assert.equal(lib.creditFloorStart(diag, "2026-01-08", "", false), "2026-01-08");
});

test("a floor earlier than the data never pushes the start backwards", () => {
  const diag = { credit_floor: { floor: "2026-01-01" } };
  assert.equal(lib.creditFloorStart(diag, "2026-05-01", "", true), "2026-05-01");
});

test("no floor at all leaves the start alone rather than guessing one", () => {
  assert.equal(lib.creditFloorStart({}, "2026-05-01", "", true), "2026-05-01");
  assert.equal(lib.creditFloorStart(null, "2026-05-01", "", true), "2026-05-01");
});

// ---- where the view opens --------------------------------------------------
// Credit reporting switched on part-way through a month, so the computed floor
// lands mid-month. Opening there would show half a month with no explanation.
// Open on the whole month instead and flag the thin days inside it.

test("the start rounds back to the beginning of the month the floor falls in", () => {
  // Credit reporting switched on mid-month. Opening on the 9th would cut the
  // month in half for no reason a reader could see; opening on the 1st gives a
  // whole month, and the days inside it that are thin get flagged instead.
  const diag = { credit_floor: { floor: "2026-07-09" } };
  assert.equal(lib.creditFloorStart(diag, "2026-01-08", "", true), "2026-07-01");
});

test("rounding back never reaches past the earliest data we hold", () => {
  const diag = { credit_floor: { floor: "2026-07-09" } };
  assert.equal(lib.creditFloorStart(diag, "2026-07-05", "", true), "2026-07-05");
});

test("a floor already on the first of a month is left alone", () => {
  const diag = { credit_floor: { floor: "2026-07-01" } };
  assert.equal(lib.creditFloorStart(diag, "2026-01-08", "", true), "2026-07-01");
});

// ---- flagging thin days ----------------------------------------------------
// Inside the opened range some days are still incomplete. They stay visible and
// get a marker, because removing them would be the same hiding the floor was
// meant to avoid.

test("a day with requests but no credits at all is flagged", () => {
  const w = lib.dayWarning({ requests: 40, aiu: 0, noToken: 0 });
  assert.ok(w, "a whole day of uncredited requests is the clearest warning sign");
  assert.match(w, /credit/i);
});

test("a day where some requests carry no token payload is flagged", () => {
  const w = lib.dayWarning({ requests: 100, aiu: 500, noToken: 12 });
  assert.match(w, /12 of 100/);
});

test("a fully recorded day is not flagged", () => {
  assert.equal(lib.dayWarning({ requests: 100, aiu: 500, noToken: 0 }), null);
});

test("a day with no requests is not flagged as a problem", () => {
  assert.equal(lib.dayWarning({ requests: 0, aiu: 0, noToken: 0 }), null);
});

test("credits missing outranks a partial token payload in the message", () => {
  const w = lib.dayWarning({ requests: 40, aiu: 0, noToken: 40 });
  assert.match(w, /credit/i, "the bigger problem is the one worth naming first");
});

test("a trivial share of token-less requests is not worth a warning", () => {
  // A marker that fires on almost every day is wallpaper. Measured on real
  // data: without a threshold this lit up 21 of 27 days, most of them a single
  // request in several hundred.
  assert.equal(lib.dayWarning({ requests: 345, aiu: 6723, noToken: 1 }), null);
  assert.equal(lib.dayWarning({ requests: 100, aiu: 500, noToken: 4 }), null);
});

test("a material share of token-less requests is flagged", () => {
  assert.ok(lib.dayWarning({ requests: 100, aiu: 500, noToken: 6 }));
  assert.ok(lib.dayWarning({ requests: 223, aiu: 3942, noToken: 44 }));
});

test("missing credits are flagged however small the day", () => {
  assert.ok(lib.dayWarning({ requests: 9, aiu: 0, noToken: 0 }),
            "a day with no credits at all is always worth saying");
});

// ---- naming the cause ------------------------------------------------------
// "Something is missing" invites a reader to distrust every figure on the page.
// The harness that stopped writing figures down is knowable, so it is named.

test("the warning names the harness responsible and why", () => {
  const w = lib.dayWarning({ requests: 494, aiu: 16428, noToken: 465,
                             noTokenBy: { cli: 463, vscode: 2 } });
  assert.match(w, /Copilot CLI/, "a reader cannot act on an unattributed warning");
  assert.match(w, /when a session closes/, "the reason, not just the culprit");
});

test("a mixed day says it is mixed rather than blaming one harness", () => {
  const w = lib.dayWarning({ requests: 100, aiu: 500, noToken: 30,
                             noTokenBy: { cli: 20, vscode: 10 } });
  assert.match(w, /Mostly Copilot CLI \(20 of 30\)/);
});

test("a single-harness day is not padded with a share it does not need", () => {
  const w = lib.dayWarning({ requests: 100, aiu: 500, noToken: 30,
                             noTokenBy: { vscode: 30 } });
  assert.match(w, /VS Code: /);
  assert.doesNotMatch(w, /Mostly/);
});

test("a day with no credits at all still names its cause", () => {
  const w = lib.dayWarning({ requests: 12, aiu: 0, noToken: 12,
                             noTokenBy: { cli: 11, vscode: 1 } });
  assert.match(w, /credit/i);
  assert.match(w, /Copilot CLI/);
});

test("a warning with no harness breakdown still reads as a sentence", () => {
  // The breakdown is optional: older reports and the calendar's own flag test
  // pass only the totals, and a dangling colon would be worse than no cause.
  const w = lib.dayWarning({ requests: 100, aiu: 500, noToken: 12 });
  assert.match(w, /whole story\.$/);
});

test("an empty breakdown names nothing rather than guessing", () => {
  const w = lib.dayWarning({ requests: 100, aiu: 500, noToken: 12, noTokenBy: {} });
  assert.match(w, /whole story\.$/);
});
