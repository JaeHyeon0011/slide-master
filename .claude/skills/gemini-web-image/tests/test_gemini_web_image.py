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
        self.submit = self.js[self.js.index("── submit"):self.js.index("── wait")]
        self.download = self.js[self.js.index("const download = "):self.js.index("try {\n  // ── submit")]

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
        self.assertIn("execCommand('insertText'", self.js)
        self.assertNotIn(".fill(", self.js)
        self.assertNotIn("pressSequentially", self.js)

    def test_submission_never_brings_a_tab_forward(self):
        # A covered or minimized window must stay where the user left it.
        self.assertNotIn("bringToFront", self.submit)

    def test_only_the_download_activates_its_tab(self):
        # Aside routes a download to the window's active tab.
        self.assertIn("bringToFront", self.download)
        self.assertEqual(self.js.count("bringToFront"), 1)

    def test_nothing_waits_on_the_window_being_painted(self):
        # An occluded window stops painting: the image never decodes and
        # Playwright's actionability checks never pass. Readiness is the
        # download button, and every click is a DOM click.
        self.assertNotIn("naturalWidth", self.js)
        self.assertNotIn(".hover(", self.js)
        self.assertNotIn("state: 'visible'", self.js)
        self.assertNotRegex(self.js, r"locator\([^)]*\)(?:\.first\(\))?\.click\(")
        self.assertIn("clickIcon(o.p, 'download')", self.download)

    def test_downloads_are_read_from_their_own_path_one_at_a_time(self):
        # saveAs() handed back the previous download; concurrent downloads all
        # received the first tab's file.
        self.assertIn("dl.path()", self.download)
        self.assertNotIn("saveAs", self.js)
        self.assertIn("await download(o)", self.js)
        self.assertNotIn("Promise.all", self.js)

    def test_a_download_named_like_an_earlier_one_is_rejected(self):
        self.assertIn("seenNames.indexOf(dl.suggestedFilename())", self.download)
        self.assertIn("seenNames.push(dl.suggestedFilename())", self.download)

    def test_a_lost_download_stops_the_rest_of_the_batch(self):
        # A download that arrives after its waiter gave up goes to the next
        # waiter, which would save it as its own.
        self.assertIn("lost = true", self.download)
        self.assertIn("!lost", self.js)
        self.assertIn("'after_lost'", self.js)

    def test_names_saved_by_earlier_batches_are_carried_in(self):
        js = gwi.build_batch_js([{"out": "row0.png", "prompt": "p"}],
                                seen_names=["Gemini_Generated_Image_abc.png"])
        self.assertIn('const seenNames = ["Gemini_Generated_Image_abc.png"];', js)

    def test_downloads_are_spaced_apart(self):
        # Back-to-back clicks: the second was dropped and handed the first's file.
        self.assertIn("await sleep(1500)", self.download)

    def test_a_download_is_not_started_without_time_to_finish(self):
        self.assertIn("left() < DL_MIN", self.js)

    def test_sending_needs_proof_the_answer_started(self):
        self.assertIn("ok = await started(p)", self.js)
        self.assertIn("r.kind = 'not_sent'", self.js)

    def test_one_row_failing_does_not_end_the_batch(self):
        self.assertIn("r.kind = 'exception'", self.submit)

    def test_selectors_do_not_depend_on_ui_language(self):
        self.assertIn("rich-textarea", self.js)
        self.assertIn("'download'", self.js)
        self.assertNotIn("aria-label", self.js)
        self.assertFalse(any("\uac00" <= ch <= "\ud7a3" for ch in self.js),
                         "Korean text in the batch script ties it to one UI language")

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

    def test_color_codes_do_not_hide_the_result(self):
        out = '\x1b[2mASIDE_RESULT {"dir": "/s", "rows": {}}\x1b[0m'
        self.assertEqual(gwi.parse_result(out)["dir"], "/s")

    def test_first_error_strips_color(self):
        out = "\x1b[31mError: boom\x1b[0m\n  at x"
        self.assertEqual(gwi.first_error(out), "Error: boom")

    def test_image_size(self):
        self.assertEqual(gwi.image_size(png(2752, 1536)), (2752, 1536))
        self.assertEqual(gwi.image_size(b"junk"), (0, 0))


class FindAside(unittest.TestCase):
    def test_windows_install_location(self):
        # install.ps1: %LOCALAPPDATA%\\Aside\\CLI\\current\\aside.exe (a junction
        # to versions\\<v>) is what goes on PATH.
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "Aside" / "CLI" / "current" / "aside.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"")
            with mock.patch.object(gwi.shutil, "which", return_value=None), \
                    mock.patch.dict(os.environ, {"LOCALAPPDATA": tmp}), \
                    mock.patch.object(gwi.Path, "expanduser",
                                      return_value=Path(tmp) / "missing"):
                self.assertEqual(gwi.find_aside(), str(exe))

    def test_windows_version_folder_when_current_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "Aside" / "CLI" / "versions"
            for version in ("1.26.900.1", "1.26.916.1741"):
                (base / version).mkdir(parents=True)
                (base / version / "aside.exe").write_bytes(b"")
            with mock.patch.object(gwi.shutil, "which", return_value=None), \
                    mock.patch.dict(os.environ, {"LOCALAPPDATA": tmp}), \
                    mock.patch.object(gwi.Path, "expanduser",
                                      return_value=Path(tmp) / "missing"):
                self.assertTrue(gwi.find_aside().endswith(
                    os.path.join("1.26.916.1741", "aside.exe")))

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

    def test_saved_download_names_are_collected_for_the_next_batch(self):
        names = []
        out = "ASIDE_RESULT " + json.dumps({"dir": str(self.session), "rows": {
            "row0.png": {"ok": True, "name": "Gemini_Generated_Image_a.png"}}})
        (self.session / "artifacts" / "row0.png").write_bytes(png(2752, 1536, b"a"))
        with mock.patch.object(gwi, "run_js", return_value=out), \
                mock.patch.object(gwi, "log"):
            gwi.run_batch("aside", self.items, self.manifest, self.manifest_path,
                          self.out, {}, [], names)
        self.assertEqual(names, ["Gemini_Generated_Image_a.png"])

    def test_a_wrong_ratio_is_another_rows_image(self):
        # Every row asks 16:9; a 1:1 file cannot be this row's.
        (saved, _b, failed), _ = self.run_with({"row0.png": {"ok": True}},
                                               {"row0.png": png(2048, 2048)})
        self.assertEqual(saved, 0)
        self.assertEqual(self.items[0]["status"], "Failed")
        self.assertIn("likely another row", self.items[0]["last_error"])
        self.assertFalse((self.out / "a.png").exists())

    def test_a_batch_error_is_kept_on_every_unresolved_row(self):
        out = "ASIDE_RESULT " + json.dumps({"dir": str(self.session), "rows": {
            "__batch__": {"kind": "exception", "error": "Target closed"}}})
        with mock.patch.object(gwi, "run_js", return_value=out), \
                mock.patch.object(gwi, "log"):
            gwi.run_batch("aside", self.items, self.manifest, self.manifest_path,
                          self.out, {}, [])
        self.assertTrue(all("Target closed" in it["last_error"] for it in self.items))

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
