// Unit tests for the date x model dimension helpers (web/js/00-lib.js).
//
// Run with:  node --test "tests/js/*.test.js"
//
// These two functions read the same bucket from opposite directions: one asks
// "what happened each day, ignoring the models I excluded", the other asks
// "what did each model cost inside this date range". Between them they are why
// a model filter can re-scope the whole dashboard.
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const lib = require(path.join(__dirname, "..", "..", "web", "js", "00-lib.js"));
const SEP = lib.DIM_SEP;

const B = (o) => Object.assign({ requests: 0, in: 0, out: 0, aiu: 0 }, o);

const client = {
  by_day: {
    "2026-07-01": { sessions: 2 },
    "2026-07-02": { sessions: 1 },
    "2026-07-03": { sessions: 1 }
  },
  by_dm: {
    [`2026-07-01${SEP}gpt-x`]: B({ requests: 10, in: 1000, out: 100, aiu: 50 }),
    [`2026-07-01${SEP}gpt-y`]: B({ requests: 2, in: 200, out: 20, aiu: 8 }),
    [`2026-07-02${SEP}gpt-x`]: B({ requests: 5, in: 500, out: 50, aiu: 25 }),
    [`2026-07-03${SEP}gpt-y`]: B({ requests: 1, in: 100, out: 10, aiu: 4 })
  },
  by_sdm: {
    [`s1${SEP}2026-07-01${SEP}gpt-x`]: 1,
    [`s1${SEP}2026-07-01${SEP}gpt-y`]: 1,
    [`s1${SEP}2026-07-02${SEP}gpt-y`]: 1,
    [`s2${SEP}2026-07-02${SEP}gpt-x`]: 1,
    [`s3${SEP}2026-07-03${SEP}(no token data)`]: 1
  }
};

test("no exclusions means no work — callers stay on the cheaper path", () => {
  assert.equal(lib.dayTotalsByModel(client, null), null);
  assert.equal(lib.dayTotalsByModel(client, new Set()), null);
});

test("an excluded model is removed from every day it appears on", () => {
  const t = lib.dayTotalsByModel(client, new Set(["gpt-y"]));
  assert.deepEqual(t["2026-07-01"], { requests: 10, in: 1000, out: 100, aiu: 50 });
  assert.deepEqual(t["2026-07-02"], { requests: 5, in: 500, out: 50, aiu: 25 });
  assert.equal(t["2026-07-03"], undefined, "a day left with nothing should not appear");
});

test("excluding everything leaves nothing, rather than silently leaving totals alone", () => {
  const t = lib.dayTotalsByModel(client, new Set(["gpt-x", "gpt-y"]));
  assert.deepEqual(t, {});
});

test("days that mix models keep only the kept share", () => {
  const t = lib.dayTotalsByModel(client, new Set(["gpt-x"]));
  assert.deepEqual(t["2026-07-01"], { requests: 2, in: 200, out: 20, aiu: 8 });
});

test("a malformed key is skipped rather than corrupting a day", () => {
  const messy = { by_dm: Object.assign({ "no-separator-here": B({ aiu: 999 }) }, client.by_dm) };
  const t = lib.dayTotalsByModel(messy, new Set(["gpt-y"]));
  const total = Object.values(t).reduce((s, b) => s + b.aiu, 0);
  assert.equal(total, 75);
});

test("a project with no by_dm yields nothing instead of throwing", () => {
  assert.deepEqual(lib.dayTotalsByModel({}, new Set(["x"])), {});
  assert.deepEqual(lib.dayTotalsByModel(null, new Set(["x"])), {});
});

test("model totals follow the date range", () => {
  const all = lib.modelTotalsIn(client, "2026-07-01", "2026-07-03");
  assert.deepEqual(all["gpt-x"], { req: 15, in: 1500, out: 150, aiu: 75 });
  assert.deepEqual(all["gpt-y"], { req: 3, in: 300, out: 30, aiu: 12 });

  const oneDay = lib.modelTotalsIn(client, "2026-07-01", "2026-07-01");
  assert.deepEqual(oneDay["gpt-x"], { req: 10, in: 1000, out: 100, aiu: 50 });
  assert.deepEqual(oneDay["gpt-y"], { req: 2, in: 200, out: 20, aiu: 8 });
});

test("a model outside the range drops out of the list entirely", () => {
  const late = lib.modelTotalsIn(client, "2026-07-03", "2026-07-03");
  assert.deepEqual(Object.keys(late), ["gpt-y"]);
});

test("the range is inclusive at both ends", () => {
  const t = lib.modelTotalsIn(client, "2026-07-02", "2026-07-03");
  assert.equal(t["gpt-x"].req, 5);
  assert.equal(t["gpt-y"].req, 1);
});

test("both views of the bucket agree on the total", () => {
  // The guarantee that makes the filter trustworthy: reading by day and reading
  // by model are the same numbers seen from two directions.
  const byDay = lib.dayTotalsByModel(client, new Set(["nothing-matches"]));
  const dayTotal = Object.values(byDay).reduce((s, b) => s + b.aiu, 0);
  const byModel = lib.modelTotalsIn(client, "2026-07-01", "2026-07-03");
  const modelTotal = Object.values(byModel).reduce((s, b) => s + b.aiu, 0);
  assert.equal(dayTotal, modelTotal);
  assert.equal(dayTotal, 87);
});

test("session totals count each matching session once across models and days", () => {
  const t = lib.sessionTotalsIn(client, new Set(["gpt-y"]), "2026-07-01", "2026-07-02");
  assert.equal(t.total, 2);
  assert.deepEqual(t.byDay, { "2026-07-01": 1, "2026-07-02": 1 });
});

test("unfiltered session totals retain sessions with no model activity facts", () => {
  const t = lib.sessionTotalsIn(client, new Set(), "2026-07-01", "2026-07-02");
  assert.deepEqual(t, { total: 3, byDay: { "2026-07-01": 2, "2026-07-02": 1 } });
});

test("session totals follow matching activity dates and exclude unattributed facts", () => {
  const early = lib.sessionTotalsIn(client, new Set(["gpt-y"]), "2026-07-01", "2026-07-01");
  assert.deepEqual(early, { total: 1, byDay: { "2026-07-01": 1 } });

  const none = lib.sessionTotalsIn(client, new Set(["gpt-x", "gpt-y"]),
                                   "2026-07-01", "2026-07-03");
  assert.deepEqual(none, { total: 0, byDay: {} });
});
