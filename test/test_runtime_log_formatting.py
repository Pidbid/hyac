import sys
import types
from pathlib import Path
from unittest import TestCase


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

fake_loguru = types.ModuleType("loguru")
fake_loguru.logger = object()
sys.modules.setdefault("loguru", fake_loguru)

fake_config = types.ModuleType("core.config")
fake_config.settings = types.SimpleNamespace(DEBUG=False)
sys.modules.setdefault("core.config", fake_config)

from core.logger import prefix_runtime_lines  # noqa: E402


class PrefixRuntimeLinesTest(TestCase):
    def test_prefixes_each_traceback_line_for_function_filtering(self):
        traceback_text = "Traceback (most recent call last):\n  File \"<string>\", line 1\nSyntaxError: invalid syntax"

        result = prefix_runtime_lines(traceback_text, "[func:abc123] ")

        self.assertEqual(
            result,
            "[func:abc123] Traceback (most recent call last):\n"
            "[func:abc123]   File \"<string>\", line 1\n"
            "[func:abc123] SyntaxError: invalid syntax",
        )

    def test_returns_original_text_when_runtime_label_is_empty(self):
        traceback_text = "SyntaxError: invalid syntax"

        result = prefix_runtime_lines(traceback_text, "")

        self.assertEqual(result, traceback_text)
