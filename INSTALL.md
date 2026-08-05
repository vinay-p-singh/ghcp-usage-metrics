# Installing

Two ways to use this tool, and they are independent — install either, or both.

| You want                                        | Install         |
| ----------------------------------------------- | --------------- |
| A dashboard inside VS Code with a refresh button | The extension   |
| To ask an AI coding agent about your usage       | The skill       |
| Neither — just the HTML report                   | Nothing; run `python usage.py` |

Everything runs locally. No data leaves your machine, and nothing is uploaded
anywhere.

## Before you start

- **Python 3.8 or newer on your PATH.** Check with `python --version`. No pip
  packages are needed — the extractor uses only the standard library.
- **VS Code**, if you want the extension.

If your interpreter is not called `python` (common on macOS and Linux, where it
is `python3`), that is fine — you set the name once in a setting, covered below.

## Install the extension from a `.vsix`

This extension is not on the Marketplace, so it installs from a `.vsix` file.

### Step 1 — get the `.vsix`

Either someone sent you one, or you build it from a clone:

```pwsh
cd extension
npm install
npm run package
```

That writes `extension/ghcp-usage-metrics-<version>.vsix`.

### Step 2 — install it through the three-dots menu

1. Open VS Code.
2. Open the **Extensions** view — click the squares icon in the Activity Bar, or
   press `Ctrl+Shift+X` (`Cmd+Shift+X` on macOS).
3. Click the **`...`** button at the top-right of the Extensions sidebar, next to
   the *EXTENSIONS* title. It is easy to miss — it sits on the sidebar header,
   not on the editor toolbar.
4. Choose **Install from VSIX…**.
5. Select the `.vsix` file.
6. Reload the window if VS Code asks.

The same thing from a terminal, if you prefer:

```pwsh
code --install-extension path\to\ghcp-usage-metrics-1.2.1.vsix
```

### Step 3 — open the dashboard

Press `Ctrl+Shift+P`, run **GHCP Usage: Open Dashboard**.

The first scan takes a little while — it is reading every Copilot log on the
machine. Later opens paint the previous report instantly and refresh behind it.

### Settings worth knowing

| Setting                  | Default   | When you need it                                                       |
| ------------------------ | --------- | ---------------------------------------------------------------------- |
| `ghcpUsage.pythonPath`   | `python`  | Your interpreter is `python3`, or lives outside PATH. Give the full path. |
| `ghcpUsage.repoPath`     | *(empty)* | You want it to run a specific checkout instead of the bundled copy.    |
| `ghcpUsage.quickScanDays`| `10`      | Only affects the very first paint, never the totals.                   |

### Updating

Installing a newer `.vsix` over an older one leaves the old folder on disk, and
after a downgrade VS Code can load the wrong one. Uninstall first:

```pwsh
code --uninstall-extension local.ghcp-usage-metrics
code --install-extension path\to\ghcp-usage-metrics-<new version>.vsix
```

From the UI: right-click the extension in the Extensions view, choose
**Uninstall**, reload, then install the new `.vsix` the same way as above.

## Set up the skill

The skill lets an AI coding agent answer questions like "which project costs the
most" from your own numbers, instead of reading a 130 KB JSON file into the
conversation.

### Copy the folder

`skills/ghcp-usage-metrics/` is self-contained — it carries the extractor, the
query CLI and the instructions. Copy the whole folder into your agent's skill
directory:

```pwsh
Copy-Item -Recurse skills\ghcp-usage-metrics "$HOME\.copilot\skills\ghcp-usage-metrics"
```

On macOS or Linux:

```bash
cp -r skills/ghcp-usage-metrics ~/.copilot/skills/ghcp-usage-metrics
```

If you have the repo checked out, this does the same thing and keeps the copy in
step with the source afterwards:

```pwsh
python scripts/bundle_skill.py
```

It only writes to `~/.copilot/skills/ghcp-usage-metrics/` when that folder
already exists, so run the copy once yourself first.

### Check it works

From inside the skill folder:

```pwsh
python usage.py
python query.py summary
```

The first command writes `out/projects.json` and `out/dashboard.html` beside the
skill. The second prints your totals. Then ask your agent something like *"how
much Copilot have I used this week"* — it should reach for the skill on its own.

The skill keeps its own `out/` snapshot, separate from any checkout you have, so
the two can report slightly different numbers depending on which was refreshed
last. Re-run `python usage.py` in whichever one you are asking about.

## When something goes wrong

The extension shows one sentence and keeps the detail out of your way. To see
the detail:

- **Show details** on the error notification opens the full record in the output
  panel.
- **Open report file** opens `out/error.log`, which holds the traceback, your
  platform and Python version, and what the scan had already read. A successful
  run deletes that file, so if it exists, the last run failed. Attach it to a bug
  report.
- **GHCP Usage: Diagnostics** from the Command Palette reports what the extractor
  can actually see on this machine.
- The dashboard's **Diagnostics** tab lists every file the scan skipped and why.
  A single unreadable log is skipped rather than failing the whole scan, so this
  is where a partial result explains itself.

Common causes:

| Symptom                                  | Cause                                                                 |
| ---------------------------------------- | --------------------------------------------------------------------- |
| "Python not found"                       | Set `ghcpUsage.pythonPath` to your interpreter.                       |
| "Could not find usage.py"                | Reinstall the `.vsix`, or set `ghcpUsage.repoPath` to a checkout.     |
| Requests but no tokens or credits        | Those logs were trimmed or rotated by Copilot. Not a setting you can change — see the Diagnostics tab. |
| Numbers lower than GitHub's own figure   | Expected. This reads one machine; GitHub bills an account. The Diagnostics tab's reconciliation card explains the gap. |
