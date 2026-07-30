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
  return {
    since: (typeof c.since === "string" && c.since) ? c.since : null,
    until: (typeof c.until === "string" && c.until) ? c.until : null,
    autoRefreshMinutes: (typeof c.autoRefreshMinutes === "number" && c.autoRefreshMinutes >= 0) ? c.autoRefreshMinutes : 0,
    budget: { monthlyAiu: (c.budget && typeof c.budget.monthlyAiu === "number" && c.budget.monthlyAiu > 0) ? c.budget.monthlyAiu : null },
    cost: { usdPerAiu: (c.cost && typeof c.cost.usdPerAiu === "number" && c.cost.usdPerAiu > 0) ? c.cost.usdPerAiu : null },
    hideEmptyProjects: (typeof c.hideEmptyProjects === "boolean") ? c.hideEmptyProjects : true,
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

// The browser concatenates these files into one script and never sees `module`;
// node --test requires the file directly and gets the exports.
if (typeof module !== "undefined" && module.exports) {
  module.exports = { esc, fmt, fmtAiu, fmtK, usdFrom, normCfg, matchesAny, hasRecordedUsage, CLIENT_KEYS,
    dayTotalsByModel, modelTotalsIn, sessionTotalsIn, DIM_SEP, NO_MODEL, isRecordedModel,
                     aliasClients, clampToSpan, addDays, windowSum, sessTotal,
                     calBucket, CLIENT_ALIAS, arcPath, pieSegments, forecastFrom,
                     rankAgents, splitAgents, priciestPerRequest, BASE_AGENTS };
}
