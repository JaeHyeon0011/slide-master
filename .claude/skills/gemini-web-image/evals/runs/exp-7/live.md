# exp-7 live check — 2026-09-25 (background redesign)

macOS, Aside CLI 1.26.916.1741, Gemini UI in Korean. Scratch manifests, mixed
ratios in every batch so a cross-row image shows up as a wrong ratio.

## Why the redesign

A professor on Windows reported that image generation only worked with the
Aside window maximized and in front. Chromium on Windows stops painting a
window it considers occluded (covered, minimized, other virtual desktop,
locked screen); macOS has no such mode. The committed version waited on a
decoded image and on Playwright's actionability checks, both of which need
painting.

## Findings on the way (all measured today)

| Change tried | Result |
|---|---|
| Aside hidden, diagnostic | `visibilityState` stayed "visible", rAF kept firing, but a finished image had `naturalWidth` 0 and `decode()` threw while its download button existed |
| Minimized window | still "visible"; rAF dropped from 21 to 8 per second, not to 0 — macOS cannot fully reproduce Windows |
| DOM click + `saveAs()` (serial, tab in front) | every second row saved the previous row's file (visible and hidden alike) |
| DOM click vs `locator.click()`, `download.path()`, tab in front, 1.5s apart | 4/4 correct for both click kinds — the click was not the cause |
| `path()` instead of `saveAs()` | 2/2 correct |
| Background text entry (no bringToFront, Aside hidden) | `insertText` after DOM focus: 103/103 chars; `execCommand`: 103/103; synthetic paste: 0 |
| Four concurrent downloads | all four received the first tab's file |
| Download clicked in a background tab | that tab's waiter got nothing in 16s; later waiters got it |
| Direct fetch of the image URL | 403 from the REPL, CORS failure in the page |
| Hooking anchor clicks / createObjectURL during download | no anchor click; only 83 KB preview blobs — the original is not produced in-page |
| Activate tab before download, serial, no pause | every second row got the previous download's name (caught by the name guard, nothing wrong saved) |
| + 1.5s pause after each download | **4/4 correct** |

## Final design, three conditions

| Aside window | Rows | Result | Wall clock | Window afterwards |
|---|---:|---|---:|---|
| "Minimized" (unverified, see below) | 4 | 4/4 | 78s | — |
| App hidden | 5 (4 + 1) | 5/5 | 117s (86s + 31s) | still hidden |
| Visible | 4 | 4/4 | 79s | — |
| "Minimized" (unverified) | 10 (4 + 4 + 2) | 10/10 | 203s (79 + 76 + 48) | — |
| App hidden, browser window off-screen (CGWindowList) before/during/after | 10 (4 + 4 + 2) | 10/10 | 200s (81 + 75 + 44) | still hidden |

23 of 23 originals (2752x1536 / 2400x1792 / 2048x2048), 23 distinct SHA-256 (per run),
no re-click needed, 0 Gemini tabs left open.

The ten-row run is the speed comparison: the Kimi WebBridge path took 272s for
ten originals on 2026-08-20; this took 203s with Aside minimized.

**Correction.** The "minimized" rows used System Events' AXMinimized on Aside's
windows. Afterwards CGWindowList showed the 1674x945 browser window on screen
while the accessibility API listed no windows at all, so the minimize most
likely reached only accessory windows (settings, download history). Those rows
are kept above as measured but are not evidence of background operation. The
hidden-app runs are: `set visible of process "Aside" to false` hides every
window, and the 10-row run checked the browser window off-screen at +30s, +90s
and +150s. The speed comparison uses that run: 200s against Kimi's 272s.
