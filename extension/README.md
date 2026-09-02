# GHCP Usage Metrics — VS Code extension

Hosts the local Copilot usage dashboard inside a VS Code webview and lets the
**Refresh data** button re-scan your logs live.

## How it works

The Python extractor (`usage.py`, in the repo root) stays the single source of
truth. The extension:

1. runs `python usage.py` (writes `out/dashboard.html`),
2. loads that self-contained report into a webview,
3. re-runs the extractor when you click **Refresh data** (or run
   *Copilot Usage: Refresh Data*), then reloads the panel with fresh numbers.

Nothing leaves your machine — the extractor only reads your local Copilot logs.

## Requirements

- **Python 3.8+ on your PATH.** No pip packages are needed — the extractor is
  stdlib-only. If your interpreter isn't named `python`, set `ghcpUsage.pythonPath`.
- **Token, AI-credit (AIU) & model figures** come from fields GitHub Copilot Chat
  writes into its own local request logs (`debug-logs` and `chatSessions`). Older
  sessions get trimmed and debug logs rotate, so a machine may show only request
  counts. Run *Copilot Usage: Diagnostics* to see exactly what was found and why.

## Data source and agent debug logs

Open the dashboard, click the **Config** gear, and use **VS Code data source**:

- **Automatic (recommended)** compares agent debug logs and saved chat sessions
  per session, then keeps the fuller copy.
- **Agent debug logs only** gives the richest per-call detail while those logs
  are retained.
- **Saved chat sessions only** works when debug logs are unavailable. It reads
  workspace sessions plus `globalStorage/emptyWindowChatSessions`, with lower
  coverage where VS Code trimmed request bodies.

When the dashboard detects no agent debug-log sessions, click **Enable logging**.
The extension sets
`github.copilot.chat.agentDebugLog.fileLogging.enabled` to `true`. Reload the
VS Code window, start a new chat, and refresh the dashboard. Existing history
cannot be recovered if its logs were never written.

## Develop / run

```pwsh
cd extension
npm install
npm run compile
```

Then press **F5** (Run Extension) and invoke **Copilot Usage: Open Dashboard** from
the Command Palette.

## Settings

| Setting                | Default    | Description                                                        |
| ---------------------- | ---------- | ------------------------------------------------------------------ |
| `ghcpUsage.pythonPath` | `python`   | Interpreter used to run `usage.py`.                                |
| `ghcpUsage.repoPath`   | *(empty)*  | Folder containing `usage.py`. Empty = auto-detect (workspace, then the extension's parent folder). |

## Package a `.vsix`

```pwsh
cd extension
npm run package
```
