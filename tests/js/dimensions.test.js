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
    [`s1${SEP}2026-07-01${SEP}gpt-x`]: B({ requests: 10, in: 1000, out: 100, aiu: 50 }),
    [`s1${SEP}2026-07-01${SEP}gpt-y`]: B({ requests: 2, in: 200, out: 20, aiu: 8 }),
    [`s1${SEP}2026-07-02${SEP}gpt-y`]: B({ requests: 0, in: 0, out: 0, aiu: 0 }),
    [`s2${SEP}2026-07-02${SEP}gpt-x`]: B({ requests: 5, in: 500, out: 50, aiu: 25 }),
    [`s3${SEP}2026-07-03${SEP}(no token data)`]: B({ requests: 1 })
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

// ---- sessions --------------------------------------------------------------
// by_sdm carries a session's own magnitudes, so "what did this piece of work
// cost" is answerable. A session spans days and models, so it is folded by id
// rather than summed per cell.

const C = (o) => Object.assign({
  by_day: {}, by_model: {}, by_agent: {}, by_am: {}, by_dm: {}, by_sdm: {},
  by_da: {}, by_dam: {}, by_skill: {}, by_ds: {}, by_tool: {}, by_dt: {},
  by_lang: {}, by_dl: {}, session_names: {} }, o);

function proj() {
  return [{
    name: "acme/alpha",
    vscode: C({
      by_sdm: {
        [`s1${SEP}2026-07-01${SEP}gpt-x`]: B({ requests: 10, in: 1000, out: 100, aiu: 50, cached: 900, cached_req: 10 }),
        [`s1${SEP}2026-07-02${SEP}gpt-y`]: B({ requests: 5, in: 500, out: 50, aiu: 25, cached: 400, cached_req: 5 }),
        [`s2${SEP}2026-07-02${SEP}gpt-x`]: B({ requests: 2, in: 200, out: 20, aiu: 8, cached: 0, cached_req: 0 })
      },
      session_names: { s1: "Refactor the parser" }
    }),
    cli: C({}), claude: C({})
  }];
}

test("a session is folded by id across the days and models it spans", () => {
  const rows = lib.rankSessions(proj(), "2026-07-01", "2026-07-31", null);
  const s1 = rows.find(r => r.sid === "s1");
  assert.equal(s1.requests, 15, "both of s1's cells count once");
  assert.equal(s1.aiu, 75);
  assert.equal(s1.in, 1500);
  assert.equal(s1.cached, 1300);
  assert.deepEqual([s1.first, s1.last], ["2026-07-01", "2026-07-02"]);
});

test("sessions are ranked by what they cost", () => {
  const rows = lib.rankSessions(proj(), "2026-07-01", "2026-07-31", null);
  assert.deepEqual(rows.map(r => r.sid), ["s1", "s2"]);
});

test("an unnamed session keeps its id rather than being given a name", () => {
  const rows = lib.rankSessions(proj(), "2026-07-01", "2026-07-31", null);
  assert.equal(rows.find(r => r.sid === "s1").name, "Refactor the parser");
  assert.equal(rows.find(r => r.sid === "s2").name, null);
});

test("the date range narrows a session to the part inside it", () => {
  const rows = lib.rankSessions(proj(), "2026-07-02", "2026-07-31", null);
  const s1 = rows.find(r => r.sid === "s1");
  assert.equal(s1.requests, 5, "only the day inside the range counts");
  assert.equal(s1.aiu, 25);
});

test("an excluded model is removed from a session's totals", () => {
  const rows = lib.rankSessions(proj(), "2026-07-01", "2026-07-31", new Set(["gpt-y"]));
  assert.equal(rows.find(r => r.sid === "s1").requests, 10);
});

// ---- cache split -----------------------------------------------------------

test("cache splits input into served-from-cache and fresh", () => {
  const s = lib.cacheSplit({ in: 1000, cached: 900, requests: 10, cached_req: 10 });
  assert.equal(s.cached, 900);
  assert.equal(s.miss, 100);
  assert.equal(Math.round(s.share * 100), 90);
  assert.equal(s.coverage, 1, "every request reported a figure");
});

test("cache coverage says how much of the answer is actually known", () => {
  const s = lib.cacheSplit({ in: 1000, cached: 400, requests: 10, cached_req: 6 });
  assert.equal(Math.round(s.coverage * 100), 60);
  assert.equal(s.complete, false, "a partial answer must not read as a whole one");
});

test("no input means no split rather than a division by zero", () => {
  const s = lib.cacheSplit({ in: 0, cached: 0, requests: 0, cached_req: 0 });
  assert.equal(s.share, 0);
  assert.equal(s.miss, 0);
});

test("a harness the reader switched off contributes no sessions", () => {
  const rows = lib.rankSessions(proj(), "2026-07-01", "2026-07-31", null, ["cli"]);
  assert.deepEqual(rows, [], "VS Code sessions must vanish when VS Code is off");
});

// ---- session sorting -------------------------------------------------------

const SROWS = [
  { sid: "b2", name: "Zebra work", project: "acme/beta", first: "2026-07-02",
    last: "2026-07-02", requests: 10, in: 500, out: 50, aiu: 20, cached: 100 },
  { sid: "a1", name: null, project: "acme/alpha", first: "2026-07-01",
    last: "2026-07-01", requests: 2, in: 900, out: 10, aiu: 40, cached: 800 },
  { sid: "c3", name: "Alpha work", project: "acme/gamma", first: "2026-07-03",
    last: "2026-07-03", requests: 10, in: 100, out: 5, aiu: 20, cached: 0 }
];

test("sorting by credits, most expensive first, is the default question", () => {
  assert.deepEqual(lib.sortSessions(SROWS, "aiu", "desc").map(r => r.sid),
                   ["a1", "b2", "c3"]);
});

test("sorting by cost per request uses the derived value, not the column text", () => {
  // a1 is 40/2 = 20 per request; b2 and c3 are 2. Cheapest first.
  assert.deepEqual(lib.sortSessions(SROWS, "perReq", "asc").map(r => r.sid)[2], "a1");
});

test("an unnamed session sorts under its id rather than an empty string", () => {
  const byName = lib.sortSessions(SROWS, "name", "asc").map(r => r.sid);
  assert.equal(byName[0], "a1", "the unnamed row sorts as 'a1', not first-by-blank");
  assert.deepEqual(byName, ["a1", "c3", "b2"]);
});

test("ties keep a stable order instead of shuffling between renders", () => {
  const once = lib.sortSessions(SROWS, "requests", "desc").map(r => r.sid);
  const twice = lib.sortSessions(SROWS, "requests", "desc").map(r => r.sid);
  assert.deepEqual(once, twice);
  assert.deepEqual(once.slice(0, 2), ["b2", "c3"], "equal requests break by id");
});

test("sorting by date uses the day the session started", () => {
  assert.deepEqual(lib.sortSessions(SROWS, "when", "asc").map(r => r.sid),
                   ["a1", "b2", "c3"]);
});

test("sorting never mutates the caller's array", () => {
  const copy = SROWS.slice();
  lib.sortSessions(SROWS, "in", "asc");
  assert.deepEqual(SROWS, copy);
});

// ---- dated dimensions ------------------------------------------------------
// Skills, agents, tools and languages each carry a date in their key so the
// calendar can re-scope them. One reader serves all four: the value is either a
// bucket of measures or a bare count, and both collapse onto the name the same
// way.

test("dimTotalsIn keeps only the dates inside the window", () => {
  const client = {
    by_ds: {
      [`2026-07-01${SEP}obsidian`]: { reads: 1, sessions: 1, requests: 2, in: 20, out: 4, aiu: 3 },
      [`2026-07-02${SEP}obsidian`]: { reads: 0, sessions: 0, requests: 8, in: 80, out: 16, aiu: 12 },
      [`2026-07-09${SEP}obsidian`]: { reads: 5, sessions: 5, requests: 5, in: 50, out: 10, aiu: 99 }
    }
  };
  const got = lib.dimTotalsIn(client, "by_ds", "2026-07-01", "2026-07-02");
  assert.deepEqual(got, { obsidian: { reads: 1, sessions: 1, requests: 10, in: 100, out: 20, aiu: 15 } });
});

test("dimTotalsIn sums the bare counts the same way", () => {
  const client = {
    by_dt: {
      [`2026-07-01${SEP}read_file`]: 3,
      [`2026-07-02${SEP}read_file`]: 4,
      [`2026-07-02${SEP}grep_search`]: 1,
      [`2026-07-09${SEP}read_file`]: 99
    }
  };
  assert.deepEqual(lib.dimTotalsIn(client, "by_dt", "2026-07-01", "2026-07-02"),
                   { read_file: 7, grep_search: 1 });
});

test("dimTotalsIn is empty rather than absent when nothing is in range", () => {
  const client = { by_dl: { [`2026-07-09${SEP}python`]: 2 } };
  assert.deepEqual(lib.dimTotalsIn(client, "by_dl", "2026-07-01", "2026-07-02"), {});
  assert.deepEqual(lib.dimTotalsIn({}, "by_dl", "2026-07-01", "2026-07-02"), {});
});
