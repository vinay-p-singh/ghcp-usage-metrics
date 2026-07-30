
let DATA = __DATA__;
let DIAG = __DIAG__;
const byName = {};

// ---- hard filter (Config tab) — JSON config mirroring config.json ----
const CFG_KEY = "cpConfig";
const DEFAULT_CFG = { since: null, until: null, autoRefreshMinutes: 0,
  budget: { monthlyAiu: null },
  cost: { usdPerAiu: null },
  hideEmptyProjects: true,
  show: { diagnostics: true },
  exclude: { projects: [], project_prefixes: [], clients: [], models: [], agents: [] } };
function loadCfg() {
  try {
    const raw = localStorage.getItem(CFG_KEY);
    if (raw) return normCfg(JSON.parse(raw));
    const old = JSON.parse(localStorage.getItem("cpExclude") || "[]");
    if (Array.isArray(old) && old.length) return normCfg({ exclude: { projects: old } });
  } catch (e) {}
  return normCfg(DEFAULT_CFG);
}
function saveCfg() { try { localStorage.setItem(CFG_KEY, JSON.stringify(CFG)); } catch (e) {} }
let CFG = loadCfg();
function excludedClients() { return aliasClients(CFG.exclude.clients); }
function isExcluded(name) {
  return matchesAny(name, CFG.exclude.projects, CFG.exclude.project_prefixes);
}
function isModelExcluded(name) { const n = _lc(name); return CFG.exclude.models.some(x => x && n === _lc(x)); }
// Models the reader has unticked in the sidebar -- the twin of the project
// checkboxes, and just as complete: the logs record a date and a model on the
// same event, so `by_dm` lets an untick re-scope every figure, headline credits
// included. Sessions are the one exception, because one can span models.
const MODEL_OFF = new Set();
function isModelOff(name) { return MODEL_OFF.has(name); }
function modelHidden(name) { return isModelExcluded(name) || isModelOff(name); }
function isAgentExcluded(name) { const n = _lc(name); return CFG.exclude.agents.some(x => x && n === _lc(x)); }
function diagnosticsOn() { return CFG.show.diagnostics !== false; }
function hideEmptyOn() { return CFG.hideEmptyProjects !== false; }

// ---- cost ----
// There is no locally readable price for an AI credit, so nothing is shown
// until a rate is configured. Everything derived from it is a projection of
// recorded credits at YOUR rate, never a bill.
function costRate() {
  return (CFG.cost && typeof CFG.cost.usdPerAiu === "number" && CFG.cost.usdPerAiu > 0) ? CFG.cost.usdPerAiu : 0;
}
function costOn() { return costRate() > 0; }
function fmtUsd(aiu) { return usdFrom(aiu, costRate()); }
function applyCostVisibility() { document.body.classList.toggle("nocost", !costOn()); }
function applyCfgToControls() {
  const ex = excludedClients();
  cbVs.disabled = ex.has("vs"); if (ex.has("vs")) cbVs.checked = false;
  cbCli.disabled = ex.has("cli"); if (ex.has("cli")) cbCli.checked = false;
  cbClaude.disabled = ex.has("cla"); if (ex.has("cla")) cbClaude.checked = false;
  applyDiagVisibility();
}

// Diagnostics is a troubleshooting surface, not a daily one. When it is turned
// off the tab has to go too -- leaving a button that opens nothing is worse
// than not offering it. A reader sitting on the tab when it is switched off is
// moved back to Overview rather than left on a blank panel.
function applyDiagVisibility() {
  const on = diagnosticsOn();
  const btn = document.querySelector('#tabs .tab[data-tab="diagnostics"]');
  if (btn) btn.hidden = !on;
  if (!on && btn && btn.classList.contains("active")) setTab("overview");
}

const cbVs       = document.getElementById("cbVs");
const cbCli      = document.getElementById("cbCli");
const cbClaude   = document.getElementById("cbClaude");
const badgeVs    = document.getElementById("badgeVs");
const badgeCli   = document.getElementById("badgeCli");
const badgeCla   = document.getElementById("badgeCla");
const projSearch = document.getElementById("projSearch");
const projBody   = document.getElementById("projBody");
const projEmpty  = document.getElementById("projEmpty");
const projReveal = document.getElementById("projReveal");
const projClear  = document.getElementById("projClear");
const presets    = document.getElementById("presets");
const dFrom      = document.getElementById("dFrom");
const dTo        = document.getElementById("dTo");
const pAiu  = document.getElementById("pAiu");
const pCost = document.getElementById("pCost");
const pCostSub = document.getElementById("pCostSub");
const pReq  = document.getElementById("pReq");
const pIn   = document.getElementById("pIn");
const pInSub = document.getElementById("pInSub");
const pOut  = document.getElementById("pOut");
const pOutSub = document.getElementById("pOutSub");
const pProj = document.getElementById("pProj");
const pDays = document.getElementById("pDays");
const dailyChart = document.getElementById("dailyChart");
const calChart   = document.getElementById("calChart");
const pieClient  = document.getElementById("pieClient");
const pieModel   = document.getElementById("pieModel");
const pieProj    = document.getElementById("pieProj");
const pieLang    = document.getElementById("pieLang");
const topChart   = document.getElementById("topChart");
const tblBody    = document.getElementById("tblBody");
const mList      = document.getElementById("mList");
const mSummary   = document.getElementById("mSummary");
const agentBody   = document.getElementById("agentBody");
const agentSignal = document.getElementById("agentSignal");
const pieAgent    = document.getElementById("pieAgent");
const skillBody   = document.getElementById("skillBody");
const pieSkill    = document.getElementById("pieSkill");
const fcView      = document.getElementById("fcView");
const stView      = document.getElementById("stView");
let AGENT_MODELS = {};
let CUR = { vs: true, cli: true, cla: true, from: "0000", to: "9999" };
let curPerProj = [];

