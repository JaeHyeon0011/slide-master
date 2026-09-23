#!/usr/bin/env python3
"""
PPT Master - Gemini Web Image Generator (Aside)

Generate an `image_prompts.json` manifest's Pending and Failed rows through the
Gemini web app, driven by the Aside browser (`aside repl`) and the account it is
already signed in to. For hosts with a Gemini subscription but no keyless CLI
image path.

One batch is one `aside repl` call: it opens one tab per row (up to four),
submits them one after another, downloads each original as it finishes, and
closes every tab it opened before it returns.

Usage:
    python3 scripts/gemini_web_image.py --manifest <image_prompts.json> [options]

Options:
    --manifest PATH     image_prompts.json to read and write back (required)
    --output, -o DIR    where images land (default: the manifest's folder)
    --batch N           rows per `aside repl` call, one tab each (default 4,
                        max 4). A batch of four measured 97s against the JS
                        budget of 105s, under the REPL's 120s limit. A row that
                        misses its turn is retried once in the same run.
    --deadline S        hard wall-clock budget for the whole run (default 420).
                        No new batch starts once less than one REPL limit is
                        left; unfinished rows stay Failed and retryable.

Examples:
    python3 .claude/skills/gemini-web-image/scripts/gemini_web_image.py \
        --manifest projects/demo/images/image_prompts.json

Dependencies:
    Aside CLI (`aside`) and the Aside browser signed in to Gemini. macOS, Linux,
    and Windows x64. Standard library only.
"""

import sys
from pathlib import Path

if __name__ == "__main__" and any(a in {"-h", "--help", "help"} for a in sys.argv[1:]):
    print(__doc__)
    raise SystemExit(0)

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time

IMAGES_URL = "https://gemini.google.com/images"

# Rows this path may take — the same statuses image_gen.py retries. Generated is
# done; Needs-Manual belongs to the user and is never sent as a prompt.
RETRYABLE = {"Pending", "Failed"}

# The page's own aspect-ratio control is not reliable to drive, but the model
# honors a ratio asked for in the opening line: 16:9 came back 2752x1536, 4:3
# came back 2400x1792, and 1:1 came back 2048x2048.
RATIO_PREFIX = "Generate a {ar} image (aspect ratio exactly {ar}).\n\n"
RATIO_LINE_RE = re.compile(
    r"Generate a (\d+:\d+) image \(aspect ratio exactly \d+:\d+\)\.")
RATIO_TOLERANCE = 0.04

# One `aside repl` call has a 120s hard limit. Past it the connection drops and
# the CLI prints "Aside isn't running on this machine", which sends the reader
# looking for the wrong problem. The JS budgets itself below that and returns.
REPL_LIMIT = 120
BUDGET = 105
MAX_BATCH = 4

# Windows caps a command line at 32,767 characters and the batch travels as one
# argument. Batches are cut short of the cap instead of failing to start.
ARG_LIMIT = 30_000

# The long edge Gemini renders inline. A saved file this small is the preview,
# not the original, and would pass the ratio and checksum checks regardless.
PREVIEW_EDGE = 1024

# Google's unusual-traffic interstitial and a signed-out page both leave no
# prompt box. Only a person can clear either, so the run stops on them.
CHALLENGE_RE = re.compile(r"google\.com/sorry/|accounts\.google\.com", re.I)


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def find_aside() -> str:
    """Locate the Aside CLI on macOS, Linux, or Windows.

    The installers put it on PATH, but a shell opened before the install (or an
    agent's non-login shell) may not see that yet, so the default install
    locations are checked too."""
    found = shutil.which("aside")
    if found:
        return found
    candidates = [Path("~/.local/bin/aside").expanduser()]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data) / "Aside" / "CLI"
        candidates += [base / "aside.exe", base / "bin" / "aside.exe"]
    for path in candidates:
        if path.exists():
            return str(path)
    return ""


def with_ratio(prompt: str, ratio: str) -> str:
    """Put the ratio line in front of the prompt, once.

    Manifests have turned up with the line already there, and prepending it
    blindly sent the same sentence to the page twice. The line belongs to this
    path alone — image_gen.py passes aspect_ratio to its backend as a parameter
    — so it is added here, and only if it is missing."""
    lead = RATIO_PREFIX.format(ar=ratio)
    if prompt.lstrip().startswith(lead.strip()):
        return prompt
    # A prompt carrying a *different* ratio is a manifest error, not something
    # to paper over: the two sentences would contradict each other on the page.
    stale = RATIO_LINE_RE.match(prompt.lstrip())
    if stale and stale.group(1) != ratio:
        log(f"  ** prompt opens with a {stale.group(1)} ratio line but the row "
            f"asks for {ratio}; sending the row's ratio in front of it")
    return lead + prompt


def aspect_ratio_value(text: str) -> float:
    try:
        width, height = text.split(":")
        return float(width) / float(height)
    except (ValueError, ZeroDivisionError):
        return 0.0


def image_size(raw: bytes) -> tuple:
    """(width, height) of a PNG or JPEG, or (0, 0)."""
    if raw[:8] == b"\x89PNG\r\n\x1a\n" and len(raw) >= 24:
        return (int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big"))
    if raw[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(raw):
            if raw[i] != 0xFF:
                i += 1
                continue
            marker = raw[i + 1]
            length = int.from_bytes(raw[i + 2:i + 4], "big")
            if marker in (0xC0, 0xC1, 0xC2):
                return (int.from_bytes(raw[i + 7:i + 9], "big"),
                        int.from_bytes(raw[i + 5:i + 7], "big"))
            i += 2 + length
    return (0, 0)


# ══════════════════════════════════════════════════════════════════════
# The batch — open, submit, wait, download, close, all inside one call
# ══════════════════════════════════════════════════════════════════════

# Every rule in here is a failure that already happened (see SKILL.md §4):
# - Tabs come from openTab(). A tab opened with `aside "<url>"` cannot be closed
#   from the REPL — closeTab() reports success and the tab stays.
# - The prompt goes in with keyboard.insertText(). fill() is rejected by the
#   contenteditable box, and pressSequentially() runs past 120s at 700 chars.
# - A tab must be in front to take input and to download its own result. With
#   submissions in the background only 1 of 4 went through; with downloads in
#   the background two tabs saved the same file. So both steps are serial and
#   each brings its tab to the front first.
# - Elements are found by structure, not by accessible name, so the page's UI
#   language does not matter: the prompt box is the editor inside
#   <rich-textarea>, and the download button is the one whose icon is named
#   "download".
_BATCH_JS = r"""
const JOBS = __JOBS__;
const BUDGET_MS = __BUDGET__ * 1000;
const URL0 = __URL__;
const BOX = 'rich-textarea .ql-editor, rich-textarea [contenteditable="true"]';
const t0 = Date.now();
const left = function(){ return BUDGET_MS - (Date.now() - t0); };
const rows = {};
const open = [];

const front = async function(p){ try { await p.bringToFront(); } catch (e) {} };
const probe = function(p){
  return p.evaluate(function(){
    return { url: location.href,
             text: (document.body ? document.body.innerText : '').slice(0, 600) };
  }).catch(function(){ return { url: '', text: '' }; });
};
// The answer has started once a response element exists or the URL has moved to
// a conversation. A click that "worked" with neither is a dropped send.
const started = function(p){
  return p.evaluate(function(){
    return !!document.querySelector('model-response') || /\/app\/[0-9a-f]+/.test(location.href);
  }).catch(function(){ return false; });
};
const ready = function(p){
  return p.evaluate(function(){
    const rs = document.querySelectorAll('model-response');
    const r = rs[rs.length - 1];
    if (!r) return null;
    const im = Array.from(r.querySelectorAll('img')).find(function(x){
      return x.naturalWidth > 400 && x.naturalHeight > 200; });
    if (!im) return null;
    const m = location.href.match(/\/app\/([0-9a-f]+)/);
    return { w: im.naturalWidth, h: im.naturalHeight, convo: m ? m[1] : null };
  }).catch(function(){ return null; });
};
const markButton = function(p, icon){
  return p.evaluate(function(name){
    const rs = document.querySelectorAll(name === 'send' ? 'body' : 'model-response');
    const scope = rs[rs.length - 1];
    if (!scope) return false;
    const b = Array.from(scope.querySelectorAll('button')).find(function(btn){
      const ic = btn.querySelector('mat-icon');
      if (!ic) return false;
      const n = (ic.getAttribute('fonticon') || ic.getAttribute('data-mat-icon-name') ||
                 ic.textContent || '').trim();
      return n === name || (name === 'send' && n === 'arrow_upward');
    });
    if (!b) return false;
    document.querySelectorAll('[data-ppt-mark]').forEach(function(x){
      x.removeAttribute('data-ppt-mark'); });
    b.setAttribute('data-ppt-mark', name);
    return true;
  }, icon).catch(function(){ return false; });
};

try {
  // ── submit, one tab at a time ────────────────────────────────────
  for (const job of JOBS) {
    const r = { T: {} };
    rows[job.out] = r;
    if (left() < 60000) { r.kind = 'no_time'; continue; }
    const ts = Date.now();
    let p = null;
    try { p = await openTab(URL0); }
    catch (e) { r.kind = 'open'; r.error = String(e && e.message || e); continue; }
    open.push({ job: job, p: p, r: r });
    await front(p);
    const box = p.locator(BOX).first();
    try { await box.waitFor({ state: 'visible', timeout: 25000 }); }
    catch (e) { r.kind = 'no_box'; r.probe = await probe(p); continue; }
    await box.click();
    await p.keyboard.insertText(job.prompt);

    let ok = false;
    for (const way of ['enter', 'button']) {
      if (ok || left() < 45000) break;
      try {
        if (way === 'enter') {
          await p.keyboard.press('Enter');
        } else {
          await front(p);
          if (!(await markButton(p, 'send'))) continue;
          await p.locator('[data-ppt-mark="send"]').first().click();
        }
      } catch (e) { continue; }
      for (let k = 0; k < 20 && !ok; k++) { await sleep(500); ok = await started(p); }
    }
    if (!ok) { r.kind = 'not_sent'; r.probe = await probe(p); continue; }
    r.sent = true;
    r.T.submit_ms = Date.now() - ts;
    // A human does not send four prompts on a metronome.
    await sleep(700 + Math.floor(Math.random() * 1300));
  }

  // ── wait, and download each one as it finishes ───────────────────
  const tw = Date.now();
  let waiting = open.filter(function(o){ return o.r.sent; });
  await fs.mkdir('./artifacts', { recursive: true });
  // An original takes 11-17s from click to file. A download started with less
  // than DL_MIN left would carry the call past the REPL's 120s limit, so the
  // row is handed back for a retry instead.
  const DL_MIN = 22000;
  while (waiting.length && left() > DL_MIN) {
    const still = [];
    for (const o of waiting) {
      if (left() < DL_MIN) { still.push(o); continue; }
      const hit = await ready(o.p);
      if (!hit) { still.push(o); continue; }
      o.r.T.wait_ms = Date.now() - tw;
      o.r.convo = hit.convo;
      o.r.shown = [hit.w, hit.h];
      const td = Date.now();
      try {
        await front(o.p);
        await sleep(600);
        try { await o.p.locator('model-response img').last().hover(); } catch (e) {}
        if (!(await markButton(o.p, 'download'))) throw new Error('download button not found');
        const dlP = o.p.waitForEvent('download',
          { timeout: Math.max(5000, Math.min(30000, left() - 4000)) });
        await o.p.locator('[data-ppt-mark="download"]').first().click();
        const dl = await dlP;
        await dl.saveAs(o.job.out);                 // lands in ./artifacts/
        const st = await fs.stat('artifacts/' + o.job.out);
        o.r.ok = true;
        o.r.bytes = st.size;
        o.r.T.download_ms = Date.now() - td;
      } catch (e) {
        o.r.kind = 'download';
        o.r.error = String(e && e.message || e).slice(0, 200);
      }
    }
    waiting = still;
    if (waiting.length) await sleep(1000);
  }
  for (const o of waiting) {
    o.r.kind = (await ready(o.p)) ? 'no_time' : 'no_image';
    o.r.probe = await probe(o.p);
  }
} catch (e) {
  rows.__batch__ = { kind: 'exception', error: String(e && e.message || e) };
} finally {
  // Every tab this call opened is closed here, including on failure.
  for (const o of open) { try { await closeTab(o.p); } catch (e) {} }
}
console.log('ASIDE_RESULT ' + JSON.stringify({ dir: pwd, rows: rows, ms: Date.now() - t0 }));
"""


def build_batch_js(jobs: list, budget: int = BUDGET) -> str:
    """jobs: [{"out": <file name in the session's artifacts/>, "prompt": ...}]"""
    return (_BATCH_JS
            .replace("__JOBS__", json.dumps(jobs, ensure_ascii=False))
            .replace("__BUDGET__", str(int(budget)))
            .replace("__URL__", json.dumps(IMAGES_URL)))


def run_js(aside: str, js: str) -> str:
    """Run one `aside repl` call and return its combined output.

    No shell in between, so no quoting rules apply to the prompt text. The
    output is decoded as UTF-8 explicitly: on Windows the default is the ANSI
    code page, which turns Korean page text into mojibake."""
    try:
        proc = subprocess.run([aside, "repl", js], capture_output=True,
                              encoding="utf-8", errors="replace",
                              timeout=REPL_LIMIT + 30)
    except subprocess.TimeoutExpired:
        return ""
    return (proc.stdout or "") + (proc.stderr or "")


_RESULT_RE = re.compile(r"^ASIDE_RESULT (\{.*\})\s*$", re.M)


def parse_result(out: str):
    match = _RESULT_RE.search(out or "")
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except ValueError:
        return None


def first_error(out: str) -> str:
    """The REPL's first error line, without ANSI colors or the stack."""
    for line in (out or "").splitlines():
        text = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
        if text.startswith(("Error:", "TypeError:", "SyntaxError:")) or "isn't running" in text:
            return text[:300]
    return ""


def plan_batches(items: list, size: int) -> list:
    """Split rows into batches of at most `size`, each short enough to pass as
    one command-line argument on Windows."""
    batches, current = [], []
    for item in items:
        trial = current + [item]
        js = build_batch_js([{"out": f"row{i}.png", "prompt": with_ratio(it["prompt"], it["aspect_ratio"])}
                             for i, it in enumerate(trial)])
        if current and (len(trial) > size or len(js) > ARG_LIMIT):
            batches.append(current)
            current = [item]
        else:
            current = trial
    if current:
        batches.append(current)
    return batches


def describe_failure(row: dict) -> str:
    kind = row.get("kind") or "unknown"
    url = (row.get("probe") or {}).get("url", "")
    if kind == "no_box":
        return f"gemini-web: prompt box never appeared at {url or 'the page'}"
    if kind == "not_sent":
        return "gemini-web: prompt typed but the answer never started"
    if kind == "no_image":
        text = " ".join(((row.get("probe") or {}).get("text") or "").split())[-160:]
        return f"gemini-web: no image inside the batch budget; page ends with: {text}"
    if kind == "download":
        return f"gemini-web: image shown but the download failed ({row.get('error')})"
    if kind == "no_time":
        return ("gemini-web: the batch's 105s budget ran out before this row's "
                "turn to send or download")
    return f"gemini-web: {kind} {row.get('error') or ''}".strip()


def save_manifest(manifest: dict, path: Path) -> None:
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def run_batch(aside: str, batch: list, manifest: dict, manifest_path: Path,
              out_dir: Path, seen: dict, previews: list) -> tuple:
    """Run one batch and write each row's outcome back at once.

    Returns (saved, blocked_url, failed). blocked_url is set when the page was
    Google's challenge or a sign-in wall, which stops the run; failed lists the
    rows that did not save."""
    jobs = [{"out": f"row{i}.png", "prompt": with_ratio(it["prompt"], it["aspect_ratio"])}
            for i, it in enumerate(batch)]
    started = time.time()
    out = run_js(aside, build_batch_js(jobs))
    result = parse_result(out)
    if not result:
        why = first_error(out) or out.strip()[:200] or "no output"
        if "isn't running" in why:
            why += (" — either the Aside app is closed, or the call ran past the "
                    "REPL's 120s limit")
        for item in batch:
            item["status"] = "Failed"
            item["last_error"] = f"gemini-web: aside repl returned no result ({why})"
        save_manifest(manifest, manifest_path)
        log(f"  batch returned no result: {why}")
        return 0, "", list(batch)

    rows = result.get("rows") or {}
    if "__batch__" in rows:
        log(f"  batch raised: {rows['__batch__'].get('error')}")
    session_dir = Path(result.get("dir") or "")
    saved, blocked, failed = 0, "", []
    for job, item in zip(jobs, batch):
        row = rows.get(job["out"]) or {"kind": "missing"}
        url = (row.get("probe") or {}).get("url", "")
        if CHALLENGE_RE.search(url):
            blocked = url
        if not row.get("ok"):
            item["status"] = "Failed"
            item["last_error"] = describe_failure(row)
            failed.append(item)
            log(f"  {item['filename']}: {item['last_error']}")
            continue

        src = session_dir / "artifacts" / job["out"]
        if not src.exists():
            src = session_dir / job["out"]
        if not src.exists():
            item["status"] = "Failed"
            item["last_error"] = f"gemini-web: downloaded file missing at {src}"
            failed.append(item)
            log(f"  {item['filename']}: {item['last_error']}")
            continue

        raw = src.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest in seen:
            # Two rows holding the same bytes means one tab saved another's
            # result. Neither copy can be trusted to belong to its row.
            item["status"] = "Failed"
            item["last_error"] = (f"gemini-web: identical to {seen[digest]} — tab "
                                  "isolation broke; resubmit")
            failed.append(item)
            log(f"  ** {item['filename']}: {item['last_error']}")
            continue
        seen[digest] = item["filename"]

        dest = out_dir / item["filename"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        width, height = image_size(raw)
        actual = width / height if height else 0
        target = aspect_ratio_value(item["aspect_ratio"])
        if not target:
            note = f"  ** aspect_ratio {item['aspect_ratio']!r} is not W:H — ratio unchecked"
        elif abs(actual - target) / target > RATIO_TOLERANCE:
            note = "  ** ratio off, review this row"
        else:
            note = ""
        if max(width, height) <= PREVIEW_EDGE:
            previews.append(item["filename"])
        timing = row.get("T") or {}
        log(f"  saved {item['filename']} {width}x{height} ratio {actual:.3f} vs "
            f"{item['aspect_ratio']} ({len(raw):,} bytes) "
            f"[submit {timing.get('submit_ms', 0) / 1000:.0f}s, "
            f"ready at {timing.get('wait_ms', 0) / 1000:.0f}s, "
            f"download {timing.get('download_ms', 0) / 1000:.1f}s]{note}")
        item["status"] = "Generated"
        item.pop("last_error", None)
        saved += 1
        save_manifest(manifest, manifest_path)

    save_manifest(manifest, manifest_path)
    log(f"  batch of {len(batch)}: {saved} saved in {time.time() - started:.0f}s, "
        "all tabs closed")
    return saved, blocked, failed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an image manifest through the Gemini web app in Aside."
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", "-o", default=None,
                        help="Output directory (default: the manifest's folder)")
    parser.add_argument("--batch", type=int, default=MAX_BATCH,
                        help=f"Rows per aside repl call, one tab each (default and "
                             f"max {MAX_BATCH}). Four fits the REPL's 120s limit "
                             "with margin")
    parser.add_argument("--deadline", type=int, default=420,
                        help="Hard wall-clock budget for the whole run in seconds "
                             "(default 420). No batch starts once less than one "
                             "batch budget is left")
    args = parser.parse_args()
    size = max(1, min(args.batch, MAX_BATCH))

    run_started = time.time()
    aside = find_aside()
    if not aside:
        log("Aside CLI not found. Install it (macOS/Linux: `curl -fsSL "
            "https://releases.aside.com/install.sh | bash`; Windows: `irm "
            "https://releases.aside.com/install.ps1 | iex`), open the Aside app, "
            "sign in to Gemini there, then rerun. The manifest is untouched.")
        sys.exit(1)

    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    out_dir = Path(args.output).resolve() if args.output else manifest_path.parent

    pending = [it for it in manifest["items"] if it["status"] in RETRYABLE]
    if not pending:
        manual = sum(1 for it in manifest["items"] if it["status"] == "Needs-Manual")
        tail = (f"; {manual} row(s) are Needs-Manual and wait for the user's own "
                "files" if manual else "")
        log(f"nothing to do — no Pending or Failed rows{tail}")
        return

    batches = plan_batches(pending, size)
    log(f"{len(pending)} row(s) in {len(batches)} batch(es) of up to {size}; "
        "the Aside window will switch tabs while it submits and downloads")

    # Seed with files already on disk so a rerun cannot save a duplicate of a
    # row that finished earlier.
    seen = {}
    for item in manifest["items"]:
        path = out_dir / item["filename"]
        if item["status"] == "Generated" and path.exists():
            seen[hashlib.sha256(path.read_bytes()).hexdigest()] = item["filename"]

    saved, previews, blocked = 0, [], ""
    # One retry pass, inside the same run. A batch of four measured 97s against
    # a 105s budget, so on a slow day its last row can miss its turn; sending it
    # again in the next batch is cheaper than making the caller rerun.
    queue = [(batch, False) for batch in batches]
    retry = []
    while queue and not blocked:
        batch, is_retry = queue.pop(0)
        if time.time() + REPL_LIMIT > run_started + args.deadline:
            unsent = sum(len(b) for b, _r in queue) + len(batch)
            log(f"deadline: {unsent} row(s) left unsent; rerun to take them")
            break
        label = "retry" if is_retry else "batch"
        log(f"{label}: " + ", ".join(it["filename"] for it in batch))
        got, blocked, failed = run_batch(aside, batch, manifest, manifest_path,
                                         out_dir, seen, previews)
        saved += got
        if not is_retry:
            retry += failed
        if not queue and retry:
            log(f"{len(retry)} row(s) failed; trying them once more")
            queue = [(b, True) for b in plan_batches(retry, size)]
            retry = []
    if blocked:
        log(f"stopping: the page went to {blocked[:80]}. That is Google's "
            "unusual-traffic check or a sign-in wall; clear it in the Aside "
            "browser by hand, then rerun. Finished rows are kept.")

    elapsed = time.time() - run_started
    total = sum(1 for it in manifest["items"] if it["status"] == "Generated")
    log(f"saved {saved} this run · manifest {total}/{len(manifest['items'])} · "
        f"{elapsed:.0f}s elapsed")
    if previews:
        log(f"** {len(previews)} row(s) saved at the {PREVIEW_EDGE}px preview size "
            f"instead of the original: {', '.join(previews)}")
    left = [it["filename"] for it in manifest["items"] if it["status"] in RETRYABLE]
    if left:
        log(f"{len(left)} row(s) still Pending/Failed with last_error set; rerun "
            "the same command to retry only those")
        sys.exit(2)


if __name__ == "__main__":
    main()
