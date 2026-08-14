// Copilot Usage & AIU Metrics — VS Code extension entry point.
//
// Architecture: the Python extractor (usage.py) remains the single source of
// truth. This extension does NOT re-implement extraction. It runs
//   python usage.py
// which writes out/dashboard.html, then hosts that self-contained report in a
// webview. The dashboard's "Refresh data" button posts { type: 'refresh' };
// we re-run the extractor and reload the webview with the fresh report.

import * as vscode from "vscode";
import * as cp from "child_process";
import * as fs from "fs";
import * as path from "path";

let panel: vscode.WebviewPanel | undefined;

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("ghcpUsage.openDashboard", () => openDashboard(context)),
    vscode.commands.registerCommand("ghcpUsage.refresh", async () => {
      const root = findRepoRoot(context);
      if (root && panel) {
        await safeRefresh(root);
      } else {
        await openDashboard(context);
      }
    }),
    vscode.commands.registerCommand("ghcpUsage.diagnostics", () => runDiagnostics(context))
  );
}

export function deactivate(): void {
  /* no-op */
}

let diagChannel: vscode.OutputChannel | undefined;

// Report what the extractor can actually see locally, so it's clear WHY a
// machine may show only request counts. Token/AIU data comes from fields
// Copilot Chat writes into its own request logs (debug-logs / chatSessions);
// when those are rotated/trimmed only request counts survive. This is not a
// log-level setting — the diagnostics make the real state explicit.
async function runDiagnostics(context: vscode.ExtensionContext): Promise<void> {
  const root = findRepoRoot(context);
  if (!root) {
    vscode.window.showErrorMessage(
      "Copilot Usage: could not find usage.py. Open the ghcp-usage-metrics folder, " +
        "or set ghcpUsage.repoPath to the folder that contains usage.py."
    );
    return;
  }
  const py = setting<string>("pythonPath", "python");
  if (!(await pythonOk(py))) {
    vscode.window.showErrorMessage(`Copilot Usage: Python not found (tried "${py}").`);
    return;
  }
  let info: DiagInfo;
  try {
    const raw = await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: "Copilot Usage: collecting diagnostics\u2026" },
      () => runCapture(py, root, ["usage.py", "--diagnostics"])
    );
    info = JSON.parse(raw) as DiagInfo;
  } catch (e: unknown) {
    await reportFailure(root, "diagnostics could not be collected", e);
    return;
  }
  const ch = (diagChannel ??= vscode.window.createOutputChannel("Copilot Usage"));
  ch.clear();
  ch.appendLine("Copilot Usage \u2014 Diagnostics");
  ch.appendLine("");
  ch.appendLine(`APPDATA: ${info.appdata}`);
  ch.appendLine(`VS Code variants found: ${(info.vscode_variants ?? []).join(", ") || "none"}`);
  for (const r of info.roots ?? []) {
    ch.appendLine(`  scanned root: ${r.path}  (exists: ${r.exists})`);
  }
  ch.appendLine("");
  ch.appendLine(`Workspaces: ${info.workspaces}`);
  ch.appendLine(
    `Debug-log sessions (main.jsonl): ${info.debug_log_sessions}  ` +
      `(with token data: ${info.main_jsonl_with_tokens})`
  );
  ch.appendLine(
    `chatSessions files: ${info.chat_files}  (with token/credit data: ${info.chat_files_with_tokens})`
  );
  ch.appendLine("");
  if (info.has_token_data) {
    ch.appendLine(
      "Token/AIU data IS present locally. If the dashboard still shows only request " +
        "counts, it's a parse/scope issue \u2014 please share this output."
    );
  } else {
    ch.appendLine("No token/AIU data is retained locally for these sessions.");
    ch.appendLine(
      "Tokens & AI-credits come from fields Copilot Chat writes into its own request " +
        "logs (debug-logs main.jsonl / chatSessions). Older sessions get trimmed and " +
        "debug logs rotate, so only request counts survive. This is NOT a log-level " +
        "setting \u2014 new Copilot activity will populate tokens going forward."
    );
  }
  ch.show(true);
  vscode.window.showInformationMessage(
    "Copilot Usage diagnostics: " +
      (info.has_token_data
        ? `token data found (${info.main_jsonl_with_tokens} logs + ${info.chat_files_with_tokens} sessions).`
        : "no token/AIU data retained locally \u2014 see the Copilot Usage output for why.")
  );
}

interface DiagInfo {
  appdata: string;
  vscode_variants: string[];
  roots: { path: string; exists: boolean }[];
  workspaces: number;
  debug_log_sessions: number;
  main_jsonl_with_tokens: number;
  chat_files: number;
  chat_files_with_tokens: number;
  has_token_data: boolean;
}

function setting<T>(key: string, def: T): T {
  return vscode.workspace.getConfiguration("ghcpUsage").get<T>(key, def);
}

// Locate the folder that holds usage.py: explicit setting, then any open
// workspace folder, then the parent of this extension (repo/extension -> repo).
function findRepoRoot(context: vscode.ExtensionContext): string | undefined {
  const configured = setting<string>("repoPath", "").trim();
  if (configured && fs.existsSync(path.join(configured, "usage.py"))) {
    return configured;
  }
  for (const folder of vscode.workspace.workspaceFolders ?? []) {
    if (fs.existsSync(path.join(folder.uri.fsPath, "usage.py"))) {
      return folder.uri.fsPath;
    }
  }
  const up = path.resolve(context.extensionPath, "..");
  if (fs.existsSync(path.join(up, "usage.py"))) {
    return up;
  }
  // packaged .vsix: Python bundled under the extension's own py/ folder
  const bundled = path.join(context.extensionPath, "py");
  if (fs.existsSync(path.join(bundled, "usage.py"))) {
    return bundled;
  }
  return undefined;
}

// Probe that the configured interpreter runs at all (`python --version`). The
// extractor is stdlib-only, so a working Python 3.x is the sole prerequisite.
function pythonOk(py: string): Promise<boolean> {
  return new Promise((resolve) => {
    cp.execFile(py, ["--version"], { windowsHide: true }, (err) => resolve(!err));
  });
}

// Run `python usage.py <args>` and resolve with its stdout (for --diagnostics).
function runCapture(py: string, root: string, args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    cp.execFile(
      py,
      args,
      { cwd: root, windowsHide: true, maxBuffer: 64 * 1024 * 1024 },
      (err, stdout, stderr) => {
        if (err) {
          reject(new Error((stderr || err.message || String(err)).trim()));
        } else {
          resolve(stdout);
        }
      }
    );
  });
}

// Run `python usage.py <args>` in the repo root. Resolves once out/dashboard.html is
// (re)written; rejects with the captured stderr on failure.
function runExtractor(root: string, args: string[] = []): Promise<void> {
  const py = setting<string>("pythonPath", "python");
  return new Promise((resolve, reject) => {
    cp.execFile(
      py,
      ["usage.py", ...args],
      { cwd: root, windowsHide: true, maxBuffer: 64 * 1024 * 1024 },
      (err, _stdout, stderr) => {
        if (err) {
          reject(new Error((stderr || err.message || String(err)).trim()));
        } else {
          resolve();
        }
      }
    );
  });
}

interface DataMsg {
  type: "data";
  phase: "quick" | "full";
  projects: unknown;
  diag: unknown;
  generated: string;
}

// The webview only starts listening once its script has run, so data produced
// before that would be dropped. Buffer the newest payload until it says ready.
let webviewReady = false;
let pendingData: DataMsg | undefined;

function pushData(msg: DataMsg): void {
  if (panel && webviewReady) {
    void panel.webview.postMessage(msg);
  } else {
    pendingData = msg;
  }
}

function flushPending(): void {
  if (panel && pendingData) {
    void panel.webview.postMessage(pendingData);
    pendingData = undefined;
  }
}

function readJson(root: string, file: string): unknown {
  try {
    return JSON.parse(fs.readFileSync(path.join(root, "out", file), "utf8"));
  } catch {
    return undefined;
  }
}

// Send the freshly written report data to the open panel without replacing its
// HTML, so the reader keeps their tab, filters and scroll position.
function sendReport(root: string, phase: "quick" | "full"): void {
  const projects = readJson(root, "projects.json");
  if (!Array.isArray(projects)) {
    return;
  }
  pushData({
    type: "data",
    phase,
    projects,
    diag: readJson(root, "diagnostics.json"),
    generated: new Date().toLocaleString()
  });
}

function loadReport(root: string, webview: vscode.Webview): string {
  const reportPath = path.join(root, "out", "dashboard.html");
  let html = fs.readFileSync(reportPath, "utf8");
  return html.replace("<head>", "<head>\n" + cspMeta(webview));
}

// Self-contained report CSP: inline style/script + data/blob URIs, no remote.
function cspMeta(webview: vscode.Webview): string {
  return (
    '<meta http-equiv="Content-Security-Policy" content="' +
    "default-src 'none'; " +
    `img-src ${webview.cspSource} data: blob:; ` +
    `style-src ${webview.cspSource} 'unsafe-inline'; ` +
    `script-src ${webview.cspSource} 'unsafe-inline'; ` +
    "font-src data:; connect-src 'none';\">"
  );
}

// Instant placeholder shown while the first scan runs (no prior report yet).
function loadingHtml(webview: vscode.Webview): string {
  return (
    '<!doctype html><html><head><meta charset="utf-8">' + cspMeta(webview) +
    "<style>body{font:14px system-ui,'Segoe UI',sans-serif;background:#1f2335;color:#c0caf5;" +
    "display:flex;align-items:center;justify-content:center;height:100vh;margin:0}" +
    ".box{text-align:center;max-width:340px;padding:0 20px}" +
    ".spin{width:34px;height:34px;border:3px solid #3b4261;border-top-color:#3b82f6;" +
    "border-radius:50%;animation:s .8s linear infinite;margin:0 auto 16px}" +
    "@keyframes s{to{transform:rotate(360deg)}}" +
    ".sub{color:#7982a9;font-size:12px;margin-top:8px;line-height:1.5}</style></head>" +
    '<body><div class="box"><div class="spin"></div>' +
    "<div>Scanning your Copilot logs\u2026</div>" +
    '<div class="sub">The first scan can take a little while. Later opens show the ' +
    "previous report instantly and refresh in the background.</div></div></body></html>"
  );
}

// Replacing the HTML restarts the webview's script, so any queued payload is
// stale and the ready handshake has to happen again.
function setHtml(target: vscode.WebviewPanel, html: string): void {
  webviewReady = false;
  pendingData = undefined;
  target.webview.html = html;
}

async function refreshInto(root: string): Promise<void> {
  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Window, title: "Copilot Usage: scanning Copilot logs…" },
    async () => runExtractor(root)
  );
  sendReport(root, "full");
}

async function safeRefresh(root: string): Promise<void> {
  if (!panel) {
    return;
  }
  try {
    await refreshInto(root);
  } catch (e: unknown) {
    await reportFailure(root, "the refresh could not finish", e);
  }
}

async function openDashboard(context: vscode.ExtensionContext): Promise<void> {
  const root = findRepoRoot(context);
  if (!root) {
    vscode.window.showErrorMessage(
      "Copilot Usage: could not find usage.py. Open the ghcp-usage-metrics folder, " +
        "or set ghcpUsage.repoPath to the folder that contains usage.py."
    );
    return;
  }

  const py = setting<string>("pythonPath", "python");
  if (!(await pythonOk(py))) {
    const pick = await vscode.window.showErrorMessage(
      `Copilot Usage: Python not found (tried "${py}"). This extension needs ` +
        "Python 3.8+ on your PATH to scan your Copilot logs (no pip packages required).",
      "Open Settings"
    );
    if (pick === "Open Settings") {
      void vscode.commands.executeCommand("workbench.action.openSettings", "ghcpUsage.pythonPath");
    }
    return;
  }

  if (panel) {
    panel.reveal(vscode.ViewColumn.Active);
    await safeRefresh(root);
    return;
  }

  panel = vscode.window.createWebviewPanel(
    "ghcpUsage",
    "Copilot Usage Metrics",
    vscode.ViewColumn.Active,
    { enableScripts: true, retainContextWhenHidden: true }
  );
  panel.onDidDispose(() => {
    panel = undefined;
    webviewReady = false;
    pendingData = undefined;
  });
  panel.webview.onDidReceiveMessage(
    async (msg: { type?: string }) => {
      if (msg?.type === "ready") {
        webviewReady = true;
        flushPending();
      } else if (msg?.type === "refresh") {
        await safeRefresh(root);
      } else if (msg?.type === "diagnostics") {
        await runDiagnostics(context);
      }
    },
    undefined,
    context.subscriptions
  );

  // Paint something usable immediately, then complete the data in the
  // background. A previous report is already the whole history, so it wins; with
  // no report at all we run a quick scan of the recent window first rather than
  // making the reader wait out a cold full scan behind a spinner.
  const reportPath = path.join(root, "out", "dashboard.html");
  webviewReady = false;
  pendingData = undefined;
  const hadReport = fs.existsSync(reportPath);
  if (hadReport) {
    try {
      setHtml(panel, loadReport(root, panel.webview));
    } catch {
      setHtml(panel, loadingHtml(panel.webview));
    }
  } else {
    setHtml(panel, loadingHtml(panel.webview));
    const days = Math.max(1, setting<number>("quickScanDays", 10));
    try {
      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Window,
          title: `Copilot Usage: scanning the last ${days} days\u2026`
        },
        () => runExtractor(root, ["--quick", String(days)])
      );
      setHtml(panel, loadReport(root, panel.webview));
    } catch (e: unknown) {
      await reportFailure(root, "the first scan could not finish", e);
    }
  }
  await safeRefresh(root);
}

function errMsg(e: unknown): string {
  if (e instanceof Error) {
    return e.message;
  }
  return String(e);
}

// usage.py writes the full traceback here when a run dies; it deletes the file
// at the start of every run, so its presence means "the last run failed".
function errorLogPath(root: string): string {
  return path.join(root, "out", "error.log");
}

// A notification is one line of reading. A pasted traceback is neither
// actionable nor readable, and it buries the line that identifies the fault.
function shortMsg(e: unknown): string {
  const lines = errMsg(e)
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);
  // usage.py labels its own summary; anything else reaching here is a raw
  // traceback (Python failed before our handler), whose last line is the cause.
  const labelled = lines.find((l) => l.startsWith("reason:"));
  const raw = lines.some((l) => l.startsWith("Traceback (")) ? lines[lines.length - 1] : lines[0];
  const text = (labelled ?? raw ?? "unknown error").replace(/^reason:\s*/, "");
  return text.length > 140 ? text.slice(0, 139) + "\u2026" : text;
}

// Short on screen, complete on disk, and one click from being shareable.
async function reportFailure(root: string | undefined, what: string, e: unknown): Promise<void> {
  const log = root ? errorLogPath(root) : undefined;
  const hasLog = !!log && fs.existsSync(log);
  const actions = hasLog ? ["Show details", "Open report file"] : ["Show details"];
  const pick = await vscode.window.showErrorMessage(
    `Copilot Usage: ${what} \u2014 ${shortMsg(e)}`,
    ...actions
  );
  if (pick === "Open report file" && log) {
    await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(log));
    return;
  }
  if (pick !== "Show details") {
    return;
  }
  const ch = (diagChannel ??= vscode.window.createOutputChannel("Copilot Usage"));
  ch.clear();
  ch.appendLine(`Copilot Usage \u2014 ${what}`);
  ch.appendLine("");
  ch.appendLine(errMsg(e).trim());
  if (hasLog && log) {
    ch.appendLine("");
    ch.appendLine(`--- ${log} ---`);
    try {
      ch.appendLine(fs.readFileSync(log, "utf8"));
    } catch (readErr: unknown) {
      ch.appendLine(`(could not be read: ${errMsg(readErr)})`);
    }
    ch.appendLine("Attach that file to a bug report \u2014 it holds the full traceback.");
  }
  ch.show(true);
}
