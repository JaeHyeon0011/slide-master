# Windows Installation Guide

This guide walks you through installing Slide Master on Windows step by step. Follow along and you'll have a working setup in about 15 minutes.

> **Clone this repository, not upstream.** Slide Master is a Korean-deck customization of [hugohe3/ppt-master](https://github.com/hugohe3/ppt-master) (MIT). It fixes the deck font to Pretendard and adjusts the workflow for Korean output. Cloning the upstream repository instead gives you a build without those changes — use the URL in [Step 3](#step-3--download-the-project).

---

## Step 1 — Install Python (Required)

Python is the only hard requirement.

1. Go to **[python.org/downloads](https://www.python.org/downloads/)** and download the latest **Python 3.10+** installer.

2. **⚠️ CRITICAL: Check "Add python.exe to PATH"** during installation — this is the single most common mistake on Windows. Skipping this will break every step that follows.

3. After installation, open **PowerShell** (search "PowerShell" in Start menu) and verify:

   ```powershell
   python --version
   ```

   You should see `Python 3.12.x` or similar. If you see "Python was not found" or it opens the Microsoft Store, see [Troubleshooting](#python-was-not-found-or-opens-microsoft-store) below.

> **💡 Tip**: Python installed via Anaconda or Miniconda works too — just make sure `python --version` shows 3.10+.

### Step 1b — Make `python3` resolve (strongly recommended)

The skill documentation spells commands as `python3 ...` in roughly 400 places. The python.org installer ships `python.exe` but **no `python3.exe`**, so every one of those commands opens the Microsoft Store instead of running. Creating one copy makes them all work unchanged:

```powershell
$py = (Get-Command python).Source; if ($py -like "*WindowsApps*") { Write-Host "Store alias is shadowing Python - see Troubleshooting first." } else { Copy-Item $py (Join-Path (Split-Path $py) "python3.exe"); python3 --version }
```

✅ Output ends with a version number → done. Every `python3` command in the docs now works.

❌ Output says the Store alias is shadowing Python → follow [Troubleshooting](#python-was-not-found-or-opens-microsoft-store), then run the line again.

> Skipping this step is survivable — the AI agent usually notices the failure and retries with `python`. But it costs a wasted attempt on nearly every command, so it is worth the ten seconds.

---

## Step 2 — Install Git for Windows (Required)

Git is needed to download the project, and Claude Code's shell tooling on Windows relies on the Bash that ships with it.

1. Download from **[git-scm.com/downloads](https://git-scm.com/downloads)** and install with the default options.

2. Verify in a **new** PowerShell window:

   ```powershell
   git --version
   ```

---

## Step 3 — Download the Project

**Option A — Git Clone** (recommended — lets you update later with a single `git pull`):

```powershell
cd $HOME
git clone https://github.com/JaeHyeon0011/slide-master.git
cd slide-master
```

**Option B — Download ZIP**:

1. Go to [github.com/JaeHyeon0011/slide-master](https://github.com/JaeHyeon0011/slide-master)
2. Click the green **Code** button → **Download ZIP**
3. Unzip to `C:\Users\YourName\slide-master`

---

## Step 4 — Install Dependencies

```powershell
cd $HOME\slide-master   # ← adjust to your actual path
pip install -r requirements.txt
```

> If `pip` is not recognized, try `python -m pip install -r requirements.txt`.

Wait for it to finish. You should see `Successfully installed ...` at the end.

---

## Step 5 — Install the Pretendard Font (Required for correct output)

Every deck this project generates is typeset in **Pretendard**. Without it installed, previews and exported `.pptx` files silently fall back to a substitute font and the layout no longer matches what the pipeline designed. The font files ship inside the repository, so there is nothing to download.

1. Open the bundled font folder in Explorer:

   ```powershell
   explorer .claude\skills\ppt-master\assets\fonts\Pretendard
   ```

2. Select all **six `.otf` files** (`Ctrl+A`, then deselect `LICENSE.txt` if it gets included).

3. Right-click the selection → **Install**.
   On Windows 11 you may need **Show more options** first to reveal the Install entry.

> **Install for all users?** Either choice works. "Install" (current user only) is enough and does not need administrator rights.

> **📌 Note for sharing decks**: PPTX files do not embed fonts. Anyone who opens your generated deck on another computer needs Pretendard installed there too, or they will see the same substitution.

---

## Step 6 — Verify Your Setup

The project ships an environment gate that checks dependencies, fonts, and tooling in one pass:

```powershell
python .claude\skills\ppt-master\scripts\preflight.py
```

✅ `[preflight] PASS — environment ready` → you're good.

⚠️ `PASS` with warnings → the core pipeline works; each warning names the optional piece that is missing and how to install it.

❌ `[preflight] FAIL` → each line names the missing dependency and its `pip install` command. See [Troubleshooting](#troubleshooting) below.

---

## Step 7 — Install Claude Code and Run

Claude Code is the most heavily validated environment for this project.

1. Install it by following **[the official Claude Code setup guide](https://docs.claude.com/en/docs/claude-code/setup)**.

2. Open the project folder and start Claude Code:

   ```powershell
   cd $HOME\slide-master
   claude
   ```

   If you prefer an IDE, open the `slide-master` folder in VS Code or a JetBrains IDE with the Claude Code extension installed. Either way, **the folder you open must be the repository root** — that is how the skills and `CLAUDE.md` get discovered.

3. Type a request in the chat, in plain language:

   ```
   3페이지짜리 테스트 PPT를 만들어줘. 표지, 본문 한 장, 마무리 한 장. 주제는 "Hello World".
   ```

4. The agent opens a confirmation page in your browser to settle direction and design, then generates the deck.

If a `.pptx` appears under `projects\<project-name>\exports\` and opens in PowerPoint — **you're done.**

> **Other agents work too.** Codex (CLI or the ChatGPT desktop app), Cursor, and VS Code Copilot can all drive this repository; the Codex execution rules live in [`AGENTS.md`](../AGENTS.md) and its discovery stubs in `.codex/skills/`.

---

## Step 8 — Optional Enhancements (most users can skip this)

With Python, the dependencies, and the font installed, you already have everything needed to generate presentations. PPTX export writes native DrawingML shapes, so it does not require CairoSVG, GTK, or a separate SVG rasterization stack. Everything below is optional.

| Enhancement | Install only if… | How to install | Verify |
|-------------|-----------------|----------------|--------|
| **Pandoc** — legacy document formats | You need to convert `.doc`, `.odt`, `.rtf`, `.tex`, `.rst`, `.org`, or `.typ`. `.docx`/`.html`/`.epub`/`.ipynb` work natively in Python. | Download `.msi` from [pandoc.org](https://pandoc.org/installing.html) | `pandoc --version` |
| **OfficeCLI** — export verification | You want automated overflow and render checks on the exported deck. With PowerPoint installed, verification screenshots come from the real PowerPoint renderer, which is the most accurate option. | `npm install -g @officecli/officecli@1.0.135` (needs [Node.js](https://nodejs.org/)) | `officecli --version` |
| **AI image generation** | Your decks need generated cover art or infographics. Photo and icon sourcing works without it. | Codex CLI or an API key — see the [main README](../README.md#설치-10분). For the keyless Gemini route, see [Step 9](#step-9--optional-gemini-web-image-path-kimi-webbridge). | `python .claude\skills\ppt-master\scripts\preflight.py --needs-images` |

---

## Step 9 — Optional: Gemini Web Image Path (Kimi WebBridge)

Skip this unless you want AI-generated images **without** a paid ChatGPT plan or an API key. This route drives the Gemini web app inside your own signed-in browser, so it needs a Gemini subscription instead.

**It works on Windows.** The daemon ships a native Windows binary, it attaches to Chrome or Edge through a browser extension, and the Korean prompts this project sends survive the trip — [`gemini_web_image.py`](../.claude/skills/gemini-web-image/scripts/gemini_web_image.py) posts every request as a UTF-8 file body rather than inline, which is exactly what avoids the Windows shell mangling non-ASCII text into `?`.

### 9a — Install the daemon

1. Install Kimi WebBridge from **[kimi.com/features/webbridge](https://www.kimi.com/features/webbridge)** and connect the browser extension to Chrome or Edge when prompted.

2. Start the daemon and confirm it is up:

   ```powershell
   & "$env:USERPROFILE\.kimi-webbridge\bin\kimi-webbridge.exe" start
   & "$env:USERPROFILE\.kimi-webbridge\bin\kimi-webbridge.exe" status
   ```

   The status output should report the daemon running on `127.0.0.1:10086` with the extension connected. If `extension_connected` is false, open the extension in the browser and let it attach.

3. Let the daemon install its own agent skill so Claude Code can start and recover it on its own:

   ```powershell
   & "$env:USERPROFILE\.kimi-webbridge\bin\kimi-webbridge.exe" install-skill
   ```

   > This skill lives outside the repository, so cloning Slide Master does not bring it along. The image path still runs without it — [`gemini_web_image.py`](../.claude/skills/gemini-web-image/scripts/gemini_web_image.py) talks to the daemon over plain HTTP — but installing it lets the agent restart a stopped daemon instead of stalling.

### 9b — Requirements checklist

| Requirement | Why | How to check |
|---|---|---|
| `curl.exe` on PATH | The image script shells out to `curl` for every daemon call | `curl.exe --version` — bundled with Windows 10 1803+ and with Git for Windows |
| Daemon running, extension attached | Nothing reaches the browser otherwise | `kimi-webbridge.exe status` |
| Signed in to Gemini with an active subscription | The route uses your own session, not an API key | Open `gemini.google.com` and confirm the prompt box renders |
| **Browser UI language set to Korean** | The skill locates page elements by their Korean accessible names (`Gemini 프롬프트 입력`, `메시지 보내기`, and three others). An English UI finds none of them | Check that the Gemini page chrome is in Korean |
| Automatic downloads allowed for `gemini.google.com` (optional) | Images then arrive at original size; without it a canvas fallback finishes the run at displayed size | Browser site settings → Automatic downloads |

### 9c — Run

The agent invokes this for you during a deck run. To drive it by hand:

```powershell
python .claude\skills\gemini-web-image\scripts\gemini_web_image.py --manifest projects\<name>\images\image_prompts.json
```

> **Do not run `stop`, `restart`, or `uninstall` on the daemon while a deck run is in progress** — it kills the browser session mid-generation. `start` is safe to repeat; it no-ops when the daemon is already up.

---

## Troubleshooting

### `python` was not found or opens Microsoft Store

**Cause**: Python isn't in your PATH, or Windows' built-in Store alias is shadowing it.

**Fix 1 — turn off the Store alias**: Search "Manage app execution aliases" in the Start menu, then switch **off** the entries named `python.exe` and `python3.exe` (labeled "App Installer").

**Fix 2** — Re-run the Python installer → **Modify** → check **"Add Python to environment variables"**.

**Fix 3** — Manually add to PATH:
1. Run `where.exe python` in PowerShell first to find the actual path (e.g. `C:\Users\YourName\AppData\Local\Programs\Python\Python312\python.exe`)
2. Search "Environment Variables" in Start menu
3. Find `Path` → **Edit** → add the **directory** from step 1 and its `Scripts` subfolder:
   ```
   C:\Users\YourName\AppData\Local\Programs\Python\Python312
   C:\Users\YourName\AppData\Local\Programs\Python\Python312\Scripts
   ```
4. Click OK, then **restart PowerShell**

### A `python3` command fails (exit 49 / opens Microsoft Store)

You skipped [Step 1b](#step-1b--make-python3-resolve-strongly-recommended). Either run it now, or **just replace `python3` with `python` in the command** — the AI agent usually switches to `python` and continues on its own too.

### The deck renders in the wrong font

Pretendard is not installed, or it was installed after the current session started. Re-run [Step 5](#step-5--install-the-pretendard-font-required-for-correct-output), then confirm with:

```powershell
python .claude\skills\ppt-master\scripts\preflight.py
```

A `'Pretendard' font not found` warning means the installation did not take. Reinstalling for all users (right-click → **Install for all users**, requires administrator rights) resolves the common case.

### `pip install` fails with permission errors

```powershell
pip install --user -r requirements.txt
```

Or run PowerShell as Administrator.

### `pip install` fails due to network issues

```powershell
pip install -r requirements.txt --proxy http://your-proxy:port
```

### `ModuleNotFoundError`

`pip` installed to a different Python. Use `python -m pip install -r requirements.txt` to match.

### `import fitz` fails

1. Upgrade pip: `python -m pip install --upgrade pip`
2. Pre-built wheel: `pip install PyMuPDF --only-binary :all:`
3. Still failing → install [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)

### Step 1b fails with an access-denied error

Python was installed for all users under `C:\Program Files`, so writing `python3.exe` next to it needs elevation. Right-click PowerShell → **Run as administrator**, then run the Step 1b line again.

### PowerShell says "running scripts is disabled"

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Gemini image generation reports "WebBridge is not answering"

The daemon is not running or the extension detached. Start it and check status:

```powershell
& "$env:USERPROFILE\.kimi-webbridge\bin\kimi-webbridge.exe" start
& "$env:USERPROFILE\.kimi-webbridge\bin\kimi-webbridge.exe" status
```

If status reports `extension_connected: false`, open the browser and let the Kimi extension attach. If the binary itself is missing, WebBridge was never installed — see [Step 9](#step-9--optional-gemini-web-image-path-kimi-webbridge). For anything still broken after a `start` and a retry, use the vendor help page at [kimi.com/features/webbridge](https://www.kimi.com/features/webbridge) rather than deep-troubleshooting the daemon.

### Gemini image generation stalls without an error

The most common cause is a **non-Korean browser UI**. The skill finds the prompt box and send button by their Korean accessible names, so an English or Chinese Gemini interface matches nothing and the run waits forever. Switch the browser's Gemini UI to Korean and rerun.

### preflight reports stale Codex stubs

Regenerate them and re-run the gate:

```powershell
python .claude\skills\ppt-master\scripts\sync_codex_stubs.py
```

---

## Still stuck?

- 📖 [FAQ](./faq.md) and [Getting Started](./getting-started.md)
- 🐛 Problems specific to this Korean workspace → ask whoever shared the repository with you (issue tracking is not enabled on this fork)
- 🐛 Problems with the underlying pipeline → [upstream ppt-master issues](https://github.com/hugohe3/ppt-master/issues)
- 🌐 Problems with the browser bridge → [kimi.com/features/webbridge](https://www.kimi.com/features/webbridge)

When reporting, include your Python version, Windows version, the full error message, and the output of `python .claude\skills\ppt-master\scripts\preflight.py`.
