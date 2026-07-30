// The test harness must build data in the shape the extractor really produces.
//
// A fixture that quietly writes to a key nothing reads is worse than no fixture:
// it fails for the right message and the wrong reason, which cost an hour when a
// project's harness records turned out to sit at the top level rather than under
// a `clients` key. So the shape is not restated here -- it is read from
// tests/golden/contract.json, which tests/test_contract.py emits from a real
// scan. If the extractor's shape changes, this fails until the harness follows.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const h = require("./harness.js");
const CONTRACT = JSON.parse(
  fs.readFileSync(path.join(__dirname, "..", "golden", "contract.json"), "utf8"));

test("a harness project has the keys the extractor writes", () => {
  const p = h.project("acme/x", {});
  assert.deepEqual(Object.keys(p).sort(), [...CONTRACT.project_keys].sort());
});

test("harness records are reachable where the dashboard looks for them", () => {
  const p = h.project("acme/x", {});
  for (const name of CONTRACT.harnesses) {
    assert.ok(p[name], `no record at p.${name} -- the dashboard reads it there`);
  }
});

test("a harness record carries every dimension the extractor emits", () => {
  const c = h.client({});
  assert.deepEqual(Object.keys(c).sort(), [...CONTRACT.dimensions].sort());
});

test("harness measures are named as the extractor names them", () => {
  const c = h.client({ "2026-07-01": { requests: 1 } });
  assert.deepEqual(Object.keys(c.by_day["2026-07-01"]).sort(),
                   [...CONTRACT.day_fields].sort());
  assert.deepEqual(Object.keys(h.FLAT({ requests: 1 })).sort(),
                   [...CONTRACT.flat_fields].sort());
});

test("the dashboard splits composite keys on the separator the extractor used", () => {
  // web/js/00-lib.js hardcodes DIM_SEP; if the extractor ever changed it, every
  // model filter would silently stop matching instead of failing loudly.
  const lib = fs.readFileSync(
    path.join(__dirname, "..", "..", "web", "js", "00-lib.js"), "utf8");
  const m = lib.match(/DIM_SEP\s*=\s*"([^"]*)"/);
  assert.ok(m, "web/js/00-lib.js no longer defines DIM_SEP");
  assert.equal(JSON.parse(`"${m[1]}"`), CONTRACT.separator);
});

test("the no-model placeholder is spelled out in exactly one dashboard module", () => {
  // It used to be hardcoded at four sites across three files, and each site that
  // forgot to exclude it produced a bug. One definition, one predicate.
  const sentinel = CONTRACT.sentinels.no_token_model;
  const dir = path.join(__dirname, "..", "..", "web", "js");
  const users = fs.readdirSync(dir)
    .filter(n => n.endsWith(".js"))
    .filter(n => fs.readFileSync(path.join(dir, n), "utf8").includes(sentinel));
  assert.deepEqual(users, ["00-lib.js"],
    `${sentinel} is hardcoded outside 00-lib.js -- use isRecordedModel() instead`);
});

test("the dashboard and the extractor agree on how the placeholder is spelled", () => {
  const lib = require(path.join(__dirname, "..", "..", "web", "js", "00-lib.js"));
  assert.equal(lib.NO_MODEL, CONTRACT.sentinels.no_token_model);
  assert.equal(lib.isRecordedModel(lib.NO_MODEL), false);
  assert.equal(lib.isRecordedModel("claude-opus-4.8"), true);
});
