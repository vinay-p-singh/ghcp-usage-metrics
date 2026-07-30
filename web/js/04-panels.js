// ---- models sidebar + agents panel + expandable project detail ----
function renderModels(agg) {
  // Include models that recorded requests but no credits -- Claude Code reports
  // no credits at all. The no-model placeholder is excluded: it is where
  // requests land when their source named no model, so offering it as a model to
  // untick would invite filtering by something nobody chose. Diagnostics counts
  // them instead.
  const items = Object.entries(agg).filter(([name, v]) => (v.aiu > 0.01 || v.req > 0) && isRecordedModel(name) && !isModelExcluded(name))
    .sort((a, b) => b[1].aiu - a[1].aiu || b[1].req - a[1].req);
  if (!items.length) { mList.innerHTML = '<div class="muted">No models in range.</div>'; mSummary.textContent = ""; return; }
  // Unticking re-scopes the whole dashboard now, but the reader is looking at
  // the sidebar when they click, so say what the selection covers.
  const kept = items.filter(([name]) => !isModelOff(name));
  const total = items.reduce((s, [, v]) => s + v.aiu, 0);
  const shown = kept.reduce((s, [, v]) => s + v.aiu, 0);
  const all = kept.length === items.length;
  mSummary.textContent = all
    ? `${items.length} models \u00b7 ${fmtAiu(total)} AIU`
    : `${kept.length} of ${items.length} models \u00b7 ${fmtAiu(shown)} of ${fmtAiu(total)} AIU`;
  mSummary.classList.toggle("filtered", !all);
  const mMax = items[0][1].aiu || 1;
  mList.innerHTML = items.map(([name, v], i) => {
    const pct = Math.max(3, v.aiu / mMax * 100);
    const on = !isModelOff(name);
    return `<label class="mrow${on ? "" : " off"}" style="background:linear-gradient(to right, var(--accent-soft) ${pct}%, transparent ${pct}%)">` +
      `<input type="checkbox" class="modelcb" value="${esc(name)}"${on ? " checked" : ""}>` +
      `<span class="sw" style="background:${PALETTE[i % PALETTE.length]}"></span>` +
      `<span class="mn" title="${esc(name)}">${esc(name)}</span>` +
      `<span class="mv">${fmtAiu(v.aiu)}</span></label>`;
  }).join("");
}

// donut pie + legend. items = [{name, value}]; fmtFn formats the value tooltip.
function renderPie(el, items, fmtFn) {
  const { total, segs } = pieSegments(items, PALETTE, "#adb5bd", 8);
  if (!total) { el.innerHTML = '<div class="muted">No data in range.</div>'; return; }
  const cx = 80, cy = 80, R = 72;
  let a = -Math.PI / 2, paths = "";
  if (segs.length === 1) {
    paths = `<circle cx="${cx}" cy="${cy}" r="${R}" fill="${segs[0].color}">` +
      `<title>${esc(segs[0].name)}: ${fmtFn(segs[0].value)} (100%)</title></circle>`;
  } else {
    for (const s of segs) {
      const a1 = a + (s.value / total) * 2 * Math.PI;
      paths += `<path d="${arcPath(cx, cy, R, a, a1)}" fill="${s.color}">` +
        `<title>${esc(s.name)}: ${fmtFn(s.value)} (${s.pct.toFixed(1)}%)</title></path>`;
      a = a1;
    }
  }
  const hole = `<circle cx="${cx}" cy="${cy}" r="40" style="fill:var(--surface)"/>` +
    `<text x="${cx}" y="${cy - 1}" text-anchor="middle" style="fill:var(--fg);font-size:16px;font-weight:650">${fmtK(total)}</text>` +
    `<text x="${cx}" y="${cy + 13}" text-anchor="middle" style="fill:var(--fg-subtle);font-size:8.5px;letter-spacing:.08em">TOTAL</text>`;
  const legend = segs.map(s =>
    `<div class="lg"><span class="sw" style="background:${s.color}"></span>` +
    `<span class="ln" title="${esc(s.name)}">${esc(s.name)}</span>` +
    `<span class="lp">${s.pct.toFixed(1)}%</span></div>`).join("");
  el.innerHTML = `<div class="pie-row"><svg class="pie" viewBox="0 0 160 160">${paths}${hole}</svg>` +
    `<div class="legend">${legend}</div></div>`;
}

function projectDetailHTML(name) {
  const d = byName[name];
  if (!d) return "";
  const model = {}, agent = {}, day = {}, langC = {};
  const acc = (o, k, b) => { const t = o[k] || (o[k] = { req: 0, in: 0, out: 0, aiu: 0 });
    t.req += b.requests; t.in += b.in; t.out += b.out; t.aiu += b.aiu; };
  for (const [clm, on] of [[d.vscode, CUR.vs], [d.cli, CUR.cli], [d.claude, CUR.cla]]) {
    if (!on) continue;
    for (const k in (clm.by_model || {})) acc(model, k, clm.by_model[k]);
    for (const k in (clm.by_agent || {})) acc(agent, k, clm.by_agent[k]);
    for (const dt in clm.by_day) if (dt >= CUR.from && dt <= CUR.to) acc(day, dt, clm.by_day[dt]);
    for (const k in (clm.by_lang || {})) langC[k] = (langC[k] || 0) + clm.by_lang[k];
  }
  const row = (k, v) => `<tr><td class="dn" title="${esc(k)}">${esc(k)}</td>` +
    `<td class="num">${fmt(v.req)}</td>` +
    `<td class="num">${fmtAiu(v.aiu)}</td>` +
    `<td class="num cost">${fmtUsd(v.aiu)}</td>` +
    `<td class="num">${fmtK(v.in)}</td><td class="num">${fmtK(v.out)}</td></tr>`;
  const crow = (k, n) => `<tr><td class="dn" title="${esc(k)}">${esc(k)}</td>` +
    `<td class="num">${fmt(n)}</td><td class="num" colspan="4"></td></tr>`;
  const grp = label => `<tr class="grp"><td colspan="6">${label}</td></tr>`;
  const sect = obj => Object.entries(obj).sort((a, b) => b[1].aiu - a[1].aiu).map(([k, v]) => row(k, v)).join("");
  const csect = obj => Object.entries(obj).sort((a, b) => b[1] - a[1]).slice(0, 20).map(([k, n]) => crow(k, n)).join("");
  const none = '<tr><td colspan="6" class="muted">none</td></tr>';
  const modelRows = Object.entries(model).filter(([k]) => isRecordedModel(k) && !modelHidden(k))
    .sort((a, b) => b[1].aiu - a[1].aiu).map(([k, v]) => row(k, v)).join("") || none;
  const agentF = Object.fromEntries(Object.entries(agent).filter(([k]) => !isAgentExcluded(k)));
  const agentRows = sect(agentF) || none;
  const dayRows = Object.keys(day).sort().map(dt => row(dt, day[dt])).join("")
    || '<tr><td colspan="6" class="muted">none in range</td></tr>';
  return `<table class="subtab"><thead><tr><th></th><th class="num">Req</th><th class="num">AIU</th>` +
    `<th class="num cost">Cost</th><th class="num">In</th><th class="num">Out</th></tr></thead><tbody>` +
    grp("By model") + modelRows +
    grp("By agent") + agentRows +
    grp("By day (selected range)") + dayRows +
    `</tbody></table>`;
}

tblBody.addEventListener("click", e => {
  const tr = e.target.closest("tr.prj");
  if (!tr) return;
  const nxt = tr.nextElementSibling;
  if (nxt && nxt.classList.contains("exp")) { nxt.remove(); tr.classList.remove("open"); return; }
  tr.classList.add("open");
  const exp = document.createElement("tr");
  exp.className = "exp";
  exp.innerHTML = `<td colspan="7">${projectDetailHTML(tr.dataset.name)}</td>`;
  tr.after(exp);
});

// ---- sidebar grid rows (sorted by lifetime sessions) ----
let order = [];
let projRows = [];
let projCbs = [];

// Load (or reload) the project dataset. Called once at boot and again whenever
// the extension pushes the completed background scan, so a fresh dataset never
// costs the reader their date range, project selection or search text.
function initData(projects) {
  const prevMin = MIN, prevMax = MAX;
  const wasFullSpan = !dFrom.value || (dFrom.value === prevMin && dTo.value === prevMax);
  // Remember what the reader had ticked so a background scan never silently
  // re-scopes their numbers. A box carrying `auto` was never their choice --
  // it is just the current default, so it follows the setting rather than
  // freezing the first answer forever.
  const prev = new Map(projCbs.map(c => [c.value, { on: c.checked, auto: c.dataset.auto === "1" }]));

  DATA = Array.isArray(projects) ? projects : [];
  for (const k in byName) delete byName[k];
  for (const d of DATA) byName[d.name] = d;

  allDays = [...new Set(DATA.filter(d => !isExcluded(d.name)).flatMap(d =>
    [...Object.keys(d.vscode.by_day), ...Object.keys(d.cli.by_day), ...Object.keys(d.claude.by_day)]))].sort();
  MIN = allDays[0] || "1970-01-01";
  MAX = allDays[allDays.length - 1] || "1970-01-01";
  // A configured start/end is a hard boundary, so make it the span the date
  // controls offer too - otherwise they invite a range the totals ignore.
  if (CFG.since && CFG.since > MIN) MIN = CFG.since;
  if (CFG.until && CFG.until < MAX) MAX = CFG.until;
  if (MAX < MIN) MAX = MIN;
  dFrom.min = dTo.min = MIN;
  dFrom.max = dTo.max = MAX;
  if (wasFullSpan) { dFrom.value = MIN; dTo.value = MAX; }
  else { dFrom.value = clampDate(dFrom.value); dTo.value = clampDate(dTo.value); }

  order = [...DATA].sort((a, b) =>
    (sessTotal(b.vscode) + sessTotal(b.cli) + sessTotal(b.claude)) - (sessTotal(a.vscode) + sessTotal(a.cli) + sessTotal(a.claude))
    || a.name.localeCompare(b.name));
  projBody.innerHTML = order.map(d =>
    `<div class="prow${hasRecordedUsage(d) ? "" : " lowsig"}" data-name="${esc(d.name)}">` +
    `<label><input type="checkbox" class="projcb" value="${esc(d.name)}">` +
    `<span class="pname" title="${esc(d.name)}">${esc(d.name)}</span></label></div>`
  ).join("");
  projRows = [...projBody.querySelectorAll(".prow")];
  projCbs = [...projBody.querySelectorAll(".projcb")];
  const demote = hideEmptyOn();
  for (const c of projCbs) {
    const low = c.closest(".prow").classList.contains("lowsig");
    const p = prev.get(c.value);
    if (p && !p.auto) { c.checked = p.on; delete c.dataset.auto; }
    else setDefaultTick(c, demote && low);
  }
}

// Apply the default state to one checkbox and record that the reader did not
// choose it, so the box keeps following the setting until they touch it.
// `demoted` means: unticked only because it has no recorded usage.
function setDefaultTick(cb, demoted) {
  cb.checked = !demoted;
  cb.dataset.auto = "1";
}

