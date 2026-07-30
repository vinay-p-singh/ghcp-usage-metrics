// ---- diagnostics -------------------------------------------------------
// The scan used to swallow its own problems: a deferred log, an unreadable file
// and a source that never stored tokens all looked identical to "no usage".
// This panel reports each one, so a surprising number can be traced to a cause.
const diagPills = document.getElementById("diagPills");
const diagCoverage = document.getElementById("diagCoverage");
const diagSources = document.getElementById("diagSources");
const diagErrors = document.getElementById("diagErrors");
const diagBadge = document.getElementById("diagBadge");
const CLIENT_NAME = { vscode: "VS Code", cli: "Copilot CLI", claude: "Claude Code" };

function diagPill(k, v, sub, cls) {
  return `<div class="pill"><div class="k">${esc(k)}</div>` +
    `<div class="v ${cls || ""}">${v}</div><div class="s">${esc(sub || "")}</div></div>`;
}

function renderDiagnostics() {
  if (!diagPills) return;
  const d = DIAG || {};
  const srcs = d.sources || {};
  const cov = d.coverage || {};
  const rows = d.no_token_rows || [];
  const sum = f => Object.values(srcs).reduce((s, v) => s + (v[f] || 0), 0);
  const failed = sum("files_failed"), badLines = sum("bad_lines");
  const problems = failed + badLines;

  diagBadge.hidden = problems === 0;
  diagBadge.textContent = String(problems);

  const el = d.elapsed || {};
  diagPills.innerHTML =
    diagPill("Scan mode", d.partial ? "Quick" : "Full",
             d.partial ? "last " + d.quick_days + " days" : "complete history",
             d.partial ? "diag-warn" : "diag-ok") +
    diagPill("Scan time", (el.total != null ? el.total + "s" : "\u2014"),
             Object.keys(el).filter(k => k !== "total").map(k => k + " " + el[k] + "s").join(" \u00b7 ")) +
    diagPill("Files read", fmt(sum("files_parsed")), "of " + fmt(sum("files_found")) + " found") +
    diagPill("Deferred", fmt(sum("files_deferred")), "outside the quick window",
             sum("files_deferred") ? "diag-warn" : "") +
    diagPill("Failures", fmt(problems), failed + " files \u00b7 " + badLines + " bad lines",
             problems ? "diag-bad" : "diag-ok") +
    diagPill("No-token requests", fmt(cov.requests_no_tokens || 0),
             (cov.pct_no_tokens || 0) + "% of " + fmt(cov.requests || 0),
             (cov.requests_no_tokens || 0) ? "diag-warn" : "diag-ok");

  // coverage
  if (!cov.requests) {
    diagCoverage.innerHTML = '<div class="muted">No request data in the last scan.</div>';
  } else if (!rows.length) {
    diagCoverage.innerHTML = '<div class="muted">Every recorded request carries token data. Nothing is missing.</div>';
  } else {
    const bc = cov.by_client || {};
    const clientRows = Object.keys(bc).filter(k => bc[k].requests).map(k =>
      `<tr><td>${esc(CLIENT_NAME[k] || k)}</td><td class="num">${fmt(bc[k].requests)}</td>` +
      `<td class="num">${fmt(bc[k].no_tokens)}</td>` +
      `<td class="num">${bc[k].requests ? (bc[k].no_tokens * 100 / bc[k].requests).toFixed(1) : 0}%</td></tr>`).join("");
    const reasons = [...new Set(rows.map(r => r.client))].map(k =>
      `<p class="diag-reason"><b>${esc(CLIENT_NAME[k] || k)}:</b> ${esc(rows.find(r => r.client === k).reason)}</p>`).join("");
    const projRowsHtml = rows.map(r =>
      `<tr><td class="dn" title="${esc(r.project)}">${esc(r.project)}</td>` +
      `<td>${esc(CLIENT_NAME[r.client] || r.client)}</td>` +
      `<td class="num">${fmt(r.requests)}</td><td class="num">${fmt(r.no_tokens)}</td></tr>`).join("");
    diagCoverage.innerHTML =
      `<p class="diag-reason"><b>${fmt(cov.requests_no_tokens)} of ${fmt(cov.requests)} requests ` +
      `(${cov.pct_no_tokens}%)</b> are real calls whose source never recorded token counts. ` +
      `They are counted as requests and contribute 0 credits &mdash; they are not estimated and not dropped.</p>` +
      `<table class="ptable"><thead><tr><th>Harness</th><th class="num">Requests</th>` +
      `<th class="num">No token data</th><th class="num">Share</th></tr></thead><tbody>${clientRows}</tbody></table>` +
      reasons +
      `<div class="ptable-scroll"><table class="ptable"><thead><tr><th>Project</th><th>Harness</th>` +
      `<th class="num">Requests</th><th class="num">No token data</th></tr></thead>` +
      `<tbody>${projRowsHtml}</tbody></table></div>`;
  }

  // sources
  const srcRows = Object.keys(srcs).map(k => {
    const v = srcs[k];
    const roots = (v.roots || []).map(r =>
      `<div class="diag-path">${esc(r.path)} ${r.exists ? "" : "(missing)"}</div>`).join("") || "";
    return `<tr><td>${esc(v.label || k)}${roots}</td>` +
      `<td class="num">${fmt(v.files_found)}</td><td class="num">${fmt(v.files_parsed)}</td>` +
      `<td class="num">${fmt(v.files_deferred)}</td>` +
      `<td class="num ${v.files_failed ? "diag-bad" : ""}">${fmt(v.files_failed)}</td>` +
      `<td class="num ${v.bad_lines ? "diag-warn" : ""}">${fmt(v.bad_lines)}</td></tr>`;
  }).join("");
  diagSources.innerHTML = srcRows
    ? `<table class="ptable"><thead><tr><th>Source</th><th class="num">Found</th><th class="num">Parsed</th>` +
      `<th class="num">Deferred</th><th class="num">Failed</th><th class="num">Bad lines</th></tr></thead>` +
      `<tbody>${srcRows}</tbody></table>`
    : '<div class="muted">No scan record. Regenerate the report to populate diagnostics.</div>';

  // errors
  const errs = d.errors || [];
  diagErrors.innerHTML = errs.length
    ? `<table class="ptable"><thead><tr><th>Source</th><th>File</th><th>Error</th></tr></thead><tbody>` +
      errs.map(e => `<tr><td>${esc(e.source)}</td><td class="diag-path">${esc(e.path)}</td>` +
        `<td class="diag-reason">${esc(e.error)}</td></tr>`).join("") + `</tbody></table>`
    : (badLines
        ? `<div class="muted">No unreadable files. ${fmt(badLines)} individual log line${badLines === 1 ? " was" : "s were"} malformed and skipped &mdash; those requests are not counted anywhere.</div>`
        : '<div class="muted">No read or parse failures.</div>');
}

const diagCopy = document.getElementById("diagCopy");
const diagStatus = document.getElementById("diagStatus");
if (diagCopy) {
  diagCopy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(DIAG, null, 2));
      diagStatus.className = "cfg-status ok";
      diagStatus.textContent = "Copied \u2713";
    } catch (e) {
      diagStatus.className = "cfg-status err";
      diagStatus.textContent = "Clipboard blocked \u2014 see out/diagnostics.json";
    }
  });
}

applyCfgToControls();
initData(DATA);
setTab(localStorage.getItem("cpTab") || "overview");
render();
renderDiagnostics();
_ready = true;

