// Unit tests for the pure dashboard helpers (web/js/00-lib.js).
//
// Run with:  node --test tests/js
//
// These are the pieces that decide what a number looks like, what a config file
// means and which rows are in scope -- the places a quiet mistake shows up as a
// wrong figure rather than a crash. No DOM, no browser, no dependencies.
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const lib = require(path.join(__dirname, "..", "..", "web", "js", "00-lib.js"));

test("esc neutralises markup so project names cannot inject HTML", () => {
  assert.equal(lib.esc("<script>x</script>"), "&lt;script&gt;x&lt;/script&gt;");
  assert.equal(lib.esc("a & b"), "a &amp; b");
  assert.equal(lib.esc("plain"), "plain");
  assert.equal(lib.esc(null), "null");
});

test("fmtK keeps large token counts inside their box", () => {
  assert.equal(lib.fmtK(999), "999");
  assert.equal(lib.fmtK(1500), "1.5K");
  assert.equal(lib.fmtK(2_400_000), "2.4M");
  assert.equal(lib.fmtK(3_210_000_000), "3.21B");
});

test("fmtK treats missing values as zero rather than NaN", () => {
  assert.equal(lib.fmtK(undefined), "0");
  assert.equal(lib.fmtK(null), "0");
});

test("usdFrom scales precision to the size of the amount", () => {
  assert.equal(lib.usdFrom(100, 0.01), "$1.00");
  assert.equal(lib.usdFrom(10, 0.01), "$0.100");
  assert.equal(lib.usdFrom(200000, 0.01), "$2,000");
});

test("usdFrom shows nothing spurious when no rate is configured", () => {
  assert.equal(lib.usdFrom(150000, 0), "$0.000");
  assert.equal(lib.usdFrom(150000, null), "$0.000");
});

test("normCfg fills in every default for an empty config", () => {
  const c = lib.normCfg({});
  assert.equal(c.since, null);
  assert.equal(c.autoRefreshMinutes, 0);
  assert.equal(c.cost.usdPerAiu, null);
  assert.deepEqual(c.exclude.projects, []);
});

test("normCfg survives garbage instead of blanking the dashboard", () => {
  for (const bad of [null, undefined, 42, "nope", []]) {
    const c = lib.normCfg(bad);
    assert.equal(c.since, null);
    assert.deepEqual(c.exclude.clients, []);
  }
});

test("normCfg rejects values that would silently mislead", () => {
  const c = lib.normCfg({
    since: 20260701,            // not a string
    cost: { usdPerAiu: -1 },    // a negative price is not a price
    budget: { monthlyAiu: 0 },  // zero budget means "no budget"
    autoRefreshMinutes: -5,
    exclude: { projects: ["ok", 7, null] }
  });
  assert.equal(c.since, null);
  assert.equal(c.cost.usdPerAiu, null);
  assert.equal(c.budget.monthlyAiu, null);
  assert.equal(c.autoRefreshMinutes, 0);
  assert.deepEqual(c.exclude.projects, ["ok"]);
});

test("normCfg keeps valid values untouched", () => {
  const c = lib.normCfg({ since: "2026-07-01", cost: { usdPerAiu: 0.01 },
                          budget: { monthlyAiu: 20000 }, autoRefreshMinutes: 5 });
  assert.equal(c.since, "2026-07-01");
  assert.equal(c.cost.usdPerAiu, 0.01);
  assert.equal(c.budget.monthlyAiu, 20000);
  assert.equal(c.autoRefreshMinutes, 5);
});

test("matchesAny excludes by substring and by prefix, case-insensitively", () => {
  assert.equal(lib.matchesAny("acme/Alpha", ["alpha"], []), true);
  assert.equal(lib.matchesAny("acme/Alpha", [], ["ACME/"]), true);
  assert.equal(lib.matchesAny("acme/Alpha", ["beta"], ["other"]), false);
});

test("matchesAny ignores empty patterns so a blank line excludes nothing", () => {
  assert.equal(lib.matchesAny("anything", [""], [""]), false);
  assert.equal(lib.matchesAny("anything", undefined, undefined), false);
});

test("aliasClients maps the names people actually type", () => {
  assert.deepEqual([...lib.aliasClients(["VS Code", "copilot cli", "Claude"])],
                   ["vs", "cli", "cla"]);
  assert.deepEqual([...lib.aliasClients(["  cli  "])], ["cli"]);
  assert.deepEqual([...lib.aliasClients(["nonsense"])], []);
});

test("clampToSpan keeps a chosen date inside the recorded range", () => {
  assert.equal(lib.clampToSpan("2026-05-05", "2026-01-01", "2026-12-31"), "2026-05-05");
  assert.equal(lib.clampToSpan("2025-01-01", "2026-01-01", "2026-12-31"), "2026-01-01");
  assert.equal(lib.clampToSpan("2027-01-01", "2026-01-01", "2026-12-31"), "2026-12-31");
  assert.equal(lib.clampToSpan("", "2026-01-01", "2026-12-31"), "2026-01-01");
});

test("addDays crosses month and year boundaries in UTC", () => {
  assert.equal(lib.addDays("2026-01-31", 1), "2026-02-01");
  assert.equal(lib.addDays("2026-03-01", -1), "2026-02-28");
  assert.equal(lib.addDays("2026-12-31", 1), "2027-01-01");
});

const client = {
  by_day: {
    "2026-01-01": { sessions: 1, requests: 2, in: 10, out: 3, aiu: 1.5 },
    "2026-02-01": { sessions: 2, requests: 5, in: 20, out: 4, aiu: 2.5 },
    "2026-03-01": { sessions: 1, requests: 1, in: 5, out: 1, aiu: 0.5 }
  }
};

test("windowSum counts only the days inside the range, inclusive", () => {
  const w = lib.windowSum(client, "2026-01-01", "2026-02-01");
  assert.deepEqual(w, { sessions: 3, requests: 7, in: 30, out: 7, aiu: 4 });
});

test("windowSum returns zeroes for a range with no activity", () => {
  assert.deepEqual(lib.windowSum(client, "2025-01-01", "2025-12-31"),
                   { sessions: 0, requests: 0, in: 0, out: 0, aiu: 0 });
});

test("sessTotal is lifetime, ignoring any range", () => {
  assert.equal(lib.sessTotal(client), 4);
  assert.equal(lib.sessTotal({ by_day: {} }), 0);
});

test("calBucket puts a silent day in the empty bucket", () => {
  assert.equal(lib.calBucket(0, 1, 5, 10), 0);
});

test("calBucket rises through the quartiles", () => {
  assert.equal(lib.calBucket(1, 1, 5, 10), 1);
  assert.equal(lib.calBucket(5, 1, 5, 10), 2);
  assert.equal(lib.calBucket(10, 1, 5, 10), 3);
  assert.equal(lib.calBucket(99, 1, 5, 10), 4);
});
