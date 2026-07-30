// Unit tests for the pure cores extracted out of the render functions.
//
// These are the calculations behind the pictures: which slices a donut gets,
// what a projection actually projects from, and which agent is called the
// biggest spender. They used to be buried inside functions that could only be
// exercised by opening a browser.
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const lib = require(path.join(__dirname, "..", "..", "web", "js", "00-lib.js"));

const PALETTE = ["c0", "c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"];
const OTHER = "#adb5bd";

// --------------------------------------------------------------------------
// pie geometry
// --------------------------------------------------------------------------

test("arcPath draws a wedge back to the centre so slices close", () => {
  const d = lib.arcPath(80, 80, 72, 0, Math.PI / 2);
  assert.match(d, /^M 80 80 L /);
  assert.match(d, /Z$/);
});

test("arcPath flags the large-arc case only past half a turn", () => {
  assert.match(lib.arcPath(0, 0, 10, 0, Math.PI * 1.5), / 0 1 1 /);
  assert.match(lib.arcPath(0, 0, 10, 0, Math.PI * 0.5), / 0 0 1 /);
});

test("pieSegments orders slices biggest first", () => {
  const { segs } = lib.pieSegments(
    [{ name: "a", value: 1 }, { name: "b", value: 5 }, { name: "c", value: 3 }],
    PALETTE, OTHER, 8);
  assert.deepEqual(segs.map(s => s.name), ["b", "c", "a"]);
});

test("pieSegments collapses the long tail into one Other wedge", () => {
  const items = Array.from({ length: 12 }, (_, i) => ({ name: "p" + i, value: 12 - i }));
  const { segs, total } = lib.pieSegments(items, PALETTE, OTHER, 8);
  assert.equal(segs.length, 9);                  // 8 named + Other
  assert.equal(segs[8].name, "Other (4)");
  assert.equal(segs[8].color, OTHER);
  assert.equal(segs.reduce((s, x) => s + x.value, 0), total);
});

test("pieSegments leaves a short list untouched", () => {
  const { segs } = lib.pieSegments(
    [{ name: "a", value: 2 }, { name: "b", value: 1 }], PALETTE, OTHER, 8);
  assert.equal(segs.length, 2);
  assert.ok(!segs.some(s => s.name.startsWith("Other")));
});

test("pieSegments percentages sum to a whole circle", () => {
  const { segs } = lib.pieSegments(
    [{ name: "a", value: 1 }, { name: "b", value: 2 }, { name: "c", value: 1 }],
    PALETTE, OTHER, 8);
  assert.equal(segs.reduce((s, x) => s + x.pct, 0).toFixed(6), "100.000000");
});

test("pieSegments drops slices of nothing rather than rendering slivers", () => {
  const { segs } = lib.pieSegments(
    [{ name: "a", value: 5 }, { name: "zero", value: 0 }, { name: "neg", value: -3 }],
    PALETTE, OTHER, 8);
  assert.deepEqual(segs.map(s => s.name), ["a"]);
});

test("pieSegments reports an empty total for no data", () => {
  assert.deepEqual(lib.pieSegments([], PALETTE, OTHER, 8), { total: 0, segs: [] });
  assert.deepEqual(lib.pieSegments(null, PALETTE, OTHER, 8), { total: 0, segs: [] });
});

test("pieSegments recycles the palette rather than running out of colours", () => {
  const items = Array.from({ length: 8 }, (_, i) => ({ name: "p" + i, value: 8 - i }));
  const short = ["x", "y"];
  const { segs } = lib.pieSegments(items, short, OTHER, 8);
  assert.deepEqual(segs.map(s => s.color), ["x", "y", "x", "y", "x", "y", "x", "y"]);
});

// --------------------------------------------------------------------------
// forecast
// --------------------------------------------------------------------------

function daysOf(startIso, n, perDay) {
  const out = {};
  for (let i = 0; i < n; i++) out[lib.addDays(startIso, i)] = perDay;
  return out;
}

test("forecastFrom returns nothing to project from when there is no usage", () => {
  assert.equal(lib.forecastFrom({}, new Date(Date.UTC(2026, 6, 15))), null);
  assert.equal(lib.forecastFrom({ "2026-07-01": 0 }, new Date(Date.UTC(2026, 6, 15))), null);
});

test("forecastFrom averages the whole range when there is under 28 days of it", () => {
  const f = lib.forecastFrom(daysOf("2026-07-01", 10, 100), new Date(Date.UTC(2026, 6, 10)));
  assert.equal(f.rateLabel, "range average");
  assert.equal(f.spanDays, 10);
  assert.equal(f.consumed, 1000);
  assert.equal(f.rate, 100);
});

test("forecastFrom switches to a trailing 28-day average once the span allows", () => {
  const f = lib.forecastFrom(daysOf("2026-06-01", 40, 10), new Date(Date.UTC(2026, 6, 10)));
  assert.equal(f.rateLabel, "trailing 28-day avg");
  assert.equal(f.spanDays, 40);
  assert.equal(f.rate, 10);            // 28 days x 10 / 28
});

test("forecastFrom counts only the current month as spent-to-date", () => {
  const daily = { "2026-06-20": 500, "2026-07-01": 100, "2026-07-02": 100 };
  const f = lib.forecastFrom(daily, new Date(Date.UTC(2026, 6, 3)));
  assert.equal(f.consumed, 700);
  assert.equal(f.mtd, 200);
});

test("forecastFrom projects the rest of the month from the daily rate", () => {
  const f = lib.forecastFrom(daysOf("2026-07-01", 10, 100), new Date(Date.UTC(2026, 6, 10)));
  assert.equal(f.daysRemaining, 21);   // July has 31 days
  assert.equal(f.projMonth, 1000 + 100 * 21);
});

test("forecastFrom projects nothing further on the last day of the month", () => {
  const f = lib.forecastFrom(daysOf("2026-07-01", 10, 100), new Date(Date.UTC(2026, 6, 31)));
  assert.equal(f.daysRemaining, 0);
  assert.equal(f.projMonth, f.mtd);
});

test("forecastFrom handles February in a leap year", () => {
  const f = lib.forecastFrom({ "2028-02-01": 10 }, new Date(Date.UTC(2028, 1, 10)));
  assert.equal(f.daysRemaining, 19);   // 29 - 10
});

test("forecastFrom scales each horizon from the same rate", () => {
  const f = lib.forecastFrom(daysOf("2026-07-01", 10, 100), new Date(Date.UTC(2026, 6, 10)));
  const byLabel = Object.fromEntries(f.horizons.map(([l, v]) => [l, v]));
  assert.equal(byLabel["Next 3 months"], 100 * 90);
  assert.equal(byLabel["Next 6 months"], 100 * 180);
  assert.equal(byLabel["End of month"], f.projMonth);
});

test("forecastFrom counts a single active day as a one-day span", () => {
  const f = lib.forecastFrom({ "2026-07-05": 42 }, new Date(Date.UTC(2026, 6, 5)));
  assert.equal(f.spanDays, 1);
  assert.equal(f.activeDays, 1);
  assert.equal(f.rate, 42);
});

// --------------------------------------------------------------------------
// agent ranking
// --------------------------------------------------------------------------

const AGENTS = {
  "GitHub Copilot Chat": { req: 1000, aiu: 9000, in: 10, out: 2 },
  "Copilot CLI": { req: 100, aiu: 500, in: 5, out: 1 },
  "Claude Code": { req: 2000, aiu: 0, in: 9, out: 3 },      // real requests, no credits
  "Researcher Subagent": { req: 50, aiu: 800, in: 4, out: 1 },
  "Plan Validator": { req: 10, aiu: 300, in: 2, out: 1 },
  "One Shot": { req: 1, aiu: 200, in: 1, out: 1 }            // below the sample floor
};

test("rankAgents orders by credits, most expensive first", () => {
  const items = lib.rankAgents(AGENTS);
  assert.deepEqual(items.slice(0, 3).map(i => i.name),
                   ["GitHub Copilot Chat", "Researcher Subagent", "Copilot CLI"]);
});

test("rankAgents keeps zero-credit agents with their real request counts", () => {
  const claude = lib.rankAgents(AGENTS).find(i => i.name === "Claude Code");
  assert.equal(claude.aiu, 0);
  assert.equal(claude.req, 2000);
});

test("rankAgents breaks credit ties on request count", () => {
  const items = lib.rankAgents({ a: { req: 1, aiu: 5 }, b: { req: 9, aiu: 5 } });
  assert.deepEqual(items.map(i => i.name), ["b", "a"]);
});

test("rankAgents computes cost per request, and zero requests do not divide", () => {
  const items = lib.rankAgents({ busy: { req: 4, aiu: 8 }, idle: { req: 0, aiu: 0 } });
  assert.equal(items[0].per, 2);
  assert.deepEqual(items.map(i => i.name), ["busy"]);   // idle has neither req nor aiu
});

test("rankAgents honours the exclusion filter", () => {
  const items = lib.rankAgents(AGENTS, n => n === "GitHub Copilot Chat");
  assert.ok(!items.some(i => i.name === "GitHub Copilot Chat"));
});

test("rankAgents copes with no agents at all", () => {
  assert.deepEqual(lib.rankAgents({}), []);
  assert.deepEqual(lib.rankAgents(null), []);
});

test("splitAgents separates harnesses from subagents", () => {
  const { base, subs } = lib.splitAgents(lib.rankAgents(AGENTS));
  assert.deepEqual(base.map(i => i.name).sort(),
                   ["Claude Code", "Copilot CLI", "GitHub Copilot Chat"]);
  assert.deepEqual(subs.map(i => i.name).sort(),
                   ["One Shot", "Plan Validator", "Researcher Subagent"]);
});

test("priciestPerRequest ignores agents below the sample floor", () => {
  const subs = lib.splitAgents(lib.rankAgents(AGENTS)).subs;
  // One Shot is 200 AIU/req but on a single call; Plan Validator is the honest answer
  assert.equal(lib.priciestPerRequest(subs, 5).name, "Plan Validator");
});

test("priciestPerRequest returns null when nothing clears the floor", () => {
  assert.equal(lib.priciestPerRequest([{ name: "x", req: 1, per: 99 }], 5), null);
  assert.equal(lib.priciestPerRequest([], 5), null);
  assert.equal(lib.priciestPerRequest(null, 5), null);
});
