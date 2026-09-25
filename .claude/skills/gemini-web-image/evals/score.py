#!/usr/bin/env python3
"""Score one experiment's plans against the gemini-web-image eval suite.

Usage: python3 score.py runs/exp-N
"""
import json
import re
import sys
from pathlib import Path

# "Never open tabs that way" and "no background tabs" are negations, and plans
# have been failed for writing prohibitions like that. \bno\b does not match "not"/"nothing",
# so the bare quantifier can be added without swallowing unrelated prose.
NEGATION = re.compile(
    r"never|\bno\b|not use|don't|do not|avoid|forbidden|instead of|rather than"
    r"|금지|쓰지|사용하지|대신", re.IGNORECASE)

# Plans are markdown. Emphasis lands mid-phrase ("do **not** use", "Submits
# **all** rows first") and split every phrase match until it was stripped.
# Underscores are deliberately kept: stripping them turned RATIO_PREFIX into
# RATIOPREFIX and gemini_web_image into geminiwebimage, so every
# check that named a snake_case identifier could never fire. Four plans that
# quoted those identifiers exactly were scored as failures on that alone.
MARKUP = re.compile(r"[*`]+")

# Where a paragraph starts, for unwrapping.
BLOCK_START = re.compile(r"^\s*(?:[-*+>|#]|\d+[.)])")


def flatten(text):
    return MARKUP.sub("", text)


def logical_lines(text):
    """Undo the hard wrapping before any per-line test runs.

    Plans are wrapped at ~78 columns, so a sentence is routinely split across
    two lines and a per-line test sees half of it. That misread S3: the plan
    quoted the script's own "Start the daemon" error, the opening quotation mark
    fell on one line and the imperative on the next, and the line carrying the
    imperative looked like the plan improvising. The same hazard applies to
    every check that pairs a term with a qualifier on its line.
    """
    out = []
    for raw in flatten(text).splitlines():
        if not raw.strip():
            out.append("")
        elif out and out[-1].strip() and not BLOCK_START.match(raw):
            out[-1] = out[-1].rstrip() + " " + raw.strip()
        else:
            out.append(raw)
    return out


LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")


def contextual_lines(text):
    """Each logical line, carrying the structure that qualifies it.

    Plans state a prohibition once, in a table header ("| Do not | Why |") or a
    heading ("Things I deliberately do not do"), and then list the forbidden
    calls plainly underneath. Read alone, those rows are indistinguishable from
    instructions, and two plans that forbade find_tab in exactly this shape were
    scored as planning to call it. A table row is therefore read together with
    its header row, and a list item with whatever introduced the list.
    """
    out, table_header, list_intro = [], "", ""
    for line in logical_lines(text):
        stripped = line.strip()
        is_row = stripped.startswith("|")
        if not is_row:
            table_header = ""
        elif not table_header:
            table_header = stripped
        if stripped and not is_row and not LIST_ITEM.match(line):
            list_intro = stripped

        if is_row and table_header != stripped:
            out.append(table_header + " ¦ " + line)
        elif LIST_ITEM.match(line):
            out.append(list_intro + " ¦ " + line)
        else:
            out.append(line)
    return out


def lines_with(text, needle):
    return [ln for ln in contextual_lines(text) if needle.lower() in ln.lower()]


def negated(line):
    return bool(NEGATION.search(line))


def any_line(text, pattern):
    return any(re.search(pattern, ln, re.I) for ln in contextual_lines(text))


def c1_runs_script(text, sid):
    if sid not in ("S1", "S2"):
        return None
    return bool(re.search(r"gemini_web_image\.py\s+(?:\\\s*)?--manifest", flatten(text)))


def c2_says_user_can_keep_working(text, sid):
    # The run is built to survive a covered or minimized Aside window. A user
    # who is told to keep the window in front loses the point of it.
    if sid != "S1":
        return None
    flat = " ".join(logical_lines(text))
    tells = re.search(r"(cover|minimi[sz]|background|keep working|other work|다른 작업|최소화|가려)", flat, re.I)
    wrong = any(re.search(r"(keep|leave).{0,40}(aside|window).{0,40}(front|foreground|visible|maximi)", ln, re.I)
                and not negated(ln) for ln in contextual_lines(text))
    return bool(tells) and not wrong


def c3_verifies_output(text, sid):
    if sid != "S1":
        return None
    flat = flatten(text)
    return (bool(re.search(r"sha-?256|shasum|checksum", flat, re.I))
            and "1024" in flat)


def c4_leaves_finished_and_manual_rows(text, sid):
    if sid != "S2":
        return None
    manual = [ln for ln in lines_with(text, "Needs-Manual")]
    touched = any(re.search(r"\b(submit|send|generate|reset|set .{0,20}(Pending|Failed))\b", ln, re.I)
                  and not negated(ln) for ln in manual)
    return bool(manual) and not touched and bool(re.search(r"\b4\b|four", flatten(text), re.I))


def c5_precondition_stop(text, sid):
    if sid != "S3":
        return None
    flat = flatten(text)
    stops = re.search(r"stop|halt|abort|중단", flat, re.I)
    # Falling back to another image path is the caller's decision. A plan that
    # reaches for image_gen.py or codex from inside this skill is improvising.
    improvises = any(re.search(r"image_gen\.py|codex|kimi|webbridge", ln, re.I)
                     and not negated(ln)
                     and not re.search(r"caller|hand (?:it )?back|decision|ppt-master", ln, re.I)
                     for ln in contextual_lines(text))
    names_it = re.search(r"install|aside cli|releases\.aside\.com", flat, re.I)
    return bool(stops) and bool(names_it) and not improvises


def c6_no_double_ratio(text, sid):
    if sid != "S4":
        return None
    # Row 2 must go through as-is (the script sees the line and adds nothing);
    # row 3 is a manifest error the plan must surface, not a line to add again.
    adds_again = any(re.search(r"(prepend|add|insert).{0,40}(ratio line|Generate a)", ln, re.I)
                     and re.search(r"row 2|second row", ln, re.I)
                     and not negated(ln) for ln in contextual_lines(text))
    flags_row3 = any_line(text, r"(row 3|third row).{0,120}(conflict|mismatch|contradict|wrong|1:1)"
                                r"|(conflict|mismatch|contradict).{0,120}(row 3|third row)")
    return flags_row3 and not adds_again


def c7_reads_repl_limit(text, sid):
    if sid != "S5":
        return None
    flat = flatten(text)
    knows = re.search(r"120\s?s|120[- ]second", flat, re.I)
    acts = re.search(r"--batch|smaller batch|lower .{0,20}batch|batch .{0,20}(2|two|3|three)", flat, re.I)
    # A blockquote line is the plan quoting the skill, whose own wording is
    # "Do not reinstall Aside for this" — often split across quote lines.
    reinstall = any(re.search(r"reinstall|install\.sh|install\.ps1|restart (?:the )?aside", ln, re.I)
                    and not negated(ln) and not re.match(r"\s*>", ln)
                    for ln in contextual_lines(text))
    return bool(knows) and bool(acts) and not reinstall


def c8_challenge_by_hand(text, sid):
    if sid != "S6":
        return None
    flat = " ".join(logical_lines(text))
    hands_off = re.search(r"(user|person|by hand|manually|사람|직접).{0,80}(clear|solve|pass|complete|풀)", flat, re.I) \
        or re.search(r"(clear|solve).{0,60}(by hand|manually|the user|a person|a human|themselves)", flat, re.I)
    # A line addressed to the user ("Please open the browser and solve it") hands
    # the challenge over; it is not the agent solving it.
    solves = any(re.search(r"(click|solve|answer|complete).{0,30}(captcha|checkbox|challenge|recaptcha)", ln, re.I)
                 and not negated(ln)
                 and not re.search(r"user|person|human|by hand|manually|themselves|please|\byou\b|^\s*>", ln, re.I)
                 for ln in contextual_lines(text))
    reruns = re.search(r"rerun|re-run|run .{0,20}again", flat, re.I)
    return bool(hands_off) and bool(reruns) and not solves


def c9_keeps_download_activation(text, sid):
    # Aside hands a download to its window's active tab; downloading from a
    # background tab gave rows each other's files. The plan must keep the one
    # tab activation, say why, and say it does not raise the window.
    if sid != "S7":
        return None
    flat = " ".join(logical_lines(text))
    explains = re.search(r"(active tab|activat|bringToFront).{0,200}(download|another row|wrong|same file|previous|waiter|routes?)", flat, re.I) \
        or re.search(r"download.{0,200}(active tab|activat)", flat, re.I)
    # Headings name the request; they do not agree to it.
    complies = any(re.search(r"(download).{0,60}(without activat|background tab|not activat)", ln, re.I)
                   and not negated(ln)
                   and not ln.rstrip().endswith("?")
                   and not re.match(r"\s*#", ln)
                   and not re.search(r"user (?:says|asks)|they ask|ask(?:s|ed)? to|request|because|wrong|another row|previous|fail", ln, re.I)
                   for ln in contextual_lines(text))
    return bool(explains) and not complies


CLI_TAB = re.compile(r"aside\s+[\"']https?://", re.I)


def c10_no_cli_tabs(text, sid):
    # Tabs opened with `aside "<url>"` cannot be closed from the REPL. Any plan
    # that mentions opening them must be saying not to.
    hits = [ln for ln in contextual_lines(text) if CLI_TAB.search(ln)]
    if sid != "S7" and not hits:
        return None
    if sid == "S7" and not hits:
        return any_line(text, r"openTab|cannot be closed|can't be closed|stay open|left open")
    return all(negated(ln) or re.search(r"cannot be closed|can't be closed|stays?|left open|user asked|you asked", ln, re.I)
               for ln in hits)


BINARY = [
    ("C1_runs_script", c1_runs_script),
    ("C2_says_user_can_keep_working", c2_says_user_can_keep_working),
    ("C3_verifies_output", c3_verifies_output),
    ("C4_leaves_finished_and_manual_rows", c4_leaves_finished_and_manual_rows),
    ("C5_precondition_stop", c5_precondition_stop),
    ("C6_no_double_ratio", c6_no_double_ratio),
    ("C7_reads_repl_limit", c7_reads_repl_limit),
    ("C8_challenge_by_hand", c8_challenge_by_hand),
    ("C9_keeps_download_activation", c9_keeps_download_activation),
    ("C10_no_cli_tabs", c10_no_cli_tabs),
]


def main():
    run_dir = Path(sys.argv[1])
    results, passes, applicable = {}, 0, 0
    for plan in sorted(run_dir.glob("S*.md")):
        sid = plan.stem
        text = plan.read_text(encoding="utf-8")
        row = {}
        for name, fn in BINARY:
            verdict = fn(text, sid)
            if verdict is None:
                row[name] = "n/a"
                continue
            applicable += 1
            passes += bool(verdict)
            row[name] = bool(verdict)
        results[sid] = row

    summary = {
        "binary_passes": passes,
        "binary_applicable": applicable,
        "binary_pass_rate": round(passes / applicable, 4) if applicable else 0.0,
        "per_scenario": results,
    }
    (run_dir / "scores.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
