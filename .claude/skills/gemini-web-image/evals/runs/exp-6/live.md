# exp-6 live check — 2026-09-23

macOS, Aside CLI 1.26.916.1741, Gemini UI in Korean. Manifest built in a
scratch folder, not in `projects/`.

## One row (smoke test)

| Row | Size | Timing |
|---|---|---|
| cover.png (16:9) | 2752x1536, 5,149,990 bytes | submit 16s, ready at 11s, download 16.3s — **46s** total |

## Five rows — one batch of four, one batch of one

| Row | Ratio asked | Saved | Submit | Ready at | Download |
|---|---|---|---:|---:|---:|
| a_mountain.png | 16:9 | 2752x1536 | 17s | 0s | 13.2s |
| b_greenhouse.png | 16:9 | 2752x1536 | 5s | 13s | 13.4s |
| c_bicycle.png | 16:9 | 2752x1536 | 5s | 27s | 17.4s |
| d_library.png | 4:3 | 2400x1792 | 6s | 44s | 15.6s |
| e_teacup.png | 1:1 | 2048x2048 | 5s | 13s | 11.4s |

"Ready at" counts from the end of the batch's last submission, when the wait
loop starts; the first row was already finished by then.

- Batch of four: **97s** against the 105s budget. Batch of one: 31s. Run total
  **128s**.
- 5/5 `Generated`, exit code 0.
- Five distinct SHA-256 prefixes: `773c7ec44fd7`, `8d1350a4753e`,
  `a3111c421833`, `ca9f5138105f`, `db788fbff1f9`.
- Every ratio within 0.1% of the request; every file an original, none at the
  1024px preview size.
- Gemini tabs left open in the Aside browser afterwards: **0**.

The 97s batch is what led to the in-run retry pass and to not starting a
download with less than 22s of budget left: on a slower day the fourth row
would otherwise push the call past the REPL's 120s limit.
