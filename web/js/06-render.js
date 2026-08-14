// ---- user-strength stats (FR-008) — productivity cluster ----
// Derived entirely from recorded values: most-used model/agent (by requests),
// output-token volume, edit/read tool-calls (exact from by_tool), and
// turns-to-completion (requests per session). No estimation, no LoC.
function renderStrengths(models, agents, tools, perProj, tot) {
  const topBy = (obj, hidden) => Object.entries(obj)
    .filter(([k]) => isRecordedModel(k) && !(hidden && hidden(k)))
    .sort((a, b) => (b[1].req || 0) - (a[1].req || 0))[0];
  const mm = topBy(models, modelHidden), ma = topBy(agents);
  const editRx = /edit|replace_string|apply_patch|create_file|insert|multi_replace/i;
  let editCalls = 0;
  for (const k in tools) if (editRx.test(k)) editCalls += tools[k];
  const fileReads = tools["read_file"] || 0;
  const tps = tot.sessions ? tot.req / tot.sessions : 0;
  const card = (k, v, s) => `<div class="pill"><div class="k">${k}</div>` +
    `<div class="v" style="font-size:var(--card-v);font-weight:600;line-height:1.3" title="${esc(String(v))}">${esc(String(v))}</div><div class="s">${s}</div></div>`;
  const cards = [
    card("Most-used model", mm ? mm[0] : "\u2014", mm ? fmt(mm[1].req) + " requests" : ""),
    card("Most-used agent", ma ? ma[0] : "\u2014", ma ? fmt(ma[1].req) + " requests" : ""),
    card("Output tokens", fmtK(tot.out), "generated in scope"),
    card("Edit tool-calls", fmt(editCalls), "files edited / created"),
    card("File reads", fmt(fileReads), "read_file calls"),
    card("Turns / session", tps.toFixed(1), fmt(tot.req) + " reqs \u00b7 " + fmt(tot.sessions) + " sessions"),
  ];
  const topProj = [...perProj].filter(p => p.out > 0).sort((a, b) => b.out - a.out).slice(0, 5);
  const projRows = topProj.map(p =>
    `<tr><td class="pn" title="${esc(p.name)}">${esc(p.name)}</td>` +
    `<td class="num">${fmtK(p.out)}</td><td class="num">${fmtK(p.in)}</td>` +
    `<td class="num">${fmt(p.requests)}</td><td class="num">${fmtAiu(p.aiu)}</td></tr>`).join("")
    || '<tr><td colspan="5" class="muted">No output in range.</td></tr>';
  stView.innerHTML = `<div class="pills">${cards.join("")}</div>` +
    `<div class="ptable-scroll" style="margin-top:14px"><table class="ptable"><thead><tr>` +
    `<th>Most productive projects (by output)</th><th class="num">Output</th><th class="num">Input</th>` +
    `<th class="num">Requests</th><th class="num">AIU</th></tr></thead><tbody>${projRows}</tbody></table></div>`;
}

// Resolve the current filter scope (harness toggles, search, project selection,
// clamped date window) and publish it to the module-level CUR + preset UI.
function computeScope() {
  const exCl = excludedClients();
  const vs  = cbVs.checked && !exCl.has("vs");
  const cli = cbCli.checked && !exCl.has("cli");
  const cla = cbClaude.checked && !exCl.has("cla");
  const q   = projSearch.value.trim().toLowerCase();
  // Unticked means excluded. Search only filters the sidebar list -- letting it
  // re-scope the totals would silently change every number while you are just
  // hunting for a project to untick.
  const excluded = new Set(projCbs.filter(c => !c.checked).map(c => c.value));
  let from = dFrom.value || MIN;
  let to   = dTo.value || MAX;
  if (CFG.since && CFG.since > from) from = CFG.since;
  if (CFG.until && CFG.until < to)   to   = CFG.until;
  CUR = { vs, cli, cla, from, to };
  markActivePreset();
  return { vs, cli, cla, q, excluded, offModels: MODEL_OFF, from, to };
}

// Sidebar harness badges: sessions within the range across all projects.
function renderBadges(scope) {
  const { from, to, offModels } = scope;
  let allVs = 0, allCli = 0, allCla = 0;
  for (const d of DATA) {
    if (isExcluded(d.name)) continue;
    allVs += sessionTotalsIn(d.vscode, offModels, from, to).total;
    allCli += sessionTotalsIn(d.cli, offModels, from, to).total;
    allCla += sessionTotalsIn(d.claude, offModels, from, to).total;
  }
  badgeVs.textContent = allVs;
  badgeCli.textContent = allCli;
  badgeCla.textContent = allCla;
}

// Project checkbox grid: mark excluded, hide 0-request/out-of-search rows.
function renderGrid(scope) {
  const { vs, cli, cla, q, from, to } = scope;
  const demote = hideEmptyOn();
  const revealed = document.body.classList.contains("show-lowsig");
  let shown = 0, low = 0;
  for (const row of projRows) {
    if (isExcluded(row.dataset.name)) { row.classList.add("excluded"); continue; }
    row.classList.remove("excluded");
    const d = byName[row.dataset.name];
    const wv = windowSum(d.vscode, from, to);
    const wc = windowSum(d.cli, from, to);
    const wl = windowSum(d.claude, from, to);
    // only show projects that actually made requests (hide empty 0-request sessions)
    const act = (vs ? wv.requests : 0) + (cli ? wc.requests : 0) + (cla ? wl.requests : 0);
    const quiet = demote && row.classList.contains("lowsig");
    if (quiet) low++;
    const visible = act > 0 && row.dataset.name.toLowerCase().includes(q) && (!quiet || revealed);
    row.classList.toggle("hidden", !visible);
    if (visible) shown++;
  }
  projReveal.hidden = low === 0;
  projReveal.textContent = revealed
    ? `hide ${low} with no recorded tokens`
    : `show ${low} with no recorded tokens`;
  projEmpty.hidden = shown > 0;
}

// Accumulate one client's flat bucket (by_model / by_agent / by_am) into an agg.
function _accDim(o, k, b) {
  const t = o[k] || (o[k] = { req: 0, in: 0, out: 0, aiu: 0 });
  t.req += b.requests; t.in += b.in; t.out += b.out; t.aiu += b.aiu;
}

// Aggregate every in-scope project × enabled client × date-window bucket into the
// totals + per-dimension breakdowns the pills and charts consume.
function aggregate(scope) {
  const { vs, cli, cla, q, excluded, from, to } = scope;
  // Models the reader unticked. Passed to the date x model dimension so an
  // excluded model drops out of the day figures too, exactly as an excluded
  // project does. Read from the filter state, not the checkboxes -- the sidebar
  // is redrawn after this runs, so the DOM is one render behind.
  const off = scope.offModels;
  const filtering = !!(off && off.size);
  const ZERO = { requests: 0, in: 0, out: 0, aiu: 0 };
  const agg = {
    aiu: 0, req: 0, inTok: 0, outTok: 0, projCount: 0,
    reqVs: 0, reqCli: 0, reqCla: 0, sessTot: 0,
    days: new Set(), daily: {}, dailyReq: {}, dayStats: {}, perProj: [],
    cachedTok: 0, cachedReq: 0, rows: [],
    clients: [vs ? "vscode" : null, cli ? "cli" : null, cla ? "claude" : null].filter(Boolean),
    modelAgg: {}, agentAgg: {}, amAgg: {}, skillAgg: {}, toolAgg: {}, langAgg: {}
  };
  for (const d of DATA) {
    if (isExcluded(d.name)) continue;
    const wv = windowSum(d.vscode, from, to);
    const wc = windowSum(d.cli, from, to);
    const wl = windowSum(d.claude, from, to);
    // only projects that made requests in range (hide empty 0-request sessions)
    const act = (vs ? wv.requests : 0) + (cli ? wc.requests : 0) + (cla ? wl.requests : 0);
    const inScope = act > 0 && !excluded.has(d.name);
    if (!inScope) continue;
    agg.projCount++;
    agg.rows.push(d);
    let ps = 0, pr = 0, pi = 0, po = 0, pa = 0;
    for (const [clm, on, hk] of [[d.vscode, vs, "vs"], [d.cli, cli, "cli"], [d.claude, cla, "cla"]]) {
      if (!on) continue;
      const dm = dayTotalsByModel(clm, off);
      const sessionTotals = sessionTotalsIn(clm, off, from, to);
      ps += sessionTotals.total;
      for (const date in clm.by_day) {
        if (date >= from && date <= to) {
          const b = clm.by_day[date];
          const t = dm ? (dm[date] || ZERO) : b;
          pr += t.requests; pi += t.in; po += t.out; pa += t.aiu;
          agg.cachedTok += t.cached || 0;
          agg.cachedReq += t.cached_req || 0;
          agg.daily[date] = (agg.daily[date] || 0) + t.aiu;
          agg.dailyReq[date] = (agg.dailyReq[date] || 0) + t.requests;
          const ds = agg.dayStats[date] || (agg.dayStats[date] = { req: 0, in: 0, out: 0, aiu: 0, sessions: 0, noToken: 0 });
          ds.req += t.requests; ds.in += t.in; ds.out += t.out; ds.aiu += t.aiu;
          ds.sessions += sessionTotals.byDay[date] || 0;
          if (hk === "vs") agg.reqVs += t.requests; else if (hk === "cli") agg.reqCli += t.requests; else agg.reqCla += t.requests;
          if (!dm || t.requests > 0) agg.days.add(date);
        }
      }
      // Requests the source filed under no model at all: they raise the request
      // count and nothing else, which is what makes a day look cheap.
      for (const key in clm.by_dm) {
        const i = key.indexOf(DIM_SEP);
        if (i < 0 || isRecordedModel(key.slice(i + 1))) continue;
        const date = key.slice(0, i);
        if (date < from || date > to) continue;
        const ds = agg.dayStats[date] || (agg.dayStats[date] = { req: 0, in: 0, out: 0, aiu: 0, sessions: 0, noToken: 0 });
        ds.noToken += clm.by_dm[key].requests;
      }
      // The model list follows the date range now, same as everything else.
      const mw = modelTotalsIn(clm, from, to);
      for (const k in mw) {
        const t = agg.modelAgg[k] || (agg.modelAgg[k] = { req: 0, in: 0, out: 0, aiu: 0 });
        const b = mw[k];
        t.req += b.req; t.in += b.in; t.out += b.out; t.aiu += b.aiu;
      }
      // Agents, skills, tools and languages all follow the date range now, the
      // same as the model list. Each reads its date-keyed dimension rather than
      // the undated one, which is what used to leave these panels reporting
      // lifetime figures under every filter.
      const aw = dimTotalsIn(clm, "by_da", from, to);
      for (const k in aw) _accDim(agg.agentAgg, k, aw[k]);
      const amw = dimTotalsIn(clm, "by_dam", from, to);
      for (const k in amw) _accDim(agg.amAgg, k, amw[k]);
      const sw = dimTotalsIn(clm, "by_ds", from, to);
      for (const k in sw) {
        const s = agg.skillAgg[k] || (agg.skillAgg[k] = { reads: 0, sessions: 0, req: 0, in: 0, out: 0, aiu: 0 });
        const b = sw[k];
        s.reads += b.reads; s.sessions += b.sessions; s.req += b.requests; s.in += b.in; s.out += b.out; s.aiu += b.aiu;
      }
      const lw = dimTotalsIn(clm, "by_dl", from, to);
      for (const k in lw) agg.langAgg[k] = (agg.langAgg[k] || 0) + lw[k];
      const tw = dimTotalsIn(clm, "by_dt", from, to);
      for (const k in tw) agg.toolAgg[k] = (agg.toolAgg[k] || 0) + tw[k];
    }
    agg.perProj.push({ name: d.name, sessions: ps, requests: pr, in: pi, out: po, aiu: pa });
    agg.aiu += pa; agg.req += pr; agg.inTok += pi; agg.outTok += po; agg.sessTot += ps;
  }
  // A project the kept models never touched is out of scope, the same as a
  // project with no requests in the window.
  if (filtering) {
    agg.perProj = agg.perProj.filter(p => p.requests > 0);
    agg.projCount = agg.perProj.length;
  }
  return agg;
}

function render() {
  const scope = computeScope();
  renderBadges(scope);
  renderGrid(scope);
  const a = aggregate(scope);
  _lastAgg = a; _lastScope = scope;

  applyCostVisibility();
  pAiu.textContent  = fmtAiu(a.aiu);
  pCost.textContent = costOn() ? fmtUsd(a.aiu) : "\u2014";
  pCostSub.textContent = costOn()
    ? "at $" + costRate() + " per credit"
    : "set cost.usdPerAiu in Config";
  pReq.textContent  = fmt(a.req);
  pIn.textContent   = fmtK(a.inTok);
  pOut.textContent  = fmtK(a.outTok);
  pProj.textContent = fmt(a.projCount);
  pDays.textContent = fmt(a.days.size);
  curPerProj = a.perProj;

  renderDaily(a.daily, a.dayStats);
  renderHeatmap(a.dayStats, scope.from, scope.to);
  renderTop(a.perProj);
  renderTable(a.perProj);
  renderModels(a.modelAgg);
  renderAgents(a.agentAgg, a.amAgg);
  renderSkills(a.skillAgg);
  renderSessions(rankSessions(a.rows, scope.from, scope.to, MODEL_OFF, a.clients));
  if (sessReveal && !sessReveal._bound) {
    sessReveal._bound = true;
    sessReveal.addEventListener("click", () => { sessShowQuiet = !sessShowQuiet; render(); });
  }
  const sessHead = document.querySelector('[data-tabpanel="sessions"] thead');
  if (sessHead && !sessHead._bound) {
    sessHead._bound = true;
    sessHead.addEventListener("click", ev => {
      const th = ev.target.closest("th.sortable");
      if (!th) return;
      sessSortBy(th.dataset.sort);
      render();
    });
  }
  renderCacheSplit({ in: a.inTok, cached: a.cachedTok, requests: a.req, cached_req: a.cachedReq });
  renderStrengths(a.modelAgg, a.agentAgg, a.toolAgg, a.perProj, { out: a.outTok, req: a.req, sessions: a.sessTot });
  renderForecast(a.daily, scope.from, scope.to);
  renderPie(pieClient, [{ name: "VS Code", value: a.reqVs }, { name: "CLI", value: a.reqCli }, { name: "Claude Code", value: a.reqCla }], fmt);
  renderPie(pieModel, Object.entries(a.modelAgg).filter(([name, v]) => v.aiu > 0 && isRecordedModel(name) && !modelHidden(name)).map(([name, v]) => ({ name, value: v.aiu })), fmtAiu);
  renderPie(pieProj, a.perProj.map(p => ({ name: p.name, value: p.requests })), fmt);
  renderPie(pieLang, Object.entries(a.langAgg).map(([name, v]) => ({ name, value: v })), fmt);
}

// A tier change only needs the two charts that bake pixel geometry into SVG
// coordinates -- the bar chart's height and the heat-map's cell grid. Every
// other surface is CSS-driven and reflows on its own, so re-aggregating the
// whole dataset on every resize step would be pure waste.
function redrawScaled() {
  if (!_lastAgg) return;
  renderDaily(_lastAgg.daily, _lastAgg.dayStats);
  renderHeatmap(_lastAgg.dayStats, _lastScope.from, _lastScope.to);
}

cbVs.addEventListener("change", render);
cbCli.addEventListener("change", render);
cbClaude.addEventListener("change", render);
projSearch.addEventListener("input", render);
mList.addEventListener("change", e => {
  if (!e.target.classList.contains("modelcb")) return;
  if (e.target.checked) MODEL_OFF.delete(e.target.value); else MODEL_OFF.add(e.target.value);
  render();
});
document.getElementById("modelAll").addEventListener("click", () => { MODEL_OFF.clear(); render(); });
document.getElementById("modelNone").addEventListener("click", () => {
  for (const c of mList.querySelectorAll(".modelcb")) MODEL_OFF.add(c.value);
  render();
});
// Touching a box makes its state the reader's own, so it survives a setting change.
projBody.addEventListener("change", e => {
  if (e.target.classList.contains("projcb")) delete e.target.dataset.auto;
  render();
});
// Any other way of changing the range retires the day chip - it would otherwise
// claim a selection the controls no longer show.
function rangeChanged() { floorOverridden = true; prevRange = null; showDayChip(null); render(); }
dFrom.addEventListener("change", rangeChanged);
dTo.addEventListener("change", rangeChanged);
presets.addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  setPreset(b.dataset.days);
  rangeChanged();
});
projClear.addEventListener("click", () => {
  // Back to the default view: everything counted except the projects that never
  // recorded a token, and no search narrowing the list.
  const demote = hideEmptyOn();
  projCbs.forEach(c => setDefaultTick(c, demote && c.closest(".prow").classList.contains("lowsig")));
  projSearch.value = "";
  render();
});
projReveal.addEventListener("click", () => {
  document.body.classList.toggle("show-lowsig");
  render();
});
document.getElementById("cliAll").addEventListener("click", () => {
  cbVs.checked = true; cbCli.checked = true; cbClaude.checked = true; render();
});
document.getElementById("cliNone").addEventListener("click", () => {
  cbVs.checked = false; cbCli.checked = false; cbClaude.checked = false; render();
});
document.getElementById("projAll").addEventListener("click", () => {
  projCbs.forEach(c => { if (!c.closest(".prow").classList.contains("hidden")) { c.checked = true; delete c.dataset.auto; } });
  render();
});
document.getElementById("projNone").addEventListener("click", () => {
  projCbs.forEach(c => { if (!c.closest(".prow").classList.contains("hidden")) { c.checked = false; delete c.dataset.auto; } });
  render();
});
const cfgView = document.getElementById("cfgView");
const dashView = document.getElementById("dashView");
const cfgBtn = document.getElementById("cfgBtn");
function setTab(t) {
  const valid = ["overview", "calendar", "breakdown", "agents", "sessions", "skills", "strengths", "forecast", "diagnostics", "config"];
  if (!valid.includes(t)) t = "overview";
  if (t === "diagnostics" && !diagnosticsOn()) t = "overview";
  for (const x of document.querySelectorAll("#tabs .tab")) {
    const on = x.dataset.tab === t;
    x.classList.toggle("active", on);
    x.setAttribute("aria-selected", String(on));
  }
  const isCfg = t === "config";
  cfgBtn.classList.toggle("active", isCfg);
  dashView.style.display = isCfg ? "none" : "";
  cfgView.hidden = !isCfg;
  if (!isCfg) for (const p of dashView.querySelectorAll(".tabpanel")) p.classList.toggle("active", p.dataset.tabpanel === t);
  try { localStorage.setItem("cpTab", t); } catch (e) {}
}
document.getElementById("tabs").addEventListener("click", e => {
  const b = e.target.closest(".tab");
  if (!b) return;
  setTab(b.dataset.tab);
});
document.getElementById("tabs").addEventListener("keydown", e => {
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  const tabs = [...document.querySelectorAll("#tabs .tab")].filter(x => !x.hidden);
  const i = tabs.findIndex(x => x.classList.contains("active"));
  if (i < 0) return;
  const j = e.key === "ArrowRight" ? (i + 1) % tabs.length : (i - 1 + tabs.length) % tabs.length;
  setTab(tabs[j].dataset.tab); tabs[j].focus(); e.preventDefault();
});
cfgBtn.addEventListener("click", () => setTab("config"));

