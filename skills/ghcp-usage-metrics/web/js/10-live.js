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
  initData(msg.projects);
  render();
  renderDiagnostics();
  updatePartialBanner();
  refreshBtn.disabled = false;
  refreshBtn.innerHTML = "&#8635; Refresh data";
  updateRefState();
  if (msg.phase === "full") toast("Full history loaded");
});

updatePartialBanner();

// ---- onboarding notice: no token/AIU data means Copilot Chat logging is off ----
(function () {
  const notice = document.getElementById("logNotice");
  const enableBtn = document.getElementById("logEnableBtn");
  const dismiss = document.getElementById("logDismiss");
  if (!notice) return;
  let hasTokens = false;
  for (const d of DATA) {
    for (const cl of [d.vscode, d.cli, d.claude]) {
      for (const k in (cl.by_day || {})) {
        const b = cl.by_day[k];
        if ((b.aiu || 0) > 0 || (b.in || 0) > 0) { hasTokens = true; break; }
      }
      if (hasTokens) break;
    }
    if (hasTokens) break;
  }
  let dismissed = false;
  try { dismissed = localStorage.getItem("cpLogNotice") === "off"; } catch (e) {}
  if (DATA.length && !hasTokens && !dismissed) {
    notice.hidden = false;
    if (!vscodeApi) enableBtn.hidden = true;   // only actionable inside the extension
  }
  enableBtn.addEventListener("click", () => { if (vscodeApi) vscodeApi.postMessage({ type: "diagnostics" }); });
  dismiss.addEventListener("click", () => {
    notice.hidden = true;
    try { localStorage.setItem("cpLogNotice", "off"); } catch (e) {}
  });
})();

// Tell the extension the message listener is live; anything it produced while
// this page was still loading gets flushed now instead of being lost.
if (vscodeApi) vscodeApi.postMessage({ type: "ready" });
