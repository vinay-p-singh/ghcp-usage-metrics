// Pure helpers: no DOM, no globals, no state.
//
// Everything here is a function of its arguments, which is exactly why it lives
// apart from the rest of the dashboard -- these are the pieces that can be unit
// tested directly (`node --test tests/js`) instead of only through a browser.
// The rest of the scripts share one scope with this file, so the names below
// are available everywhere, just as before.

// ---- text + numbers ----
function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
const fmt = n => n.toLocaleString();
const fmtAiu = n => n.toLocaleString(undefined, { maximumFractionDigits: 2 });
// compact K/M/B for large token counts so they never overflow their box
const fmtK = n => {
  n = Math.round(n || 0);
  if (n >= 1e9) return (n / 1e9).toFixed(2) + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return n.toLocaleString();
};

// Money is always "your configured rate x recorded credits", never a bill, so
// the rate is passed in rather than read from anywhere.
function usdFrom(aiu, rate) {
  const v = (Number(aiu) || 0) * (Number(rate) || 0);
  if (v >= 1000) return "$" + v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (v >= 1) return "$" + v.toFixed(2);
  return "$" + v.toFixed(3);
}

// ---- config ----
const _lc = s => String(s).toLowerCase();
const CLIENT_ALIAS = { "vscode": "vs", "vs code": "vs", "vs": "vs",
  "cli": "cli", "copilot cli": "cli", "claude": "cla", "claude code": "cla", "cla": "cla" };
// The per-project keys each harness writes its buckets under.
const CLIENT_KEYS = ["vscode", "cli", "claude"];

// Where the extractor files a request whose source never named a model. It is
// not a model anyone chose, so nothing that lists, charts or ranks models may
// treat it as one. Defined once because every site that forgot produced a bug.
const NO_MODEL = "(no token data)";
const isRecordedModel = name => name !== NO_MODEL;

function _arr(a) { return Array.isArray(a) ? a.filter(x => typeof x === "string") : []; }

// Anything malformed becomes its safe default rather than throwing: this parses
// hand-edited JSON, and a typo must not blank the dashboard.
function normCfg(c) {
  c = (c && typeof c === "object") ? c : {};
  const ex = (c.exclude && typeof c.exclude === "object") ? c.exclude : {};
  const rc = (c.reconcile && typeof c.reconcile === "object") ? c.reconcile : {};
  return {
    since: (typeof c.since === "string" && c.since) ? c.since : null,
    until: (typeof c.until === "string" && c.until) ? c.until : null,
    autoRefreshMinutes: (typeof c.autoRefreshMinutes === "number" && c.autoRefreshMinutes >= 0) ? c.autoRefreshMinutes : 0,
    budget: { monthlyAiu: (c.budget && typeof c.budget.monthlyAiu === "number" && c.budget.monthlyAiu > 0) ? c.budget.monthlyAiu : null },
    cost: { usdPerAiu: (c.cost && typeof c.cost.usdPerAiu === "number" && c.cost.usdPerAiu > 0) ? c.cost.usdPerAiu : null },
    hideEmptyProjects: (typeof c.hideEmptyProjects === "boolean") ? c.hideEmptyProjects : true,
    startAtCreditFloor: (typeof c.startAtCreditFloor === "boolean") ? c.startAtCreditFloor : true,
    reconcile: {
      cycleStart: (typeof rc.cycleStart === "string" && rc.cycleStart) ? rc.cycleStart : null,
      cycleEnd: (typeof rc.cycleEnd === "string" && rc.cycleEnd) ? rc.cycleEnd : null,
      officialAiu: (typeof rc.officialAiu === "number" && rc.officialAiu > 0) ? rc.officialAiu : null
    },
    show: { diagnostics: (c.show && typeof c.show.diagnostics === "boolean") ? c.show.diagnostics : true },
    exclude: {
      projects: _arr(ex.projects), project_prefixes: _arr(ex.project_prefixes),
      clients: _arr(ex.clients), models: _arr(ex.models), agents: _arr(ex.agents)
    }
  };
}

function matchesAny(name, substrings, prefixes) {
  const n = _lc(name);
  return (substrings || []).some(x => x && n.includes(_lc(x)))
      || (prefixes || []).some(x => x && n.startsWith(_lc(x)));
}

function aliasClients(names) {
  return new Set((names || []).map(c => CLIENT_ALIAS[_lc(c).trim()]).filter(Boolean));
}

// ---- dates ----
function clampToSpan(v, min, max) { return !v ? min : v < min ? min : v > max ? max : v; }

function addDays(iso, n) {
  const t = new Date(iso + "T00:00:00Z");
  t.setUTCDate(t.getUTCDate() + n);
  return t.toISOString().slice(0, 10);
}

// ---- aggregation ----
// sum one client's metrics within [from, to]
function windowSum(cl, from, to) {
  let s = 0, r = 0, i = 0, o = 0, a = 0;
  for (const date in cl.by_day) {
    if (date >= from && date <= to) {
      const b = cl.by_day[date];
      s += b.sessions; r += b.requests; i += b.in; o += b.out; a += b.aiu;
    }
  }
  return { sessions: s, requests: r, in: i, out: o, aiu: a };
}

function sessTotal(cl) { let s = 0; for (const k in cl.by_day) s += cl.by_day[k].sessions; return s; }

// ---- reconciliation against GitHub's own figure ----
// This tool measures a machine; GitHub bills an account. The two answer
// different questions, so the gap between them is the finding -- never a
// licence to adjust a recorded number to match. Ours should always be the
// smaller of the two; the reverse means something here is double-counted.

// Every recorded credit in the cycle, deliberately ignoring sidebar filters:
// comparing a filtered subset against an account-wide total would overstate the
// gap and invite exactly the wrong conclusion.
function recordedInCycle(data, from, to) {
  let aiu = 0, requests = 0;
  for (const p of (data || [])) {
    for (const k of CLIENT_KEYS) {
      const w = windowSum(p[k], from, to);
      aiu += w.aiu; requests += w.requests;
    }
  }
  return { aiu, requests };
}

// UTC, because that is the clock every bucket is filed on (INV-34). Reading a
// local date here would make the card disagree with the days it compares.
function todayIso() { return new Date().toISOString().slice(0, 10); }

// `today` is passed in rather than read from the clock so this stays a pure
// function -- a stale card is a state worth testing, not one worth waiting for.
function reconcileState(rc, ours, today) {
  rc = rc || {};
  if (!rc.cycleStart || !rc.cycleEnd || !rc.officialAiu) return { ready: false };
  const gap = rc.officialAiu - ours.aiu;
  return {
    ready: true,
    stale: !!(today && (today > rc.cycleEnd || today < rc.cycleStart)),
    start: rc.cycleStart, end: rc.cycleEnd,
    official: rc.officialAiu,
    ours: ours.aiu, requests: ours.requests,
    gap,
    coverage: rc.officialAiu ? ours.aiu / rc.officialAiu : 0,
    overcount: gap < 0
  };
}

// Composite-key separator, matching AM_SEP on the Python side.
const DIM_SEP = "\u001f";

// Per-day totals with the excluded models removed, from the date x model
// dimension. Returns null when nothing is excluded so callers can stay on the
// cheaper by_day path. Session membership is handled separately by by_sdm.
function dayTotalsByModel(cl, off) {
  if (!off || !off.size) return null;
  const out = {};
  const src = (cl && cl.by_dm) || {};
  for (const key in src) {
    const i = key.indexOf(DIM_SEP);
    const model = key.slice(i + 1);
    if (i < 0 || !isRecordedModel(model) || off.has(model)) continue;
    const date = key.slice(0, i);
    const t = out[date] || (out[date] = { requests: 0, in: 0, out: 0, aiu: 0 });
    const b = src[key];
    t.requests += b.requests; t.in += b.in; t.out += b.out; t.aiu += b.aiu;
  }
  return out;
}

// Distinct sessions with matching request activity inside [from, to]. A
// session may produce several model/day facts but counts once across the range
// and once on each active day. During model filtering, unattributed facts do
// not match any selected model.
function sessionTotalsIn(cl, off, from, to) {
  const filtering = !!(off && off.size);
  if (!filtering) {
    const byDay = {};
    let total = 0;
    for (const date in ((cl && cl.by_day) || {})) {
      if (date < from || date > to) continue;
      const count = cl.by_day[date].sessions || 0;
      if (count) byDay[date] = count;
      total += count;
    }
    return { total, byDay };
  }
  const sessions = new Set();
  const daily = {};
  const src = (cl && cl.by_sdm) || {};
  for (const key in src) {
    const first = key.indexOf(DIM_SEP);
    const second = key.indexOf(DIM_SEP, first + 1);
    if (first < 0 || second < 0) continue;
    const session = key.slice(0, first);
    const date = key.slice(first + 1, second);
    const model = key.slice(second + 1);
    if (date < from || date > to || !isRecordedModel(model) || off.has(model)) continue;
    sessions.add(session);
    const day = daily[date] || (daily[date] = new Set());
    day.add(session);
  }
  const byDay = {};
  for (const date in daily) byDay[date] = daily[date].size;
  return { total: sessions.size, byDay };
}

// Per-model totals inside [from, to]. The same dimension read the other way,
// which is what lets the model list follow the date range instead of always
// reporting lifetime figures.
function modelTotalsIn(cl, from, to) {
  const out = {};
  const src = (cl && cl.by_dm) || {};
  for (const key in src) {
    const i = key.indexOf(DIM_SEP);
    if (i < 0) continue;
    const date = key.slice(0, i);
    if (date < from || date > to) continue;
    const model = key.slice(i + 1);
    const t = out[model] || (out[model] = { req: 0, in: 0, out: 0, aiu: 0 });
    const b = src[key];
    t.req += b.requests; t.in += b.in; t.out += b.out; t.aiu += b.aiu;
  }
  return out;
}

// Totals for any `date<SEP>name` dimension inside [from, to], collapsed onto
// the name. Skills, agents, tools and languages all carry the date in the key
// for exactly this reason: without it those panels reported lifetime figures
// under every filter. The stored value is either a bucket of measures or a bare
// count, and both fold the same way, so one reader serves all four.
function dimTotalsIn(cl, dim, from, to) {
  const out = {};
  const src = (cl && cl[dim]) || {};
  for (const key in src) {
    const i = key.indexOf(DIM_SEP);
    if (i < 0) continue;
    const date = key.slice(0, i);
    if (date < from || date > to) continue;
    const name = key.slice(i + 1);
    const v = src[key];
    if (typeof v === "number") {
      out[name] = (out[name] || 0) + v;
      continue;
    }
    const t = out[name] || (out[name] = {});
    for (const f in v) t[f] = (t[f] || 0) + v[f];
  }
  return out;
}

// Did this project ever record a token or a credit?
//
// Sessions get opened that never reach a model, and trimmed logs leave behind
// day entries that carry a request count and nothing else. Those projects are
// real but tell you nothing about spend, so they are worth demoting out of the
// default view. Deliberately lifetime rather than windowed: a list that
// reshuffles as you drag the calendar is worse than one that stays put.
function hasRecordedUsage(p) {
  for (const k of CLIENT_KEYS) {
    const cl = p && p[k];
    if (!cl || !cl.by_day) continue;
    for (const date in cl.by_day) {
      const b = cl.by_day[date];
      if (b.aiu > 0 || b.in > 0 || b.out > 0) return true;
    }
  }
  return false;
}

// Quartile bucket for the activity calendar's colour scale.
function calBucket(n, t1, t2, t3) {
  return n <= 0 ? 0 : n <= t1 ? 1 : n <= t2 ? 2 : n <= t3 ? 3 : 4;
}

// ---- pie geometry ----
function arcPath(cx, cy, r, a0, a1) {
  const p = a => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  const [x0, y0] = p(a0), [x1, y1] = p(a1);
  const large = (a1 - a0) > Math.PI ? 1 : 0;
  return `M ${cx} ${cy} L ${x0.toFixed(2)} ${y0.toFixed(2)} ` +
    `A ${r} ${r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} Z`;
}

// Slices for one donut: biggest first, everything past `topN` collapsed into a
// single "Other" wedge so a long tail cannot render as unreadable slivers.
// Zero and negative values are dropped -- a slice of nothing is noise.
function pieSegments(items, palette, otherColor, topN) {
  const arr = (items || []).filter(i => i.value > 0).sort((a, b) => b.value - a.value);
  const total = arr.reduce((s, i) => s + i.value, 0);
  if (!total) return { total: 0, segs: [] };
  const N = topN || 8;
  const segs = arr.slice(0, N).map((it, i) => ({
    name: it.name, value: it.value, color: palette[i % palette.length],
    pct: it.value / total * 100
  }));
  const restSum = arr.slice(N).reduce((s, i) => s + i.value, 0);
  if (restSum > 0) {
    segs.push({ name: `Other (${arr.length - N})`, value: restSum, color: otherColor,
                pct: restSum / total * 100 });
  }
  return { total, segs };
}

// ---- forecast ----
// `now` is passed in rather than read from the clock, so a projection can be
// tested and so the whole calculation is reproducible for a given day.
function forecastFrom(daily, now) {
  const dates = Object.keys(daily || {}).filter(d => daily[d] > 0).sort();
  if (!dates.length) return null;
  const consumed = dates.reduce((s, d) => s + daily[d], 0);
  const first = dates[0], last = dates[dates.length - 1];
  const spanDays = Math.max(1, Math.round((Date.parse(last) - Date.parse(first)) / 864e5) + 1);

  // A trailing 28-day average tracks recent behaviour; with less than 28 days of
  // span there is nothing to trail, so the whole range is averaged instead.
  const t28 = new Date(Date.parse(last));
  t28.setUTCDate(t28.getUTCDate() - 27);
  const s28 = t28.toISOString().slice(0, 10);
  let sum28 = 0;
  for (const d of dates) if (d >= s28) sum28 += daily[d];
  const useT28 = spanDays >= 28;
  const rate = useT28 ? sum28 / 28 : consumed / spanDays;

  const y = now.getUTCFullYear(), mo = now.getUTCMonth();
  const monthStart = new Date(Date.UTC(y, mo, 1)).toISOString().slice(0, 10);
  const daysInMonth = new Date(Date.UTC(y, mo + 1, 0)).getUTCDate();
  const daysRemaining = Math.max(0, daysInMonth - now.getUTCDate());
  let mtd = 0;
  for (const d of dates) if (d >= monthStart) mtd += daily[d];
  const projMonth = mtd + rate * daysRemaining;

  return {
    consumed, activeDays: dates.length, spanDays, rate, mtd, daysRemaining, projMonth,
    rateLabel: useT28 ? "trailing 28-day avg" : "range average",
    horizons: [["End of month", projMonth, 1], ["Next 3 months", rate * 90, 3],
               ["Next 4 months", rate * 120, 4], ["Next 6 months", rate * 180, 6]]
  };
}

// ---- agent ranking ----
const BASE_AGENTS = ["GitHub Copilot Chat", "Copilot CLI", "Claude Code"];

// Most expensive first. Agents with no credits (Claude, pre-telemetry CLI) keep
// their real request counts rather than being hidden.
function rankAgents(agg, excluded) {
  const skip = excluded || (() => false);
  return Object.entries(agg || {})
    .filter(([name, v]) => !skip(name) && (v.aiu > 0 || v.req > 0))
    .map(([name, v]) => ({ name, req: v.req, aiu: v.aiu, in: v.in, out: v.out,
                           per: v.req ? v.aiu / v.req : 0 }))
    .sort((a, b) => b.aiu - a.aiu || b.req - a.req);
}

function splitAgents(items) {
  const base = new Set(BASE_AGENTS);
  return { base: items.filter(i => base.has(i.name)),
           subs: items.filter(i => !base.has(i.name)) };
}

// A single call can look infinitely expensive per request, so the "priciest"
// signal ignores agents below a minimum sample.
function priciestPerRequest(items, minReq) {
  return (items || []).filter(i => i.req >= (minReq || 5))
    .sort((a, b) => b.per - a.per)[0] || null;
}

// Which date the view should open on. Credit reporting switched on part-way
// through a month, so the computed floor lands mid-month; opening exactly there
// would show half a month with nothing to explain the edge. Open on the whole
// month that contains it and let the thin days inside carry their own marker.
// Nothing is removed either way -- the range control still reaches everything.
function creditFloorStart(diag, min, cfgSince, enabled) {
  if (cfgSince) return cfgSince;
  if (enabled === false) return min;
  const floor = (diag && diag.credit_floor && diag.credit_floor.floor) || "";
  if (!floor) return min;
  const start = floor.slice(0, 8) + "01";
  return start > min ? start : min;
}

// Why one day inside the opened range still cannot be taken at face value.
// Returns a sentence for a tooltip, or null when the day is fully recorded.
// Missing credits outranks a partial token payload: it is the larger claim.
//
// The share threshold exists because a marker that fires everywhere says
// nothing: without it, 21 of 27 real days lit up, most for a single request in
// several hundred. Missing credits is exempt -- that is material at any size.
const DAY_WARN_SHARE = 0.05;

function dayWarning(d, minShare) {
  const req = (d && d.requests) || 0;
  if (!req) return null;
  if (!((d && d.aiu) > 0)) {
    return `${fmt(req)} request${req === 1 ? "" : "s"} on this day, and no AI ` +
      `credits were recorded for any of them. The calls are real; the credit ` +
      `figure was never written down, so this day reads as free and was not.`;
  }
  const nt = (d && d.noToken) || 0;
  const share = minShare == null ? DAY_WARN_SHARE : minShare;
  if (nt > 0 && nt / req >= share) {
    return `${fmt(nt)} of ${fmt(req)} requests on this day ` +
      `(${Math.round(nt * 100 / req)}%) carry no token payload. They are counted ` +
      `as requests and add nothing to the totals, so the figures for this day ` +
      `are a floor rather than the whole story.`;
  }
  return null;
}

// One row per session, folded across the days and models it spans, because a
// session is a piece of work rather than a cell. Sorted by what it cost, which
// is the question the data was extracted to answer. A session the source never
// named keeps its id -- there is nothing honest to put in its place.
function rankSessions(projects, from, to, off, clients) {
  const byId = {};
  for (const p of (projects || [])) {
    for (const key of (clients && clients.length ? clients : CLIENT_KEYS)) {
      const cl = p[key];
      if (!cl) continue;
      const names = cl.session_names || {};
      for (const cell in (cl.by_sdm || {})) {
        const first = cell.indexOf(DIM_SEP);
        const second = cell.indexOf(DIM_SEP, first + 1);
        if (first < 0 || second < 0) continue;
        const sid = cell.slice(0, first);
        const date = cell.slice(first + 1, second);
        const model = cell.slice(second + 1);
        if (date < from || date > to) continue;
        if (off && off.size && off.has(model)) continue;
        const b = cl.by_sdm[cell];
        const r = byId[sid] || (byId[sid] = {
          sid, name: names[sid] || null, project: p.name, harness: key,
          first: date, last: date, requests: 0, in: 0, out: 0, aiu: 0,
          cached: 0, models: []
        });
        if (date < r.first) r.first = date;
        if (date > r.last) r.last = date;
        r.requests += b.requests || 0;
        r.in += b.in || 0;
        r.out += b.out || 0;
        r.aiu += b.aiu || 0;
        r.cached += b.cached || 0;
        if (isRecordedModel(model) && r.models.indexOf(model) < 0) r.models.push(model);
      }
    }
  }
  return Object.values(byId).filter(r => r.requests > 0)
    .sort((a, b) => b.aiu - a.aiu || b.requests - a.requests);
}

// Input tokens split into what came from cache and what did not. `coverage` is
// the share of requests that reported a cache figure at all: cache reporting
// began part-way through the recorded history, so a split drawn from partial
// reporting must say so rather than presenting itself as the whole picture.
function cacheSplit(t) {
  const input = (t && t.in) || 0;
  const cached = (t && t.cached) || 0;
  const req = (t && t.requests) || 0;
  const creq = (t && t.cached_req) || 0;
  return {
    cached,
    miss: Math.max(0, input - cached),
    share: input ? cached / input : 0,
    coverage: req ? creq / req : 0,
    complete: req > 0 && creq >= req
  };
}

// Sort session rows by any column the table offers. `perReq` is derived rather
// than stored, and an unnamed session sorts under its id -- sorting by name
// must not drop every unnamed row into one indistinguishable blank block.
// Ties break on id so repeated renders keep the same order.
function sortSessions(rows, key, dir) {
  const mul = dir === "asc" ? 1 : -1;
  const val = r => {
    if (key === "name") return String(r.name || r.sid || "").toLowerCase();
    if (key === "project") return String(r.project || "").toLowerCase();
    if (key === "when") return String(r.first || "");
    if (key === "perReq") return r.requests ? r.aiu / r.requests : 0;
    return r[key] || 0;
  };
  return [...(rows || [])].sort((a, b) => {
    const x = val(a), y = val(b);
    const cmp = (typeof x === "string" || typeof y === "string")
      ? String(x).localeCompare(String(y))
      : x - y;
    return mul * cmp || String(a.sid).localeCompare(String(b.sid));
  });
}

// The browser concatenates these files into one script and never sees `module`;
// node --test requires the file directly and gets the exports.
if (typeof module !== "undefined" && module.exports) {
  module.exports = { esc, fmt, fmtAiu, fmtK, usdFrom, normCfg, matchesAny, hasRecordedUsage, CLIENT_KEYS,
    dayTotalsByModel, modelTotalsIn, sessionTotalsIn, dimTotalsIn, DIM_SEP, NO_MODEL, isRecordedModel,
                     aliasClients, clampToSpan, addDays, windowSum, sessTotal,
                     calBucket, CLIENT_ALIAS, arcPath, pieSegments, forecastFrom,
                     rankAgents, splitAgents, priciestPerRequest, BASE_AGENTS,
                     creditFloorStart, dayWarning, rankSessions, cacheSplit,
                     sortSessions, recordedInCycle, reconcileState, todayIso };
}
