
/* Boot. Runs as the first child of <body> -- before any content paints -- so
   the opening frame already carries the right size tier and theme. Doing this
   at the end of the page instead would flash the desktop layout in a narrow
   panel, and the light palette inside a dark editor. The main script below
   reuses these globals rather than duplicating the logic. */
var SIZE_STEPS = [["xs", 560], ["sm", 820], ["md", 1280], ["lg", 1680]];
var THEME_MODES = ["auto", "light", "dim", "dark", "contrast"];
var THEME_ACCENTS = ["blue", "violet", "teal", "amber", "rose"];
var _modePref = "auto";
function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
function measuredWidth() {
  // documentElement, not body: body padding is itself tier-driven, so
  // measuring body would let the layout oscillate around a boundary.
  return document.documentElement.clientWidth || window.innerWidth || 1024;
}
function sizeTier(w) {
  for (var i = 0; i < SIZE_STEPS.length; i++) if (w < SIZE_STEPS[i][1]) return SIZE_STEPS[i][0];
  return "xl";
}
function isNarrow() { var t = document.body.dataset.size; return t === "xs" || t === "sm"; }
function applySize() {
  var t = sizeTier(measuredWidth());
  if (document.body.dataset.size === t) return false;
  document.body.dataset.size = t;
  return true;
}
// VS Code stamps its theme kind onto the webview body; absence of that marker
// AND of the --vscode-* palette means we are a standalone page in a browser.
function hostKind() {
  var k = document.body.dataset.vscodeThemeKind || "";
  if (k) return k;
  var m = /vscode-(high-contrast-light|high-contrast|dark|light)/.exec(document.body.className || "");
  return m ? "vscode-" + m[1] : "";
}
function hasHostPalette() {
  try { return !!getComputedStyle(document.body).getPropertyValue("--vscode-editor-background").trim(); }
  catch (e) { return false; }
}
// fallback when the palette exists but the kind marker does not: resolve the
// editor background through a throwaway element so we always read plain rgb()
function paletteIsDark() {
  try {
    var p = document.createElement("span");
    p.style.cssText = "position:absolute;visibility:hidden;background:var(--vscode-editor-background,#fff)";
    document.body.appendChild(p);
    var c = getComputedStyle(p).backgroundColor || "";
    p.remove();
    var n = c.match(/\d+(?:\.\d+)?/g);
    if (!n || n.length < 3) return false;
    return (0.299 * n[0] + 0.587 * n[1] + 0.114 * n[2]) < 128;
  } catch (e) { return false; }
}
function resolveMode(m) {
  if (m !== "auto") return m;
  if (hasHostPalette()) return "auto";
  // standalone browser: nothing to inherit, so mirror the OS preference with
  // our own surfaces rather than pinning everyone to the light default
  try { return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"; }
  catch (e) { return "light"; }
}
function applyModeTokens(m) {
  if (THEME_MODES.indexOf(m) < 0) m = "auto";
  _modePref = m;
  var eff = resolveMode(m);
  document.body.dataset.theme = eff;
  if (eff === "auto") {
    var k = hostKind();
    var dark = k ? /dark|high-contrast$/.test(k) : paletteIsDark();
    document.body.dataset.hostKind = dark ? "dark" : "light";
  } else {
    delete document.body.dataset.hostKind;
  }
  return m;
}
function applyAccentTokens(a) {
  if (THEME_ACCENTS.indexOf(a) < 0) a = "blue";
  document.body.dataset.accent = a;
  return a;
}
applySize();
applyModeTokens(lsGet("cpTheme") || "auto");
applyAccentTokens(lsGet("cpAccent") || "blue");
