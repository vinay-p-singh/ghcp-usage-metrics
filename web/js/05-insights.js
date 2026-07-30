// ---- agent cost ranking (FR-006) + cost-reduction signals (FR-010) ----
// Ranks named agents/subagents by total attributed AIU (most expensive first) so the
// biggest spenders can be targeted for reduction. AIU/request exposes per-call cost.
// Agents with aiu=0 (Claude Code, pre-telemetry CLI) still list their real request
// counts; only real GitHub-recorded AIU drives the ranking — nothing is estimated.
function renderAgents(agg, am) {
  const items = rankAgents(agg, isAgentExcluded);
  AGENT_MODELS = {};
  for (const k in (am || {})) {
    const ix = k.indexOf("\u001f");
    const ag = ix >= 0 ? k.slice(0, ix) : k;
    const model = ix >= 0 ? k.slice(ix + 1) : "?";
    if (isAgentExcluded(ag)) continue;
    (AGENT_MODELS[ag] || (AGENT_MODELS[ag] = [])).push({ model, req: am[k].req, aiu: am[k].aiu, in: am[k].in, out: am[k].out });
  }
  if (!items.length) {
    agentSignal.innerHTML = '<div class="muted">No agent activity in range.</div>';
    agentBody.innerHTML = '<tr><td colspan="6" class="muted">No agents in range.</td></tr>';
    renderPie(pieAgent, [], fmtAiu);
    return;
  }
  const { base, subs } = splitAgents(items);
  const total = items.reduce((s, i) => s + i.aiu, 0);
  const top = items[0];
  const top3 = items.slice(0, 3);
  const top3sum = top3.reduce((s, i) => s + i.aiu, 0);
  const share = total ? top3sum / total * 100 : 0;
  const priciest = priciestPerRequest(base, 5);
  const card = (k, v, s) => `<div class="pill"><div class="k">${k}</div>` +
    `<div class="v" style="font-size:var(--card-v-sm);font-weight:600;line-height:1.3;white-space:normal" title="${esc(v)}">${esc(v)}</div>` +
    `<div class="s">${s}</div></div>`;
  const cards = [
    card("Biggest spender", top.name, `${fmtAiu(top.aiu)} AIU · ${total ? (top.aiu / total * 100).toFixed(1) : 0}% of AIU`),
    card("Top 3 agents", top3.map(i => i.name).join(", "), `${share.toFixed(1)}% of AIU (${fmtAiu(top3sum)})`),
  ];
  if (priciest) cards.push(card("Priciest base agent / req", priciest.name, `${fmtAiu(priciest.per)} AIU/req · ${fmt(priciest.req)} req`));
  const subTotal = subs.reduce((s, i) => s + i.aiu, 0);
  if (subs.length) {
    const subTop = subs[0];
    cards.push(card("Top subagent", subTop.name, `${fmtAiu(subTop.aiu)} AIU · ${subTotal ? (subTop.aiu / subTotal * 100).toFixed(1) : 0}% of subagent AIU`));
    const subPri = priciestPerRequest(subs, 5);
    if (subPri) cards.push(card("Priciest subagent / req", subPri.name, `${fmtAiu(subPri.per)} AIU/req · ${fmt(subPri.req)} req`));
  }
  agentSignal.innerHTML = `<div class="pills">${cards.join("")}</div>`;
  const rowH = i =>
    `<tr class="prj" data-agent="${esc(i.name)}"><td class="pn" title="${esc(i.name)}"><span class="caret">\u25b8</span> ${esc(i.name)}</td>` +
    `<td class="num">${fmt(i.req)}</td>` +
    `<td class="num">${fmtAiu(i.aiu)}</td>` +
    `<td class="num">${fmtAiu(i.per)}</td>` +
    `<td class="num">${fmtK(i.in)}</td>` +
    `<td class="num">${fmtK(i.out)}</td></tr>`;
  const grpH = (label, n) => `<tr class="agrp"><td colspan="6">${label} (${n})</td></tr>`;
  let body = "";
  if (base.length) body += grpH("Base / harness agents", base.length) + base.map(rowH).join("");
  if (subs.length) body += grpH("Subagents \u00b7 runSubagent", subs.length) + subs.map(rowH).join("");
  agentBody.innerHTML = body || '<tr><td colspan="6" class="muted">No agents in range.</td></tr>';
  renderPie(pieAgent, items.map(i => ({ name: i.name, value: i.aiu })), fmtAiu);
}

agentBody.addEventListener("click", e => {
  const tr = e.target.closest("tr.prj");
  if (!tr) return;
  const nxt = tr.nextElementSibling;
  if (nxt && nxt.classList.contains("exp")) { nxt.remove(); tr.classList.remove("open"); return; }
  tr.classList.add("open");
  const models = (AGENT_MODELS[tr.dataset.agent] || [])
    .filter(x => isRecordedModel(x.model) && !modelHidden(x.model)).sort((a, b) => b.aiu - a.aiu);
  const rows = models.map(x =>
    `<tr><td class="dn" title="${esc(x.model)}">${esc(x.model)}</td>` +
    `<td class="num">${fmt(x.req)}</td><td class="num">${fmtAiu(x.aiu)}</td>` +
    `<td class="num">${fmtK(x.in)}</td><td class="num">${fmtK(x.out)}</td></tr>`).join("")
    || '<tr><td colspan="5" class="muted">no model breakdown</td></tr>';
  const exp = document.createElement("tr");
  exp.className = "exp";
  exp.innerHTML = `<td colspan="6"><table class="subtab"><thead><tr><th></th><th class="num">Req</th>` +
    `<th class="num">AIU</th><th class="num">In</th><th class="num">Out</th></tr></thead><tbody>` +
    `<tr class="grp"><td colspan="5">By model</td></tr>${rows}</tbody></table></td>`;
  tr.after(exp);
});

// ---- skills efficiency (FR-007) ----
// Skills are detected from SKILL.md reads (session_files) — each read is a real
// invocation. A session's tokens/AIU are attributed to every skill it invoked
// (honest attribution, documented overlap; nothing estimated). VS Code only.
function renderSkills(agg) {
  const items = Object.entries(agg)
    .map(([name, v]) => ({ name, reads: v.reads, sessions: v.sessions, aiu: v.aiu, in: v.in, out: v.out,
      per: v.sessions ? v.aiu / v.sessions : 0 }))
    .sort((a, b) => b.reads - a.reads || b.aiu - a.aiu);
  if (!items.length) {
    skillBody.innerHTML = '<tr><td colspan="7" class="muted">No SKILL.md reads in range (VS Code only; recent sessions).</td></tr>';
    renderPie(pieSkill, [], fmt);
    return;
  }
  skillBody.innerHTML = items.map(i =>
    `<tr><td class="pn" title="${esc(i.name)}">${esc(i.name)}</td>` +
    `<td class="num">${fmt(i.reads)}</td>` +
    `<td class="num">${fmt(i.sessions)}</td>` +
    `<td class="num">${fmtAiu(i.aiu)}</td>` +
    `<td class="num">${fmtAiu(i.per)}</td>` +
    `<td class="num">${fmtK(i.in)}</td>` +
    `<td class="num">${fmtK(i.out)}</td></tr>`
  ).join("");
  renderPie(pieSkill, items.map(i => ({ name: i.name, value: i.reads })), fmt);
}

// ---- usage forecast (FR-009) — multi-horizon projection + budget cascade ----
// Linear projection from REAL recorded daily AIU. Everything here is an explicit
// projection (labelled), never presented as a recorded value. Budget cascade:
// plan allowance (not locally detectable) -> config budget.monthlyAiu -> none.
function renderForecast(daily, from, to) {
  const f = forecastFrom(daily, new Date());
  if (!f) { fcView.innerHTML = '<div class="muted">No AIU in range to project from.</div>'; return; }
  const { consumed, activeDays, spanDays, rate, rateLabel, mtd, daysRemaining, projMonth } = f;
  const budget = (CFG.budget && typeof CFG.budget.monthlyAiu === "number" && CFG.budget.monthlyAiu > 0) ? CFG.budget.monthlyAiu : null;
  const card = (k, v, s) => `<div class="pill"><div class="k">${k}</div>` +
    `<div class="v" style="font-size:var(--card-v);font-weight:600;line-height:1.3">${v}</div><div class="s">${s}</div></div>`;
  const cards = [
    card("Consumed (in range)", fmtAiu(consumed) + " AIU", `${fmt(activeDays)} active days \u00b7 ${fmt(spanDays)} calendar days`),
    card("Daily rate", fmtAiu(rate) + " AIU/day", rateLabel),
    card("Projected end of month", fmtAiu(projMonth) + " AIU", `MTD ${fmtAiu(mtd)} \u00b7 ${daysRemaining}d left`),
  ];
  if (costOn()) {
    cards.push(card("Projected cost, end of month", fmtUsd(projMonth),
      `spent so far ${fmtUsd(mtd)} \u00b7 at $${costRate()} per credit`));
  }
  if (budget) {
    const pct = projMonth / budget * 100;
    cards.push(card("Monthly budget", fmtAiu(budget) + " AIU", `EoM projection ${pct.toFixed(0)}% of budget`));
  }
  const rows = f.horizons.map(([label, proj, months]) => {
    let budgetCell = '<td class="num muted">\u2014</td>', statusCell = '<td class="num muted">\u2014</td>';
    if (budget) {
      const b = budget * months;
      const pct = proj / b * 100;
      const over = proj > b;
      budgetCell = `<td class="num">${fmtAiu(b)}</td>`;
      statusCell = `<td class="num" style="color:${over ? '#d1242f' : '#1a7f37'}">${pct.toFixed(0)}% ${over ? 'over' : 'under'}</td>`;
    }
    return `<tr><td>${label}</td><td class="num">${fmtAiu(proj)}</td><td class="num cost">${fmtUsd(proj)}</td>${budgetCell}${statusCell}</tr>`;
  }).join("");
  const note = budget
    ? `Comparing projections against a monthly budget of ${fmtAiu(budget)} AIU (Config \u2192 budget.monthlyAiu).`
    : `No monthly budget set \u2014 showing projected charges only. Add <code>budget.monthlyAiu</code> in Config to compare (plan allowance isn't locally detectable for this account).`;
  fcView.innerHTML = `<div class="pills">${cards.join("")}</div>` +
    `<div class="ptable-scroll" style="margin-top:14px"><table class="ptable"><thead><tr><th>Horizon</th>` +
    `<th class="num">Projected AIU</th><th class="num cost">Projected cost</th><th class="num">Budget</th><th class="num">vs budget</th></tr></thead>` +
    `<tbody>${rows}</tbody></table></div>` +
    `<p class="cfg-note" style="margin-top:10px">Projections are linear estimates from recorded AIU (rate = ${rateLabel}); real usage is bursty. ${note}</p>`;
}

