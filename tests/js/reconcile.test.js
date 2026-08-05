// INV-35. The reconciliation card compares this machine's recorded credits
// against the figure GitHub reports for the same billing cycle.
//
// Run with:  node --test "tests/js/*.test.js"
//
// The rule that matters is restraint: the card reports a difference and never
// closes it. A tool that quietly scaled its own totals up to meet an external
// number would look accurate and be worthless -- the gap is the finding.
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const lib = require(path.join(__dirname, "..", "..", "web", "js", "00-lib.js"));

function proj(days) {
  const empty = () => ({ by_day: {} });
  const p = { name: "p", vscode: empty(), cli: empty(), claude: empty() };
  for (const [date, b] of Object.entries(days)) {
    p.vscode.by_day[date] = Object.assign(
      { sessions: 0, requests: 0, in: 0, out: 0, aiu: 0 }, b);
  }
  return p;
}

const CYCLE = { cycleStart: "2026-07-31", cycleEnd: "2026-08-30", officialAiu: 1000 };
const DATA = [proj({
  "2026-07-30": { requests: 5, aiu: 500 },   // the day before the cycle opens
  "2026-07-31": { requests: 10, aiu: 300 },
  "2026-08-04": { requests: 20, aiu: 600 },
  "2026-08-31": { requests: 7, aiu: 700 }    // the day after it closes
})];

test("only the days inside the cycle are counted", () => {
  const ours = lib.recordedInCycle(DATA, CYCLE.cycleStart, CYCLE.cycleEnd);
  assert.equal(ours.aiu, 900, "days outside the cycle leaked into the total");
  assert.equal(ours.requests, 30);
});

test("the gap is reported, and our own total is left exactly as recorded", () => {
  const ours = lib.recordedInCycle(DATA, CYCLE.cycleStart, CYCLE.cycleEnd);
  const st = lib.reconcileState(CYCLE, ours, "2026-08-05");
  assert.equal(st.ours, 900, "a recorded total was adjusted to meet GitHub's figure");
  assert.equal(st.official, 1000);
  assert.equal(st.gap, 100);
  assert.equal(Math.round(st.coverage * 1000) / 10, 90);
  assert.equal(st.overcount, false);
});

test("recording more than GitHub billed is flagged rather than hidden", () => {
  // Ours can only ever be a subset of what GitHub bills, so exceeding it means
  // something here is double-counted -- a bug, not a gap to explain away.
  const st = lib.reconcileState(CYCLE, { aiu: 1200, requests: 40 }, "2026-08-05");
  assert.equal(st.overcount, true);
  assert.equal(st.gap, -200);
});

test("a cycle that has closed reports itself stale instead of comparing", () => {
  const fresh = lib.reconcileState(CYCLE, { aiu: 900, requests: 30 }, "2026-08-05");
  const past = lib.reconcileState(CYCLE, { aiu: 900, requests: 30 }, "2026-09-02");
  const early = lib.reconcileState(CYCLE, { aiu: 900, requests: 30 }, "2026-07-01");
  assert.equal(fresh.stale, false);
  assert.equal(past.stale, true, "an expired cycle silently compared against a new one");
  assert.equal(early.stale, true);
});

test("nothing is claimed until all three inputs are given", () => {
  const ours = { aiu: 900, requests: 30 };
  assert.equal(lib.reconcileState({}, ours, "2026-08-05").ready, false);
  assert.equal(lib.reconcileState(
    { cycleStart: "2026-07-31", cycleEnd: "2026-08-30" }, ours, "2026-08-05").ready, false);
  assert.equal(lib.reconcileState(
    { cycleStart: "2026-07-31", officialAiu: 1000 }, ours, "2026-08-05").ready, false);
});

test("the config survives a round trip through normCfg", () => {
  const c = lib.normCfg({ reconcile: CYCLE });
  assert.deepEqual(c.reconcile, CYCLE);
});

test("a malformed reconcile block becomes empty rather than throwing", () => {
  // This parses hand-edited JSON, so a typo must not blank the dashboard.
  for (const bad of [null, "nope", { officialAiu: -5 }, { officialAiu: "1000" }]) {
    const c = lib.normCfg({ reconcile: bad });
    assert.equal(c.reconcile.officialAiu, null);
    assert.equal(lib.reconcileState(c.reconcile, { aiu: 1, requests: 1 }, "2026-08-05").ready, false);
  }
});

test("today is read in UTC, matching the clock the buckets use", () => {
  assert.match(lib.todayIso(), /^\d{4}-\d{2}-\d{2}$/);
  assert.equal(lib.todayIso(), new Date().toISOString().slice(0, 10));
});
