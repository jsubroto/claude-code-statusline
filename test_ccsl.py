#!/usr/bin/env python3

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccsl import _cols, generate_script, render_preview, update_settings


class TestCols(unittest.TestCase):
    def test_ascii(self):
        self.assertEqual(_cols("hello"), 5)

    def test_emoji(self):
        self.assertEqual(_cols("💰"), 2)

    def test_mixed(self):
        self.assertEqual(_cols("💰 $0.04"), 8)



class TestRenderPreview(unittest.TestCase):
    def test_all_fields(self):
        keys = ["model", "dir", "context", "cost", "git", "duration"]
        out = render_preview(keys, "default")
        self.assertIn("[", out)  # model bracket
        self.assertIn("$", out)  # cost
        self.assertIn("│", out)  # separator

    def test_empty_selection(self):
        self.assertEqual(render_preview([], "default"), "(nothing selected)")

    def test_single_field_no_separator(self):
        out = render_preview(["model"], "default")
        self.assertNotIn("│", out)


class TestGenerateScript(unittest.TestCase):
    def _script(self, keys, theme="default"):
        return generate_script(keys, theme)

    def test_cost_format(self):
        s = self._script(["cost"])
        self.assertIn("{cost:.2f}", s)

    def test_bar_included(self):
        s = self._script(["context"])
        self.assertIn("{bar}", s)
        self.assertIn("{used_k}", s)

    def test_mono_no_ansi(self):
        s = self._script(["model"], "mono")
        self.assertNotIn("\\033[", s.split("parts.append")[1])

    def test_only_enabled_fields(self):
        s = self._script(["model"])
        self.assertNotIn("cost", s.split("parts =")[1])

    def test_session_reads_name_then_transcript(self):
        s = self._script(["session"])
        self.assertIn("session_name", s)
        self.assertIn("transcript_path", s)

    def test_session_absent_when_not_enabled(self):
        s = self._script(["model"])
        self.assertNotIn("transcript_path", s)


class TestUpdateSettings(unittest.TestCase):
    def test_writes_statusline_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            script = Path(tmp) / "ccsl_statusline.sh"
            with (
                patch("ccsl.CLAUDE_SETTINGS", settings),
                patch("ccsl.STATUSLINE_SCRIPT", script),
            ):
                update_settings()
            data = json.loads(settings.read_text())
            self.assertEqual(data["statusLine"]["type"], "command")

    def test_preserves_existing_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text(json.dumps({"theme": "dark"}))
            script = Path(tmp) / "ccsl_statusline.sh"
            with (
                patch("ccsl.CLAUDE_SETTINGS", settings),
                patch("ccsl.STATUSLINE_SCRIPT", script),
            ):
                update_settings()
            data = json.loads(settings.read_text())
            self.assertEqual(data["theme"], "dark")


if __name__ == "__main__":
    unittest.main()
