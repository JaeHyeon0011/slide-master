---
name: gemini-web-image
description: >
  Generate an image_prompts.json manifest's ai rows through the Gemini web app,
  driven by the Aside browser (`aside repl`) and the Gemini account it is signed
  in to. Use on a host that has a Gemini subscription but no usable keyless CLI
  image path — no ChatGPT plan for codex, or codex is unavailable. Built to run
  in the background with the Aside window covered or minimized (measured on
  macOS with Aside hidden; Windows x64 is the design target). Do not use when
  image_gen.py can run a CLI or API backend; those need no browser.
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

**It must run with the Aside window covered or minimized, and nothing in it may
depend on that window being painted.** On Windows, Chromium marks a covered,
minimized, locked-screen, or other-virtual-desktop window as occluded and stops
painting it ([Chromium docs](https://chromium.googlesource.com/chromium/src.git/+/master/docs/windows_native_window_occlusion_tracking.md));
macOS has no such mode ([Edge policy: "macOS: Not supported"](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-browser-policies/windowocclusionenabled)),
which is the likely reason the first Aside version worked on a Mac and stalled
on Windows (inferred from the symptom; not reproduced on Windows). In
an unpainted window the finished image never decodes and Playwright's `click()`
and `waitFor('visible')` wait for frames that never come. So every step here is
paint-free: the prompt box is awaited as attached, text goes in without the tab
in front, a row counts as ready when its download button exists, and every click
is a DOM click.

**Downloads are the one serial step, and the only one that touches focus.**
Aside delivers a download to the active tab of its window, so each download
first activates its own tab — a tab switch inside the Aside window, which leaves
a covered or minimized window where it is — then clicks, reads that download's
own file, and pauses before the next. Generation runs in parallel: Gemini works
on all four while the call submits and collects them one at a time. On macOS
the activation left a hidden Aside hidden; on Windows, Chromium's
activation path may flash the taskbar button or restore the window — unverified,
and the one behaviour to watch on a first Windows run. If a download does not
arrive, the call stops downloading and leaves the rest to the retry pass,
because a late download would otherwise be saved by the next waiting row.

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

**The user can keep working.** The Aside window may be covered by other windows
or minimized for the whole run. The one visible effect, if they look at Aside,
is its tab switching at each download (see §1 for the Windows caveat). The
Aside app must stay open; a locked screen has not been tested.

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
| Never wait on the window being painted | Readiness is the download button's presence, not a decoded image; the box is awaited as `attached`; every click is a DOM click. With Aside hidden, a finished image kept `naturalWidth` 0 and `img.decode()` threw, while the button was already there |
| Type the prompt with `keyboard.insertText()` after a DOM focus, falling back to `execCommand('insertText')` | Both put the full prompt into a background tab with Aside hidden. `fill()` is rejected by the contenteditable box, `pressSequentially()` passes 120s at about 700 characters, and a synthetic paste event is ignored |
| Submit without bringing a tab forward | Aside reports every tab visible and focused, and text lands in background tabs. The earlier "1 of 4 background submissions" came from actionability waits, not from input |
| Activate the tab, then download; one download at a time; read `download.path()`; pause 1.5s after each | Aside hands a download to the window's active tab: clicked in a background tab, the tab's own waiter saw nothing. `download.saveAs()` returned the previous download's file for every second row. Four concurrent downloads all received the first tab's file. With activation, `path()` and the pause: 13 of 13 correct across minimized, hidden and visible runs |
| Reject a download whose file name was already seen in the batch | Gemini names each file after its image (`Gemini_Generated_Image_<id>.png`). A repeated name is another row's download handed over again; the row fails and the retry pass redoes it |
| Treat a wrong aspect ratio as a failed row | Gemini holds the asked ratio to within 0.1%, so a mismatch means another row's image. It is removed and the row is marked `Failed`, never kept with a warning |
| Find elements by structure | Accessible names are rendered in the UI language. The prompt box is the editor inside `<rich-textarea>`; buttons are identified by their icon names (`send`, `download`) |
| A click is not proof of a send | Require the answer to have started (a `model-response` element, or the URL moving to a conversation) before counting a row as submitted; try Enter, then the send button |
| Put the ratio in the prompt's first line — the script does it | The script prepends `Generate a <ar> image (aspect ratio exactly <ar>).` from the row's `aspect_ratio`. **The manifest's `prompt` must not carry that line itself**; it is added only if missing, and a line naming a different ratio is reported |
| Stop on `google.com/sorry/` or a sign-in page | That is Google's unusual-traffic check or a signed-out session. Only a person can clear it in the Aside browser; the run stops and keeps what it finished |
| Vary the gaps between sends | Fixed intervals are a machine signature, and Google's challenge once followed a run whose every step was metronomic |
| Pass the batch as one argument, under 30,000 characters as Windows quotes it | Windows caps a command line at 32,767 characters, and quoting doubles backslashes and escapes quotes. Long prompts are split into smaller batches before they would cross it |

---

## 5. Verify before reporting success

1. Every requested row reads `Generated` and its file exists.
2. Each file's ratio is within 4% of its row's `aspect_ratio`. The script marks
   a mismatched row `Failed` and removes its file.
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

Measured 2026-09-25 on macOS, Aside CLI 1.26.916.1741, Korean UI, with the
background design above. Every row was an original (2752x1536 for 16:9,
2400x1792 for 4:3, 2048x2048 for 1:1), every checksum distinct, and no tab was
left open.

| Aside window during the run | Rows | Result | Wall clock |
|---|---:|---|---:|
| App hidden, browser window confirmed off-screen before, during and after | 10 (4 + 4 + 2) | 10/10 | **200s** (81s + 75s + 44s) |
| App hidden | 5 (4 + 1) | 5/5, app still hidden afterwards | **117s** (86s + 31s) |
| Visible | 4 | 4/4 | **79s** |

For comparison, the retired Kimi WebBridge path took 272s for ten originals
(2026-08-20), so ten images are about 26% faster here — with the window out of
sight instead of in front. (Earlier "minimized" runs are not listed: the
minimize command reached Aside's accessory windows, and the browser window was
later found on screen.)

macOS keeps painting a hidden window at a reduced rate rather than stopping,
so these runs prove the design does not need the window in front, but not that
a Windows occluded window behaves identically. Nothing in the script waits on
painting; the contract tests pin that.

**Where the time goes.** Submitting a row takes about 5s and downloading its
original 11–13s plus a 1.5s pause, both one row at a time. Generation overlaps
them — by the time the fourth row was sent, the first was finished. A batch of
four is about 80s against a 105s budget; a row that misses its turn is retried
in the next batch rather than stretching the call past the REPL limit.

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
| `aside repl returned no result (no output within 150s — the call hung)` | A page step never returned — on Windows, most likely a throttled renderer. Rerun with `--batch 2`; report it if it recurs |
| `aside repl returned no result (... isn't running ...)` | Either the Aside app is closed or a call ran past 120s. Open the app and rerun; if it recurs with the app open, lower `--batch` to 3 or 2. Do not reinstall Aside for this |
| `the page raised an error: ...` | One row's step threw. Read the message; the other rows in the batch were not affected |
| `the prompt box did not take the typed text` | Neither typing method reached the editor. Open Gemini in the Aside browser by hand and check for a dialog over the prompt box |
| `prompt box never appeared at <url>` | Read the URL. `google.com/sorry/...` is Google's challenge and `accounts.google.com` is a sign-in wall — clear it in the Aside browser by hand. A normal Gemini URL means the page changed; re-read it with `aside repl` and `snapshot()` before editing selectors |
| `prompt typed but the answer never started` | The send was dropped. The retry pass resends it; if it fails twice, check the page by hand for a dialog covering the prompt box |
| `no image inside the batch budget; page ends with: ...` | Gemini answered with text — often a refusal of the prompt — or was slow. Read the quoted tail; reword the prompt if it is a refusal |
| `the batch's 105s budget ran out ...` | The row's image was ready but its turn to download did not come. The retry pass takes it; nothing needs changing |
| `not downloaded — an earlier download in the batch went missing ...` | Deliberate: after one lost download the rest of that batch is left to the retry pass. Nothing needs changing unless it recurs every batch |
| `image shown but the download failed (no download arrived ...)` | The click produced no download inside the wait. The retry pass redoes it; if every row fails this way, the page's download control changed |
| `image shown but the download failed (received another row's download ...)` | Aside handed over the previous download again. The retry pass takes it; if every second row fails this way, the 1.5s pause after each download is too short for that machine |
| `image shown but the download failed` (other) | The download button did not produce a file. Rerun; if every row fails this way, the page's download control changed |
| `identical to <file>` or `saved WxH but the row asks for ...` | The row received another row's image; the file was not kept. Resubmit; if it recurs, the download rules in §4 are no longer holding |

Rows this skill cannot finish stay `Failed`. Hand them back to the caller; the
manifest is the record.
