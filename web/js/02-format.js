// ---- date span ----
// Rebuilt on every data load: the background full scan can widen the span, and
// a partial (quick) report starts narrow.
let allDays = [];
let MIN = "1970-01-01";
let MAX = "1970-01-01";

function clampDate(v) { return clampToSpan(v, MIN, MAX); }

function presetFrom(days) {
  const f = addDays(MAX, -(Number(days) - 1));
  return f < MIN ? MIN : f;
}
function setPreset(days) {
  if (days === "all") { dFrom.value = MIN; dTo.value = MAX; }
  else { dTo.value = MAX; dFrom.value = presetFrom(days); }
}
function markActivePreset() {
  let match = "custom";
  if (dFrom.value === MIN && dTo.value === MAX) match = "all";
  else if (dTo.value === MAX) {
    for (const days of [7, 30, 90]) if (dFrom.value === presetFrom(days)) match = String(days);
  }
  for (const btn of presets.querySelectorAll("button"))
    btn.classList.toggle("active", btn.dataset.days === match);
}

function renderDaily(daily, stats) {
  // one solid bar per active day; contiguous "active days" strip (no gaps).
  const dates = Object.keys(daily).filter(d => (daily[d] || 0) > 0.0001).sort();
  if (!dates.length) { dailyChart.innerHTML = '<div class="muted">No AIU in range.</div>'; return; }
  const max = Math.max(...dates.map(d => daily[d])) || 1;
  const W = 600, H = cssNum("--chart-h", 84), padT = 6, padB = 4, MINH = 2.5;
  const bw = W / dates.length;
  const plot = H - padT - padB;
  let bars = "";
  dates.forEach((d, i) => {
    const val = daily[d];
    const h = Math.max((val / max) * plot, MINH);
    const x = i * bw + 0.5, w = Math.max(bw - 1, 0.8);
    const y = H - padB - h;
    bars += `<rect class="dayhit" data-date="${d}" x="${x.toFixed(1)}" y="${padT}" width="${w.toFixed(1)}" ` +
      `height="${(H - padB - padT).toFixed(1)}" fill="transparent"></rect>` +
      `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" ` +
      `height="${h.toFixed(1)}" style="fill:var(--accent);pointer-events:none"></rect>`;
  });
  dailyChart.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:${H}px">${bars}</svg>`;
  attachDayTips(dailyChart, stats || {});
}

