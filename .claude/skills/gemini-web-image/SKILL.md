---
name: gemini-web-image
description: >
  Generate an image_prompts.json manifest's ai rows through the Gemini web app,
  driven by the Aside browser (`aside repl`) and the Gemini account it is signed
  in to. Use on a host that has a Gemini subscription but no usable keyless CLI
  image path — no ChatGPT plan for codex, or codex is unavailable. Works on
  macOS, Linux, and Windows x64. Do not use when image_gen.py can run a CLI or
  API backend; those need no browser.
---

# Gemini Web Image

> Fallback image path for the ppt-master manifest contract. Reads
> `images/image_prompts.json`, writes `images/<filename>`, and sets each row's
> `status` — the same contract [`image_gen.py`](../ppt-master/scripts/image_gen.py)
> honors, so Step 6 needs no change.

**Trigger**: a manifest with `Pending` / `Failed` `ai` rows on a host where no
CLI or API backend can run, and the Aside browser is signed in to Gemini.

---

## 1. The one idea this skill rests on

**One batch is one `aside repl` call, and that call owns its tabs from open to
close.** It opens a tab per row with `openTab()` (up to four), submits the rows
one after another, waits, downloads each original as it finishes, and closes
every tab it opened in a `finally` before it returns. Nothing outlives the call,
so nothing from one batch can be mistaken for another's.

**Only one tab is ever in front, and both the send and the download need to
be.** A background Gemini tab does not take typed input, and a background
download can pick up another tab's result. So submission is serial, download is
serial, and each step brings its own tab forward first. Generation is what runs
in parallel — Gemini works on all four while the call handles them one at a
time.

---

## 2. Preconditions

| Requirement | Check |
|---|---|
| Aside CLI installed | `aside --version`. macOS/Linux: `curl -fsSL https://releases.aside.com/install.sh \| bash`. Windows x64 (PowerShell): `irm https://releases.aside.com/install.ps1 \| iex` |
| Aside app running | The CLI drives the Aside browser; with the app closed every call fails |
| Gemini signed in inside Aside | Open `gemini.google.com/images` in the Aside browser; a signed-in page shows the prompt box. Aside has its own profile, so a Chrome sign-in does not carry over |
| Manifest | Valid `image_prompts.json` with at least one `Pending` or `Failed` row |

The browser's UI language does not matter: the prompt box and the download
button are found by page structure, not by their accessible names. This was
verified on a Korean UI; other languages are expected to work and have not been
measured.

Stop and name the failed precondition. Do not fall back to another image path
from inside this skill — that decision belongs to the caller.

---

## 3. Run

```bash
python3 .claude/skills/gemini-web-image/scripts/gemini_web_image.py \
  --manifest projects/<name>/images/image_prompts.json
```

On Windows use `python` and backslashes; nothing else changes.

| Flag | Meaning | Default |
|---|---|---|
| `--manifest` | Path to `image_prompts.json` | — |
| `--output` / `-o` | Output directory | Manifest's folder |
| `--batch` | Rows per `aside repl` call, one tab each | `4` (the maximum) |
| `--deadline` | Wall-clock budget for the whole run; no batch starts with less than 120s left | `420` |

**The Aside window switches tabs while it runs.** Every send and every download
brings its tab to the front. Say this once before starting so the user does not
click into the window mid-run.

**Idempotent**: only `Pending` and `Failed` rows are taken — the same statuses
`image_gen.py` retries — and each saved file is written back to the manifest
immediately, so an interrupted run keeps what it finished. `Needs-Manual` rows
belong to the user and are never submitted. Re-doing a row that already reads
`Generated` means setting its status back to `Failed` first.

**Failures retry once, in the same run.** A row that did not save is marked
`Failed` with `last_error`, and after the first pass every such row is sent
again in fresh batches. A row that fails twice stays `Failed`; rerunning the
same command retries it again. The exit code is `2` while any row is left.

---

## 4. Rules the browser path forces

Each of these is a failure that already happened, not a preference. The
contract tests in `tests/` pin the ones that live in the script.

| Rule | Why |
|---|---|
| Open tabs with `openTab()`, never `aside "<url>"` | A tab opened from the CLI cannot be closed from the REPL: `closeTab()` and `page.close()` both report success and the tab stays. Four such tabs, closed both ways, left eight |
| Close every tab in `finally` | A batch that fails half-way must not leave tabs behind; relying on the session to clean up leaves it unknowable whether a timed-out call did |
| Keep each call inside 105s | `aside repl` has a 120s hard limit, and past it the CLI prints `Aside isn't running on this machine` — which sends the reader to restart an app that is fine. The JS budgets itself, and a download is not started with less than 22s left, because an original takes 11–17s |
| Type the prompt with `keyboard.insertText()` | `fill()` is rejected by Gemini's contenteditable box, and `pressSequentially()` passes 120s at about 700 characters |
| Bring the tab forward for the send **and** the download | Background submissions: 1 of 4 went through. Serial downloads without focus: 4 files with only 2 distinct checksums. Both together: 4 of 4 distinct. CDP focus emulation would avoid moving the window, but Aside's page object has no CDP session |
| Find elements by structure | Accessible names are rendered in the UI language. The prompt box is the editor inside `<rich-textarea>`; the download button is the one in the response whose icon is named `download` |
| A click is not proof of a send | Require the answer to have started (a `model-response` element, or the URL moving to a conversation) before counting a row as submitted; try Enter, then the send button |
| Put the ratio in the prompt's first line — the script does it | The script prepends `Generate a <ar> image (aspect ratio exactly <ar>).` from the row's `aspect_ratio`. **The manifest's `prompt` must not carry that line itself**; it is added only if missing, and a line naming a different ratio is reported |
| Stop on `google.com/sorry/` or a sign-in page | That is Google's unusual-traffic check or a signed-out session. Only a person can clear it in the Aside browser; the run stops and keeps what it finished |
| Vary the gaps between sends | Fixed intervals are a machine signature, and Google's challenge once followed a run whose every step was metronomic |
| Pass the batch as one argument, under 30,000 characters | Windows caps a command line at 32,767 characters. Long prompts are split into smaller batches before they would cross it |

---

## 5. Verify before reporting success

1. Every requested row reads `Generated` and its file exists.
2. Each file's ratio is within 4% of its row's `aspect_ratio`. The script prints
   `** ratio off` otherwise; that row needs a resubmit, not a footnote.
3. No two output files share a checksum. The script already refuses a file
   identical to one saved earlier (the row is marked `Failed`), but check the
   final set anyway:

   ```bash
   shasum -a 256 projects/<name>/images/*.png | awk '{print substr($1,1,12), $2}' | sort
   ```

4. No file is 1024px on its long edge. That is the inline preview, not the
   original, and it passes the ratio and checksum checks. The run prints a `**`
   line naming any such row; an absent line is the pass.
5. No Gemini tab is left open in the Aside browser.

### 5.1 Timing — measured

Measured 2026-09-23 on macOS, Aside CLI 1.26.916.1741, Korean UI.

| Run | Result | Wall clock |
|---|---|---:|
| 1 row | 2752x1536, tabs 0 left | **46s** |
| 5 rows (batch of 4 + batch of 1: 16:9 ×3, 4:3, 1:1) | 5/5, 5 distinct checksums, originals at 2752x1536 / 2400x1792 / 2048x2048, tabs 0 left | **128s** (97s + 31s) |

**Where the time goes.** Two costs are serial because both need the tab in
front: submitting a row (5–6s, 16–17s for the first tab while the page loads)
and downloading its original (11–17s). Generation overlaps them — by the time
the fourth row was sent, the first was already finished. A batch of four is
about 100s of serial work against a 105s budget; that is why a row that misses
its turn is retried in the next batch rather than stretching the call past the
REPL limit.

**Ten rows** run as 4 + 4 + 2 and should take about 3.5–4 minutes; the default
420s deadline covers that plus one retry batch. A larger deck needs a raised
`--deadline`.

---

## 6. Checking the skill after a change

Two layers, both runnable without a browser:

```bash
# the script's contract — tab closing, budget, selectors, manifest write-back
python3 -m unittest discover .claude/skills/gemini-web-image/tests

# the skill's teaching — does a plan written from this file follow §4
python3 .claude/skills/gemini-web-image/evals/score.py <dir-of-plans>
```

[`evals/run-harness.md`](evals/run-harness.md) describes how the plans are
written. When an eval check fails, read the plan before touching the skill —
the check is a pattern match over prose.

---

## 7. When a row does not come back

| `last_error` says | Action |
|---|---|
| `aside repl returned no result (... isn't running ...)` | Either the Aside app is closed or a call ran past 120s. Open the app and rerun; if it recurs with the app open, lower `--batch` |
| `prompt box never appeared at <url>` | Read the URL. `google.com/sorry/...` is Google's challenge and `accounts.google.com` is a sign-in wall — clear it in the Aside browser by hand. A normal Gemini URL means the page changed; re-read it with `aside repl` and `snapshot()` before editing selectors |
| `prompt typed but the answer never started` | The send was dropped. The retry pass resends it; if it fails twice, check the page by hand for a dialog covering the prompt box |
| `no image inside the batch budget; page ends with: ...` | Gemini answered with text — often a refusal of the prompt — or was slow. Read the quoted tail; reword the prompt if it is a refusal |
| `the batch's 105s budget ran out ...` | The row's image was ready but its turn to download did not come. The retry pass takes it; nothing needs changing |
| `image shown but the download failed` | The download button did not produce a file. Rerun; if every row fails this way, the page's download control changed |
| `identical to <file> — tab isolation broke` | Two rows received the same bytes. Resubmit the row; if it recurs, the focus rule in §4 is no longer holding |

Rows this skill cannot finish stay `Failed`. Hand them back to the caller; the
manifest is the record.
