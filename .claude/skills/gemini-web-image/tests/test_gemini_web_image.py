"""Contract tests for gemini_web_image.py — no browser, no Aside needed.

Each test pins a rule that, when it was missing, failed silently: a tab left
open, a prompt with its ratio line twice, two rows saving the same file, a
Korean-only selector. Run:

    python3 -m unittest discover .claude/skills/gemini-web-image/tests
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import gemini_web_image as gwi  # noqa: E402


def png(width, height, salt=b""):
    """A byte string whose PNG header reports width x height."""
    return (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
            + width.to_bytes(4, "big") + height.to_bytes(4, "big") + salt)


class BatchScript(unittest.TestCase):
    def setUp(self):
        self.js = gwi.build_batch_js([{"out": "row0.png", "prompt": "a cat"}])

    def test_tabs_come_from_open_tab_and_close_in_finally(self):
        # `aside "<url>"` tabs cannot be closed from the REPL; openTab() tabs can.
        self.assertIn("openTab(URL0)", self.js)
        finally_part = self.js[self.js.index("} finally {"):]
        self.assertIn("closeTab(o.p)", finally_part)

    def test_budget_stays_under_the_repl_limit(self):
        self.assertLess(gwi.BUDGET, gwi.REPL_LIMIT)
        self.assertIn(f"const BUDGET_MS = {gwi.BUDGET} * 1000", self.js)

    def test_prompt_is_inserted_not_filled(self):
        self.assertIn("keyboard.insertText(job.prompt)", self.js)
        self.assertNotIn(".fill(", self.js)
        self.assertNotIn("pressSequentially", self.js)

    def test_both_submit_and_download_bring_the_tab_forward(self):
        submit = self.js[self.js.index("── submit"):self.js.index("── wait")]
        download = self.js[self.js.index("── wait"):self.js.index("} finally {")]
        self.assertIn("await front(p)", submit)
        self.assertIn("await front(o.p)", download)

    def test_selectors_do_not_depend_on_ui_language(self):
        self.assertIn("rich-textarea", self.js)
        self.assertIn("'download'", self.js)
        self.assertNotIn("aria-label", self.js)
        self.assertFalse(any("가" <= ch <= "힣" for ch in self.js),
                         "Korean text in the batch script ties it to one UI language")

    def test_a_download_is_not_started_without_time_to_finish(self):
        self.assertIn("left() < DL_MIN", self.js)

    def test_sending_needs_proof_the_answer_started(self):
        self.assertIn("ok = await started(p)", self.js)
        self.assertIn("r.kind = 'not_sent'", self.js)

    def test_prompt_text_survives_as_a_json_literal(self):
        tricky = 'quote " backslash \\ 한글 `tick` ${x}'
        js = gwi.build_batch_js([{"out": "row0.png", "prompt": tricky}])
        line = js.splitlines()[1]
        payload = line[len("const JOBS = "):-1]
        self.assertEqual(json.loads(payload)[0]["prompt"], tricky)


class RatioLine(unittest.TestCase):
    def test_added_once(self):
        once = gwi.with_ratio("a cat", "16:9")
        self.assertTrue(once.startswith("Generate a 16:9 image"))
        self.assertEqual(gwi.with_ratio(once, "16:9"), once)

    def test_conflicting_ratio_is_reported(self):
        stale = gwi.with_ratio("a cat", "4:3")
        with mock.patch.object(gwi, "log") as log:
            gwi.with_ratio(stale, "16:9")
        self.assertIn("ratio line", log.call_args[0][0])


class Batching(unittest.TestCase):
    def rows(self, n, prompt="p"):
        return [{"filename": f"{i}.png", "prompt": prompt, "aspect_ratio": "16:9",
                 "status": "Pending"} for i in range(n)]

    def test_batches_hold_at_most_four(self):
        sizes = [len(b) for b in gwi.plan_batches(self.rows(10), 4)]
        self.assertEqual(sizes, [4, 4, 2])

    def test_long_prompts_split_under_the_windows_argument_cap(self):
        batches = gwi.plan_batches(self.rows(4, prompt="x" * 12_000), 4)
        self.assertGreater(len(batches), 1)
        for batch in batches:
            jobs = [{"out": f"row{i}.png", "prompt": gwi.with_ratio(it["prompt"], "16:9")}
                    for i, it in enumerate(batch)]
            self.assertLessEqual(len(gwi.build_batch_js(jobs)), gwi.ARG_LIMIT)


class Output(unittest.TestCase):
    def test_parse_result(self):
        out = 'noise\nASIDE_RESULT {"dir": "/s", "rows": {}}\n[ok | 1ms]'
        self.assertEqual(gwi.parse_result(out)["dir"], "/s")
        self.assertIsNone(gwi.parse_result("nothing here"))

    def test_first_error_strips_color(self):
        out = "\x1b[31mError: boom\x1b[0m\n  at x"
        self.assertEqual(gwi.first_error(out), "Error: boom")

    def test_image_size(self):
        self.assertEqual(gwi.image_size(png(2752, 1536)), (2752, 1536))
        self.assertEqual(gwi.image_size(b"junk"), (0, 0))


class FindAside(unittest.TestCase):
    def test_windows_install_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "Aside" / "CLI" / "aside.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"")
            with mock.patch.object(gwi.shutil, "which", return_value=None), \
                    mock.patch.dict(os.environ, {"LOCALAPPDATA": tmp}), \
                    mock.patch.object(gwi.Path, "expanduser",
                                      return_value=Path(tmp) / "missing"):
                self.assertEqual(gwi.find_aside(), str(exe))

    def test_path_wins(self):
        with mock.patch.object(gwi.shutil, "which", return_value="/usr/bin/aside"):
            self.assertEqual(gwi.find_aside(), "/usr/bin/aside")


class RunBatch(unittest.TestCase):
    """run_batch against a fake `aside repl` that has already 'downloaded'."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.session = root / "session"
        (self.session / "artifacts").mkdir(parents=True)
        self.out = root / "images"
        self.out.mkdir()
        self.manifest_path = self.out / "image_prompts.json"
        self.items = [{"filename": f"{c}.png", "prompt": c, "aspect_ratio": "16:9",
                       "status": "Pending"} for c in "abc"]
        self.manifest = {"items": self.items}

    def tearDown(self):
        self.tmp.cleanup()

    def run_with(self, rows, files, seen=None):
        for name, raw in files.items():
            (self.session / "artifacts" / name).write_bytes(raw)
        out = "ASIDE_RESULT " + json.dumps({"dir": str(self.session), "rows": rows})
        previews = []
        with mock.patch.object(gwi, "run_js", return_value=out), \
                mock.patch.object(gwi, "log"):
            result = gwi.run_batch("aside", self.items, self.manifest,
                                   self.manifest_path, self.out,
                                   {} if seen is None else seen, previews)
        return result, previews

    def test_saved_rows_are_written_back_at_once(self):
        (saved, blocked, failed), _ = self.run_with(
            {"row0.png": {"ok": True}, "row1.png": {"ok": True},
             "row2.png": {"ok": False, "kind": "no_image", "probe": {"url": "", "text": ""}}},
            {"row0.png": png(2752, 1536, b"a"), "row1.png": png(2752, 1536, b"b")})
        self.assertEqual((saved, blocked), (2, ""))
        self.assertEqual([it["filename"] for it in failed], ["c.png"])
        on_disk = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual([it["status"] for it in on_disk["items"]],
                         ["Generated", "Generated", "Failed"])
        self.assertIn("no image", on_disk["items"][2]["last_error"])
        self.assertTrue((self.out / "a.png").exists())

    def test_identical_files_fail_the_second_row(self):
        same = png(2752, 1536, b"same")
        (saved, _b, failed), _ = self.run_with(
            {"row0.png": {"ok": True}, "row1.png": {"ok": True},
             "row2.png": {"ok": True}},
            {"row0.png": same, "row1.png": same, "row2.png": png(2752, 1536, b"c")})
        self.assertEqual(saved, 2)
        self.assertEqual(self.items[1]["status"], "Failed")
        self.assertIn("identical", self.items[1]["last_error"])

    def test_a_file_matching_an_earlier_run_is_rejected(self):
        old = png(2752, 1536, b"old")
        seen = {hashlib.sha256(old).hexdigest(): "earlier.png"}
        (saved, _b, _f), _ = self.run_with(
            {"row0.png": {"ok": True}}, {"row0.png": old}, seen=seen)
        self.assertEqual(saved, 0)
        self.assertEqual(self.items[0]["status"], "Failed")

    def test_preview_sized_files_are_reported(self):
        _r, previews = self.run_with({"row0.png": {"ok": True}},
                                     {"row0.png": png(1024, 572)})
        self.assertEqual(previews, ["a.png"])

    def test_challenge_page_stops_the_run(self):
        (saved, blocked, _f), _ = self.run_with(
            {"row0.png": {"ok": False, "kind": "no_box",
                          "probe": {"url": "https://www.google.com/sorry/index?x", "text": ""}}},
            {})
        self.assertEqual(saved, 0)
        self.assertIn("/sorry/", blocked)

    def test_no_result_marks_every_row_failed(self):
        with mock.patch.object(gwi, "run_js",
                               return_value="Aside isn't running on this machine"), \
                mock.patch.object(gwi, "log"):
            saved, _b, failed = gwi.run_batch("aside", self.items, self.manifest,
                                              self.manifest_path, self.out, {}, [])
        self.assertEqual(saved, 0)
        self.assertEqual(len(failed), 3)
        self.assertIn("120s", self.items[0]["last_error"])


class Main(unittest.TestCase):
    def test_needs_manual_rows_are_never_sent_and_failures_retry_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "image_prompts.json"
            items = [{"filename": f"{i}.png", "prompt": "p", "aspect_ratio": "1:1",
                      "status": "Pending"} for i in range(5)]
            items.append({"filename": "mine.png", "prompt": "p", "aspect_ratio": "1:1",
                          "status": "Needs-Manual"})
            path.write_text(json.dumps({"items": items}), encoding="utf-8")
            calls = []

            def fake(aside, batch, *rest):
                calls.append([it["filename"] for it in batch])
                for it in batch:
                    it["status"] = "Generated"
                if len(calls) == 1:
                    batch[-1]["status"] = "Failed"
                    return len(batch) - 1, "", [batch[-1]]
                return len(batch), "", []

            argv = ["x", "--manifest", str(path)]
            with mock.patch.object(gwi, "find_aside", return_value="aside"), \
                    mock.patch.object(gwi, "run_batch", side_effect=fake), \
                    mock.patch.object(gwi, "log"), mock.patch.object(sys, "argv", argv):
                gwi.main()
        self.assertEqual(calls, [["0.png", "1.png", "2.png", "3.png"], ["4.png"], ["3.png"]])
        self.assertNotIn("mine.png", sum(calls, []))


if __name__ == "__main__":
    unittest.main()
