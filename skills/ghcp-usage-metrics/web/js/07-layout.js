// ---- responsive tiers -------------------------------------------------
// Size tiers are bootstrapped by the inline script at the top of <body>, which
// is where `applySize` / `isNarrow` / `sizeTier` live. Only the pieces the
// renderers need are declared here.
let _ready = false, _sizeRaf = 0;
// last render's inputs, kept so a tier change can redraw just the SVG charts
let _lastAgg = null, _lastScope = null;
function cssNum(name, dflt) {
  const v = parseFloat(getComputedStyle(document.body).getPropertyValue(name));
  return Number.isFinite(v) ? v : dflt;
}

// ---- collapsible filters sidebar (usable in the narrow VS Code webview) ----
// Manual toggle wins and persists; with no saved preference the sidebar
// auto-collapses below the responsive breakpoint and re-opens when widened.
const filtersBtn = document.getElementById("filtersBtn");
const SIDEBAR_KEY = "cpSidebar";
function applySidebar(collapsed) {
  document.body.classList.toggle("sidebar-collapsed", collapsed);
  filtersBtn.setAttribute("aria-pressed", String(!collapsed));
  filtersBtn.classList.toggle("active", !collapsed);
}
function sidebarPref() { try { return localStorage.getItem(SIDEBAR_KEY); } catch (e) { return null; } }
function initSidebar() {
  const pref = sidebarPref();
  if (pref === "collapsed") applySidebar(true);
  else if (pref === "open") applySidebar(false);
  else applySidebar(isNarrow());
}
filtersBtn.addEventListener("click", () => {
  const collapsed = !document.body.classList.contains("sidebar-collapsed");
  applySidebar(collapsed);
  try { localStorage.setItem(SIDEBAR_KEY, collapsed ? "collapsed" : "open"); } catch (e) {}
});
function onViewportResize() {
  cancelAnimationFrame(_sizeRaf);
  _sizeRaf = requestAnimationFrame(() => {
    const changed = applySize();
    if (!sidebarPref()) applySidebar(isNarrow());
    if (changed && _ready) redrawScaled();
  });
}
if (window.ResizeObserver) new ResizeObserver(onViewportResize).observe(document.documentElement);
window.addEventListener("resize", onViewportResize);
initSidebar();

