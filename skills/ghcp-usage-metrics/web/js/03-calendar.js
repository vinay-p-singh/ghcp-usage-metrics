// ---- day tooltip + day/range selection -------------------------------------
// The calendar used to be a picture you could only look at. Every day cell (and
// every bar in the AIU chart) is now a filter control, and hovering explains the
// day in the same units the rest of the dashboard uses.
const dayTip = document.createElement("div");
dayTip.id = "dayTip";
dayTip.hidden = true;
document.body.appendChild(dayTip);

function dayTipHTML(iso, s) {
  s = s || { req: 0, in: 0, out: 0, aiu: 0, sessions: 0, noToken: 0 };
  const wd = new Date(iso + "T00:00:00Z").toLocaleDateString(undefined,
    { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const line = (k, v) => `<div class="dt-row"><span>${k}</span><b>${v}</b></div>`;
  const warn = dayWarning({ requests: s.req, aiu: s.aiu, noToken: s.noToken });
  return `<div class="dt-head">${esc(wd)}</div>` +
    line("Requests", fmt(s.req)) +
    line("Credits", fmtAiu(s.aiu) + " AIU") +
    (costOn() ? line("Cost", fmtUsd(s.aiu)) : "") +
    line("Input", fmtK(s.in)) +
    line("Output", fmtK(s.out)) +
    (s.sessions ? line("Sessions active", fmt(s.sessions)) : "") +
    (warn ? `<div class="dt-warn">\u26a0 ${esc(warn)}</div>` : "") +
    `<div class="dt-foot">Click to filter \u00b7 drag across days for a range</div>`;
}

function positionTip(ev) {
  const pad = 12;
  const r = dayTip.getBoundingClientRect();
  let x = ev.clientX + pad, y = ev.clientY + pad;
  if (x + r.width > window.innerWidth - 8) x = ev.clientX - r.width - pad;
  if (y + r.height > window.innerHeight - 8) y = ev.clientY - r.height - pad;
  dayTip.style.left = Math.max(8, x) + "px";
  dayTip.style.top = Math.max(8, y) + "px";
}

// Drag selection: press on a day, release on another, and the range between
// them becomes the date filter. A press-and-release on one day is just a click.
let dragFrom = null, dragTo = null, dragging = false;

function paintDragPreview(host) {
  if (!dragFrom) return;
  const lo = dragFrom < dragTo ? dragFrom : dragTo;
  const hi = dragFrom < dragTo ? dragTo : dragFrom;
  for (const el of host.querySelectorAll("[data-date]")) {
    el.classList.toggle("in-drag", el.dataset.date >= lo && el.dataset.date <= hi);
  }
}

function attachDayTips(host, stats) {
  host._dayStats = stats || {};
  if (host._tipsBound) return;   // charts re-render often; listeners bind once
  host._tipsBound = true;
  host.addEventListener("mousemove", ev => {
    const el = ev.target.closest("[data-date]");
    if (!el) { dayTip.hidden = true; return; }
    const iso = el.dataset.date;
    if (dayTip.dataset.for !== iso) {
      dayTip.dataset.for = iso;
      dayTip.innerHTML = dayTipHTML(iso, host._dayStats[iso]);
    }
    dayTip.hidden = false;
    positionTip(ev);
    if (dragging) { dragTo = iso; paintDragPreview(host); }
  });
  host.addEventListener("mouseleave", () => { dayTip.hidden = true; });
  host.addEventListener("mousedown", ev => {
    const el = ev.target.closest("[data-date]");
    if (!el) return;
    dragging = true; dragFrom = dragTo = el.dataset.date;
    ev.preventDefault();
  });
  host.addEventListener("mouseup", ev => {
    if (!dragging) return;
    dragging = false;
    const el = ev.target.closest("[data-date]");
    if (el) dragTo = el.dataset.date;
    for (const n of host.querySelectorAll(".in-drag")) n.classList.remove("in-drag");
    if (dragFrom) applyDayFilter(dragFrom, dragTo);
    dragFrom = dragTo = null;
  });
}
document.addEventListener("mouseup", () => { dragging = false; });

// Remembering the range the reader came from means a day filter is a detour,
// not a dead end.
let prevRange = null;
function applyDayFilter(a, b) {
  const lo = a < b ? a : b, hi = a < b ? b : a;
  if (!prevRange) prevRange = { from: dFrom.value, to: dTo.value };
  dFrom.value = clampDate(lo);
  dTo.value = clampDate(hi);
  render();
  setTab("overview");
  showDayChip(lo, hi);
}
function clearDayFilter() {
  if (prevRange) { dFrom.value = prevRange.from; dTo.value = prevRange.to; prevRange = null; }
  render();
  showDayChip(null);
}
function showDayChip(lo, hi) {
  const chip = document.getElementById("dayChip");
  if (!lo) { chip.hidden = true; return; }
  const label = lo === hi ? lo : lo + " \u2192 " + hi;
  chip.innerHTML = `Showing ${esc(label)} <button class="chip-x" id="dayChipX" title="Back to the previous range">&times;</button>`;
  chip.hidden = false;
  document.getElementById("dayChipX").addEventListener("click", clearDayFilter);
}

// GitHub-style contribution calendar coloured by requests/day (fully recorded).
function renderHeatmap(stats, from, to) {
  stats = stats || {};
  const dailyReq = {};
  for (const k in stats) dailyReq[k] = stats[k].req;
  const start = new Date(from + "T00:00:00Z");
  start.setUTCDate(start.getUTCDate() - start.getUTCDay());   // back to Sunday
  const end = new Date(to + "T00:00:00Z");
  const vals = Object.values(dailyReq).filter(v => v > 0).sort((a, b) => a - b);
  if (end < start || !vals.length) {
    calChart.innerHTML = '<div class="muted">No activity in range.</div>'; return;
  }
  const q = p => vals[Math.min(vals.length - 1, Math.floor(p * vals.length))];
  const t1 = q(0.25), t2 = q(0.5), t3 = q(0.75);
  const CO = ["var(--cal-0)", "var(--cal-1)", "var(--cal-2)", "var(--cal-3)", "var(--cal-4)"];
  const bucket = n => calBucket(n, t1, t2, t3);  const color = n => CO[bucket(n)];
  const MN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const cell = cssNum("--cal-cell", 24), gap = 5, step = cell + gap, padL = 36, padT = 20;
  let cols = 0, cells = "", months = "", lastMonth = -1;
  const cur = new Date(start);
  while (cur <= end) {
    const col = Math.floor((cur - start) / (7 * 86400000));
    const row = cur.getUTCDay();
    cols = Math.max(cols, col);
    const iso = cur.toISOString().slice(0, 10);
    const x = padL + col * step, y = padT + row * step;
    if (iso >= from && iso <= to) {
      const n = dailyReq[iso] || 0;
      const idx = bucket(n);
      const flagged = n > 0 && dayWarning({
        requests: n, aiu: (stats[iso] || {}).aiu, noToken: (stats[iso] || {}).noToken });
      cells += `<rect class="calcell${flagged ? " calwarn" : ""}" data-date="${iso}" x="${x}" y="${y}" width="${cell}" height="${cell}" rx="3" style="fill:${CO[idx]}"></rect>` +
        `<text x="${x + cell / 2}" y="${y + cell / 2 + 3.5}" text-anchor="middle" font-size="10" ` +
        `style="fill:${idx >= 3 ? "#ffffff" : "var(--fg-muted)"}" pointer-events="none">${cur.getUTCDate()}</text>` +
        (flagged
          ? `<text x="${x + cell - 3}" y="${y + 8}" text-anchor="end" font-size="9" ` +
            `style="fill:var(--warn-fg, #9a6700)" pointer-events="none">\u26a0</text>`
          : "");
    }
    const mo = cur.getUTCMonth();
    if (row === 0 && mo !== lastMonth) {
      months += `<text x="${x}" y="${padT - 4}" font-size="10" style="fill:var(--fg-subtle)">${MN[mo]}</text>`;
      lastMonth = mo;
    }
    cur.setUTCDate(cur.getUTCDate() + 1);
  }
  const W = padL + (cols + 1) * step, H = padT + 7 * step;
  const wd = [[1, "Mon"], [3, "Wed"], [5, "Fri"]]
    .map(([r, l]) => `<text x="0" y="${padT + r * step + cell - 1}" font-size="9" style="fill:var(--fg-subtle)">${l}</text>`).join("");
  const legend = `<div class="cal-legend">Less ${CO.map(c => `<span class="cell" style="background:${c}"></span>`).join("")} More</div>`;
  calChart.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${months}${wd}${cells}</svg>${legend}`;
  attachDayTips(calChart, stats);
}

const PALETTE = ["#4e79a7", "#f28e2b", "#59a14f", "#b07aa1", "#e15759", "#76b7b2",
                 "#edc948", "#ff9da7", "#9c755f", "#86bcb6", "#d4a6c8", "#bab0ac"];

function renderTop(perProj) {
  const items = [...perProj].filter(p => p.aiu > 0).sort((a, b) => b.aiu - a.aiu);
  const total = items.reduce((s, p) => s + p.aiu, 0);
  if (!total) { topChart.innerHTML = '<div class="muted">No AIU in range.</div>'; return; }
  const N = 8;
  const top = items.slice(0, N);
  const rest = items.slice(N);
  const restSum = rest.reduce((s, p) => s + p.aiu, 0);
  const segs = top.map((p, i) => ({ name: p.name, aiu: p.aiu, color: PALETTE[i % PALETTE.length] }));
  if (restSum > 0) segs.push({ name: `Other (${rest.length})`, aiu: restSum, color: "#adb5bd" });
  const bar = segs.map(s => {
    const pct = s.aiu / total * 100;
    return `<span class="seg" style="width:${pct.toFixed(2)}%;background:${s.color}" ` +
      `title="${esc(s.name)}: ${fmtAiu(s.aiu)} AIU (${pct.toFixed(1)}%)"></span>`;
  }).join("");
  const legend = segs.map(s => {
    const pct = s.aiu / total * 100;
    return `<div class="lg"><span class="sw" style="background:${s.color}"></span>` +
      `<span class="ln" title="${esc(s.name)}">${esc(s.name)}</span>` +
      `<span class="lp">${pct.toFixed(1)}%</span></div>`;
  }).join("");
  topChart.innerHTML = `<div class="stack">${bar}</div><div class="legend">${legend}</div>`;
}

function renderTable(perProj) {
  const rows = [...perProj].sort((a, b) => b.aiu - a.aiu);
  tblBody.innerHTML = rows.map(p =>
    `<tr class="prj" data-name="${esc(p.name)}">` +
      `<td class="pn" title="${esc(p.name)}"><span class="caret">\u25b8</span> ${esc(p.name)}</td>` +
      `<td class="num">${fmt(p.sessions)}</td>` +
      `<td class="num">${fmt(p.requests)}</td>` +
      `<td class="num">${fmtAiu(p.aiu)}</td>` +
      `<td class="num cost">${fmtUsd(p.aiu)}</td>` +
      `<td class="num">${fmtK(p.in)}</td>` +
      `<td class="num">${fmtK(p.out)}</td></tr>`
  ).join("") ||
    '<tr><td colspan="7" class="muted">No projects in range.</td></tr>';
}

