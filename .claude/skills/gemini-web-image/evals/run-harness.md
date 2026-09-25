# Run Harness — gemini-web-image

Repeatable procedure for checking that this skill still teaches its own
rules. Run it after changing SKILL.md or the script.

```bash
# one plan per scenario, written by an agent whose only authority is the skill
python3 .claude/skills/gemini-web-image/evals/score.py <dir-of-plans>
```

Every check encodes a failure that actually happened while building this
path. A plan that passes is one that would not repeat it.

> Read a failing plan before changing the skill. Five calibration rounds in
> a row, the first reading blamed the skill for a fault in the checks: a grep
> over free prose scores phrasing as much as understanding.

## History

`exp-1` through `exp-5` scored the Kimi WebBridge version of this skill and
were deleted when the path moved to Aside on 2026-09-23; they live in git
history. The shared prose parsers in `score.py` (`flatten`, `logical_lines`,
`contextual_lines`) were kept, because the faults they fix — hard-wrapped
sentences, prohibitions stated once in a table header or a heading, emphasis
splitting phrases — are properties of how plans are written, not of the bridge.

Before the first Aside round the checks were run against seven deliberately
wrong plans (run image_gen.py instead, reset Needs-Manual rows, fall back to
codex, prepend the ratio line again, reinstall Aside, solve the captcha, open
CLI tabs in the background). Every check that applied failed, which is the
evidence that a pass means something.

The first Aside round (`exp-6`) scored 9/11, and both failures were the
checker's, not the plans'. S6 wrote "can only be cleared by a person" and C8
knew only "by hand"/"the user" after the verb; it also read the plan's message
to the user ("Please open the browser and solve the challenge") as the agent
solving it. S7 refused both requests with the measured reasons, but C9 searched
a flattened text in which `.` stopped at the line break inside a blockquote,
and it read the plan's restatement of the request, a heading phrased as a question, and a quotation of the bring-forward rule as compliance. All three are
the same fault the Kimi rounds kept finding: reading a phrase without the line
around it. The corrected checker scores `exp-6` 11/11 and still fails every
deliberately wrong plan.

## Input

Seven scenarios, `S1`-`S7`, in `scenarios.json`. Scenarios are fixed across
experiments so scores stay comparable.

| Id | Scenario | Checks |
|---|---|---|
| S1 | 6 pending rows, mixed ratios, Aside up | C1 runs the script · C2 tells the user the Aside window may stay covered or minimized · C3 verifies checksums and the 1024px preview case |
| S2 | 2 Generated, 1 Needs-Manual, 4 Failed | C1 · C4 leaves finished and Needs-Manual rows alone, takes the 4 |
| S3 | Aside CLI not installed | C5 stops, names the install, does not fall back to another image path |
| S4 | Prompts already carry a ratio line, one of them wrong | C6 does not add it again, flags the mismatched row |
| S5 | Every row: "Aside isn't running" while the app is open | C7 reads it as the 120s REPL limit and lowers `--batch`, no reinstall |
| S6 | `google.com/sorry/` interstitial | C8 hands the challenge to a person and reruns afterwards |
| S7 | User asks for CLI-opened tabs and downloads without tab activation | C9 keeps the per-download tab activation with its reason · C10 no `aside "<url>"` tabs |

`exp-7` (2026-09-25) follows the background redesign: S7 now asks for
downloads without tab activation instead of background submission, which the
script already does, and C2/C9 were rewritten to match. Scores before `exp-7`
are not comparable on those two checks. Its first scoring was 9/11 and both
misses were the checker again: C7 read the second line of a blockquoted
"Do not / reinstall Aside for this" as advice to reinstall, and C9 read the
plan's title (`# S7 — ... download without activating`) as agreement. Quote
lines and headings are now exempt; `exp-7` scores 11/11 and the deliberately
wrong plans still score 1/11 (the one pass is S2's correct script call).

C10 also runs on every other plan that mentions opening a tab with
`aside "<url>"`, and fails it unless the line is a prohibition.

## Execution

**One subagent per scenario.** Batching several scenarios into one agent
makes their plans correlated — a single misreading fails every plan that
agent wrote — and only its first plan is a cold read, which is the
condition this suite is meant to measure. Dispatch one subagent per
scenario with:

- the full text of `.claude/skills/gemini-web-image/SKILL.md`
- the full text of `.claude/skills/gemini-web-image/scripts/gemini_web_image.py`
- the scenario description
- the instruction: *"Write the exact execution plan you would follow — every
  command in order, and every decision point with the branch you take. Do not
  execute anything. Do not consult outside knowledge; the skill is the only
  authority."*

The subagent's plan text is the run output. It is saved to
`runs/exp-N/<scenario-id>.md`.

Plan scoring measures whether the skill *teaches* the right procedure. That is
exactly the "no trial and error" goal, and it costs no image quota.

## Live check

Every third experiment, additionally run the real script against a five-row
manifest (one batch of four and one of one) and record the result in `runs/exp-N/live.md`. This catches a skill
that scores well on plans while the script itself has drifted.

## Output capture

```
runs/exp-N/
├── S1.md … S7.md      # one plan per scenario
├── scores.json        # per-eval results
└── live.md            # only on every third experiment
```
