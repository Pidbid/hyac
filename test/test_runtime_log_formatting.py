import importlib.util
import sys
import types
from contextlib import contextmanager
from pathlib import Path
from unittest import TestCase


APP_LOGGER_PATH = Path(__file__).resolve().parents[1] / "app" / "core" / "logger.py"


class FakeLogger:
    def __init__(self):
        self.active_extra = {}
        self.seen_messages = []

    @contextmanager
    def contextualize(self, **extra):
        previous_extra = self.active_extra
        self.active_extra = {**previous_extra, **extra}
        try:
            yield
        finally:
            self.active_extra = previous_extra

    def info(self, message):
        self.seen_messages.append((message, dict(self.active_extra)))


fake_logger = FakeLogger()
fake_loguru = types.ModuleType("loguru")
fake_loguru.logger = fake_logger

fake_config = types.ModuleType("core.config")
fake_config.settings = types.SimpleNamespace(DEBUG=False)
sys.modules.setdefault("core.config", fake_config)

spec = importlib.util.spec_from_file_location("hyac_app_core_logger", APP_LOGGER_PATH)
app_logger = importlib.util.module_from_spec(spec)
assert spec and spec.loader
previous_loguru = sys.modules.get("loguru")
sys.modules["loguru"] = fake_loguru
try:
    spec.loader.exec_module(app_logger)
finally:
    if previous_loguru is None:
        sys.modules.pop("loguru", None)
    else:
        sys.modules["loguru"] = previous_loguru

function_runtime_log_context = app_logger.function_runtime_log_context
prefix_runtime_lines = app_logger.prefix_runtime_lines


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


class FunctionRuntimeLogContextTest(TestCase):
    def test_contextualizes_global_loguru_logger_with_function_label(self):
        with function_runtime_log_context(
            app_id="app123",
            function_id="func123",
            function_name="hello",
            runtime_label="[func:func123] ",
        ):
            fake_logger.info("loguru output")

        self.assertEqual(
            fake_logger.seen_messages[-1],
            (
                "loguru output",
                {
                    "app_id": "app123",
                    "function_id": "func123",
                    "function_name": "hello",
                    "runtime_label": "[func:func123] ",
                },
            ),
        )
