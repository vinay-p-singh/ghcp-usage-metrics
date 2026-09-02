// ---- partial-report banner + background data channel ----
// A cold scan reads hundreds of megabytes of logs, so the extension paints a
// quick scan of the recent window first and streams the completed history in
// afterwards. Re-rendering in place keeps the reader's tab, filters and scroll.
const partialNotice = document.getElementById("partialNotice");
const partialBody = document.getElementById("partialBody");
function updatePartialBanner() {
  const d = DIAG || {};
  if (!d.partial) { partialNotice.hidden = true; return; }
  const deferred = Object.values(d.sources || {})
    .reduce((s, v) => s + (v.files_deferred || 0), 0);
  partialBody.innerHTML =
    `<b>Showing the last ${d.quick_days} days only.</b> ${fmt(deferred)} older log ` +
    `file${deferred === 1 ? " is" : "s are"} still being read \u2014 totals will grow ` +
    `once the full history finishes loading.`;
  partialNotice.hidden = false;
}

let _toastTimer = 0;
function toast(text) {
  let el = document.getElementById("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    document.body.appendChild(el);
  }
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}

window.addEventListener("message", ev => {
  const msg = ev.data || {};
  if (msg.type !== "data" || !Array.isArray(msg.projects)) return;
  if (msg.diag) DIAG = msg.diag;
  if (msg.generated) refState.dataset.gen = msg.generated;
  // The report now says which store it came from, so the choice stops being
  // pending and the control goes back to reporting the run.
  sourcePending = null;
  syncReportedSettings();
  initData(msg.projects);
  render();
  renderDiagnostics();
  renderFloorNotice();
  renderSourceNotice();
  updatePartialBanner();
  refreshBtn.disabled = false;
  refreshBtn.innerHTML = "&#8635; Refresh data";
  updateRefState();
  if (msg.phase === "full") toast("Full history loaded");
});

updatePartialBanner();

// ---- onboarding notice: agent debug file logging is off ------------------
(function () {
  const notice = document.getElementById("logNotice");
  const body = document.getElementById("logBody");
  const enableBtn = document.getElementById("logEnableBtn");
  const dismiss = document.getElementById("logDismiss");
  if (!notice) return;
  const setup = debugLogSetup(DIAG && DIAG.source);
  let dismissed = false;
  try { dismissed = localStorage.getItem("cpLogNotice") === "off"; } catch (e) {}
  if (setup && !dismissed) {
    body.innerHTML = `<b>Copilot agent debug file logging is disabled.</b> ${esc(setup.body)}`;
    notice.hidden = false;
    if (!vscodeApi) enableBtn.hidden = true;
  }
  enableBtn.addEventListener("click", () => {
    if (vscodeApi) vscodeApi.postMessage({ type: "enableDebugLogs" });
  });
  dismiss.addEventListener("click", () => {
    notice.hidden = true;
    try { localStorage.setItem("cpLogNotice", "off"); } catch (e) {}
  });
})();

// ---- credit-coverage floor notice -----------------------------------------
// Say why the view starts where it does, and make the earlier data one click
// away. Nothing is discarded -- it is just not mixed into a headline that would
// then be comparing complete months against incomplete ones.
function renderFloorNotice() {
  const notice = document.getElementById("floorNotice");
  const body = document.getElementById("floorBody");
  if (!notice || !body) return;
  const cf = (DIAG && DIAG.credit_floor) || {};
  const showing = dFrom.value;
  // The view opens at the start of the floor's month, so compare against that
  // and not the floor itself -- otherwise the notice hides exactly when shown.
  const opensAt = cf.floor ? cf.floor.slice(0, 8) + "01" : "";
  let dismissed = false;
  try { dismissed = localStorage.getItem("cpFloorNotice") === "off"; } catch (e) {}
  if (!cf.floor || !cf.days_before || dismissed || showing < opensAt) {
    notice.hidden = true;
    return;
  }
  const onsets = Object.entries(cf.onsets || {})
    .map(([k, v]) => `${CLIENT_LABEL[k] || k} from ${v}`).join(", ");
  const never = (cf.never_reports || [])
    .map(k => CLIENT_LABEL[k] || k).join(", ");
  body.innerHTML =
    `<b>Showing usage from ${esc(cf.floor)}, when every harness was reporting AI credits.</b> ` +
    `${esc(onsets)}. ${cf.days_before} earlier active day${cf.days_before === 1 ? "" : "s"} ` +
    `(back to ${esc(cf.first_day || "")}) recorded requests but no credits, so including them ` +
    `would compare complete months against incomplete ones. The data is still there.` +
    (never ? ` ${esc(never)} publishes no credit figure at all.` : "");
  notice.hidden = false;
}

(function () {
  const showAll = document.getElementById("floorShowAll");
  const dismiss = document.getElementById("floorDismiss");
  if (showAll) {
    showAll.addEventListener("click", () => {
      floorOverridden = true;
      dFrom.value = MIN;
      dTo.value = MAX;
      rangeChanged();
      renderFloorNotice();
    });
  }
  if (dismiss) {
    dismiss.addEventListener("click", () => {
      document.getElementById("floorNotice").hidden = true;
      try { localStorage.setItem("cpFloorNotice", "off"); } catch (e) {}
    });
  }
})();
renderFloorNotice();

// ---- which store produced these numbers ------------------------------------
// A report built from saved sessions alone is a floor, not a bill, and nothing
// in the figures themselves says so.
function renderSourceNotice() {
  const notice = document.getElementById("sourceNotice");
  const body = document.getElementById("sourceBody");
  if (!notice || !body) return;
  const n = sourceNotice(DIAG && DIAG.source);
  let dismissed = false;
  try { dismissed = localStorage.getItem("cpSourceNotice") === "off"; } catch (e) {}
  if (!n || dismissed) {
    notice.hidden = true;
    return;
  }
  notice.classList.toggle("partial", n.level === "warn");
  body.innerHTML = `<b>${esc(n.title)}.</b> ${esc(n.body)}`;
  notice.hidden = false;
}

(function () {
  const dismiss = document.getElementById("sourceDismiss");
  if (!dismiss) return;
  dismiss.addEventListener("click", () => {
    document.getElementById("sourceNotice").hidden = true;
    try { localStorage.setItem("cpSourceNotice", "off"); } catch (e) {}
  });
})();
renderSourceNotice();

// Tell the extension the message listener is live; anything it produced while
// this page was still loading gets flushed now instead of being lost.
if (vscodeApi) vscodeApi.postMessage({ type: "ready" });