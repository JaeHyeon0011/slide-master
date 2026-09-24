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
| **AI image generation** | Your decks need generated cover art or infographics. Photo and icon sourcing works without it. | Codex CLI or an API key — see the [main README](../README.md#설치-10분). For the keyless Gemini route, see [Step 9](#step-9--optional-gemini-web-image-path-aside). | `python .claude\skills\ppt-master\scripts\preflight.py --needs-images` |

---

## Step 9 — Optional: Gemini Web Image Path (Aside)

Skip this unless you want AI-generated images **without** a paid ChatGPT plan or an API key. This route drives the Gemini web app inside the [Aside](https://aside.com) browser, signed in to your own Google account, so it needs a Gemini subscription instead.

**It works on Windows x64.** Aside ships a signed Windows CLI, and [`gemini_web_image.py`](../.claude/skills/gemini-web-image/scripts/gemini_web_image.py) passes each batch to it as a single argument without going through a shell and reads the reply as UTF-8, so Korean prompts are not mangled into `?`. It finds the page's prompt box and download button by page structure rather than by their labels, so the Gemini UI language does not matter.

### 9a — Install Aside

1. Install the Aside app from **[aside.com](https://aside.com)** if you have not already, open it, and leave it running.

2. Install the Aside CLI in PowerShell and confirm it answers:

   ```powershell
   irm https://releases.aside.com/install.ps1 | iex
   aside --version
   ```

   The installer puts `aside.exe` under `%LOCALAPPDATA%\Aside\CLI` and adds it to your user PATH. Open a **new** PowerShell window before `aside --version` so the PATH change is picked up. The image script also checks that folder directly, so it finds the CLI even from a shell opened before the install.

3. In the **Aside browser** (not Chrome or Edge — Aside keeps its own profile), open `https://gemini.google.com/images` and sign in. The page should show a prompt box.

### 9b — Requirements checklist

| Requirement | Why | How to check |
|---|---|---|
| Windows x64 | The Aside CLI installer supports x64 only | `$env:PROCESSOR_ARCHITECTURE` prints `AMD64` |
| Aside CLI on PATH | The image script runs `aside repl` for every batch | `aside --version` |
| Aside app running | The CLI drives the Aside browser; with the app closed every call fails | The Aside window is open |
| Signed in to Gemini **inside Aside**, with an active subscription | The route uses your own session, not an API key | Open `gemini.google.com/images` in Aside and confirm the prompt box renders |

### 9c — Run

The agent invokes this for you during a deck run. To drive it by hand:

```powershell
python .claude\skills\gemini-web-image\scripts\gemini_web_image.py --manifest projects\<name>\images\image_prompts.json
```

Rows go four at a time. While it runs, the Aside window switches between its tabs — every submission and download brings its tab to the front — so leave the window alone until the run prints its summary. Ten images take about four minutes.

> This path was built and measured on macOS. The Windows-specific parts (CLI location, argument passing, UTF-8 output) are covered by the script's tests, but the first real Windows run is yours — if a batch fails, the row's `last_error` in `image_prompts.json` says why.

### 9d — Pin the image path to Gemini web (no paid ChatGPT plan)

The deck workflow's image source defaults to **auto**, which tries the `codex` backend first. On a machine with only a free ChatGPT account that attempt cannot succeed, and its recovery step suggests installing Codex, which is a dead end. Pin the choice for this machine instead: create `CLAUDE.local.md` in the repository root with the content below. Claude Code loads it on every session in this folder, and `.gitignore` keeps it out of the repository.

```markdown
# 이 PC의 고정 설정

- 이 PC에는 ChatGPT 무료 계정만 있어 Codex로 이미지를 만들 수 없다. Gemini는 유료 구독이 있다.
- 덱의 AI 이미지 생성 방식(`image_ai_path`)은 항상 `gemini-web`(Gemini 웹 전용)으로 확정한다. 확인 화면의 추천값과 채팅 확인 모두 이 값으로 내고, `auto`나 `codex`를 추천하지 않는다.
- Codex CLI 설치나 `codex login`을 권하지 않는다.
- Gemini 웹 경로가 실패하면 `.claude/skills/gemini-web-image/SKILL.md` §7에 따라 실패한 행과 `last_error`를 보고하고, 웹 이미지 검색이나 직접 업로드로 넘긴다.
```

The confirmation page still shows the image-source field; with this file in place the recommended value is **Gemini web only**, and choosing it by hand has the same effect.

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

### Gemini image generation reports "Aside CLI not found"

The CLI is not installed or not on PATH. Install it and open a new PowerShell window:

```powershell
irm https://releases.aside.com/install.ps1 | iex
aside --version
```

See [Step 9](#step-9--optional-gemini-web-image-path-aside).

### Rows fail with "aside repl returned no result (Aside isn't running ...)"

Either the Aside app is closed, or one call ran past the CLI's 120-second limit — the CLI prints the same "isn't running" message for both. If the app is open, rerun with smaller batches:

```powershell
python .claude\skills\gemini-web-image\scripts\gemini_web_image.py --manifest projects\<name>\images\image_prompts.json --batch 2
```

### Rows fail with "prompt box never appeared at ..."

Read the URL in the message. `google.com/sorry/...` is Google's unusual-traffic check and `accounts.google.com` means the Aside browser is signed out; clear either by hand in the Aside browser, then rerun. Finished rows are kept.

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
- 🌐 Problems with the Aside browser or CLI → [aside.com](https://aside.com)

When reporting, include your Python version, Windows version, the full error message, and the output of `python .claude\skills\ppt-master\scripts\preflight.py`.
