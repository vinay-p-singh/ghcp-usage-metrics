// ---- theme (mode + accent) ----
const themeBtn = document.getElementById("themeBtn");
const themePop = document.getElementById("themePop");
const tpModes = document.getElementById("tpModes");
const tpAccents = document.getElementById("tpAccents");
function applyMode(m) {
  const pref = applyModeTokens(m);
  for (const b of tpModes.children) b.classList.toggle("active", b.dataset.mode === pref);
}
function applyAccent(a) {
  const pref = applyAccentTokens(a);
  for (const b of tpAccents.children) b.classList.toggle("active", b.dataset.accent === pref);
}
applyMode(lsGet("cpTheme") || "auto");
applyAccent(lsGet("cpAccent") || "blue");
// Colours track the host live because they are var() references, but the
// light/dark stamp that drives `color-scheme` has to be recomputed when the
// user switches editor theme (or OS appearance, when opened standalone).
if (window.MutationObserver) {
  new MutationObserver(() => { if (_modePref === "auto") applyMode("auto"); })
    .observe(document.body, { attributes: true, attributeFilter: ["class", "data-vscode-theme-kind"] });
}
try {
  matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () => { if (_modePref === "auto") applyMode("auto"); });
} catch (e) {}
themeBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  const open = themePop.hidden;
  themePop.hidden = !open;
  themeBtn.setAttribute("aria-expanded", String(open));
});
tpModes.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-mode]"); if (!b) return;
  localStorage.setItem("cpTheme", b.dataset.mode); applyMode(b.dataset.mode);
});
tpAccents.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-accent]"); if (!b) return;
  localStorage.setItem("cpAccent", b.dataset.accent); applyAccent(b.dataset.accent);
});
document.addEventListener("click", (e) => {
  if (!themePop.hidden && !e.target.closest(".themewrap")) {
    themePop.hidden = true; themeBtn.setAttribute("aria-expanded", "false");
  }
});

// ---- export CSV (current in-scope per-project rows) ----
document.getElementById("csvBtn").addEventListener("click", () => {
  const rows = [["Project", "Sessions", "Requests", "AIU", "Input", "Output"]];
  for (const p of [...curPerProj].sort((a, b) => b.aiu - a.aiu))
    rows.push([p.name, p.sessions, p.requests, p.aiu, p.in, p.out]);
  const csv = rows.map(r => r.map(c => {
    const s = String(c);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }).join(",")).join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = "ghcp-usage.csv";
  a.click();
  URL.revokeObjectURL(a.href);
});

// ---- config tab (JSON hard filter) + live refresh ----
const cfgJson = document.getElementById("cfgJson");
const cfgStatus = document.getElementById("cfgStatus");
const cfgTextFromCfg = () => JSON.stringify(CFG, null, 2);

// A confirmation that outlives the action it confirms stops meaning anything --
// come back to the tab tomorrow and it still reads "Saved". Successes retire
// themselves; failures stay until the next attempt.
let statusTimer = null;
function clearStatuses() {
  clearTimeout(statusTimer);
  for (const el of [cfgStatus, qsStatus]) { el.className = "cfg-status"; el.textContent = ""; }
}
function setStatus(el, cls, msg) {
  el.className = "cfg-status " + cls;
  el.textContent = msg;
  clearTimeout(statusTimer);
  if (cls === "ok") statusTimer = setTimeout(clearStatuses, 3000);
}
function setCfgStatus(cls, msg) { setStatus(cfgStatus, cls, msg); }
document.getElementById("tabs").addEventListener("click", clearStatuses);
cfgBtn.addEventListener("click", clearStatuses);

// ---- quick settings ----
// The JSON editor stays the full surface; this form covers the few fields that
// actually get changed, so the common cases need no JSON at all.
const qs = {
  since: document.getElementById("qsSince"),
  until: document.getElementById("qsUntil"),
  cost: document.getElementById("qsCost"),
  budget: document.getElementById("qsBudget"),
  auto: document.getElementById("qsAuto"),
  hideEmpty: document.getElementById("qsHideEmpty"),
  diag: document.getElementById("qsDiag")
};
const qsStatus = document.getElementById("qsStatus");
function syncQuickSettings() {
  qs.since.value = CFG.since || "";
  qs.until.value = CFG.until || "";
  qs.cost.value = (CFG.cost && CFG.cost.usdPerAiu) || "";
  qs.budget.value = (CFG.budget && CFG.budget.monthlyAiu) || "";
  qs.auto.value = CFG.autoRefreshMinutes || 0;
  qs.hideEmpty.checked = hideEmptyOn();
  qs.diag.checked = diagnosticsOn();
}
function applyCfgEverywhere() {
  cfgJson.value = cfgTextFromCfg();
  syncQuickSettings();
  saveCfg();
  applyCfgToControls();
  initData(DATA);
  render();
  setupAutoRefresh();
}
document.getElementById("qsApply").addEventListener("click", () => {
  const num = el => { const v = parseFloat(el.value); return Number.isFinite(v) && v > 0 ? v : null; };
  CFG = normCfg(Object.assign({}, CFG, {
    since: qs.since.value || null,
    until: qs.until.value || null,
    cost: { usdPerAiu: num(qs.cost) },
    budget: { monthlyAiu: num(qs.budget) },
    autoRefreshMinutes: Math.max(0, parseFloat(qs.auto.value) || 0),
    hideEmptyProjects: qs.hideEmpty.checked,
    show: { diagnostics: qs.diag.checked }
  }));
  applyCfgEverywhere();
  setStatus(qsStatus, "ok", "Saved \u2713");
});

cfgJson.value = cfgTextFromCfg();
syncQuickSettings();
document.getElementById("cfgApply").addEventListener("click", () => {
  let parsed;
  try { parsed = JSON.parse(cfgJson.value); }
  catch (e) { setCfgStatus("err", "Invalid JSON: " + e.message); return; }
  CFG = normCfg(parsed);
  applyCfgEverywhere();
  setCfgStatus("ok", "Applied \u2713 saved to this browser");
});
document.getElementById("cfgReset").addEventListener("click", () => {
  CFG = normCfg(DEFAULT_CFG);
  prevRange = null;
  showDayChip(null);
  dFrom.value = dTo.value = "";   // re-open to the full span the new config allows
  applyCfgEverywhere();
  setCfgStatus("ok", "Reset \u2713 all filters cleared");
});
document.getElementById("cfgDownload").addEventListener("click", () => {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([cfgTextFromCfg()], { type: "application/json" }));
  a.download = "config.json";
  a.click();
  URL.revokeObjectURL(a.href);
  setCfgStatus("ok", "Downloaded config.json \u2713 drop it in the repo root");
});

// refresh: re-extract live inside the VS Code panel, else reload the static report
const vscodeApi = (typeof acquireVsCodeApi !== "undefined") ? acquireVsCodeApi() : null;
const refreshBtn = document.getElementById("refreshBtn");
const refState = document.getElementById("refState");
refreshBtn.title = vscodeApi
  ? "Re-scan your Copilot logs and reload with fresh data"
  : "Reload this report (re-run  python usage.py  first to regenerate the data)";
function triggerRefresh() {
  refreshBtn.disabled = true;
  refreshBtn.textContent = "Refreshing\u2026";
  if (vscodeApi) vscodeApi.postMessage({ type: "refresh" });
  else location.reload();
}
refreshBtn.addEventListener("click", triggerRefresh);

// header status line + configurable auto-refresh ("motor refresh")
let autoTimer = null;
function updateRefState() {
  const gen = refState.dataset.gen || "";
  const n = Number(CFG.autoRefreshMinutes) || 0;
  const parts = [];
  if (gen) parts.push("Updated " + gen);
  parts.push(n > 0 ? "auto-refresh every " + n + " min" : "auto-refresh off");
  refState.textContent = parts.join(" \u00b7 ");
}
function setupAutoRefresh() {
  if (autoTimer) { clearInterval(autoTimer); autoTimer = null; }
  const n = Number(CFG.autoRefreshMinutes) || 0;
  if (n > 0) autoTimer = setInterval(triggerRefresh, n * 60000);
  updateRefState();
}
setupAutoRefresh();

