#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from lsp.shim import PRELOAD_CONTENT_HEADER, USER_CODE_END_MARKER, USER_CODE_START_MARKER
from lsp_sidecar import formatter


class LspSidecarFormatterTest(unittest.TestCase):
    def test_run_formatter_dedents_user_code_between_markers(self):
        source = (
            "# shim\n"
            f"{USER_CODE_START_MARKER}\n"
            "    def handler(ctx):\n"
            "        x=1\n"
            f"{USER_CODE_END_MARKER}\n"
        )

        def fake_autopep8(candidate: str):
            if "\n    def handler" in candidate:
                return candidate, False
            return candidate.replace("x=1", "x = 1"), True

        with patch.object(formatter, "run_autopep8", side_effect=fake_autopep8):
            result = formatter.run_formatter(source)

        self.assertIsNotNone(result)
        self.assertIn("\ndef handler(ctx):\n", result)
        self.assertIn("    x = 1\n", result)
        self.assertNotIn("\n    def handler(ctx):\n", result)

    def test_run_formatter_repairs_missing_block_indent_without_dedenting_return(self):
        source = (
            "import json\n"
            "\n"
            "async def handler(ctx, request):\n"
            'print("123")\n'
            '    return {"code": 0, "msg": "success", "data": "Hello, World!"}\n'
        )

        def fake_autopep8(candidate: str):
            return candidate, formatter.is_valid_python(candidate)

        with patch.object(formatter, "run_autopep8", side_effect=fake_autopep8):
            result = formatter.run_formatter(source)

        self.assertIn('    print("123")\n', result)
        self.assertIn(
            '    return {"code": 0, "msg": "success", "data": "Hello, World!"}\n',
            result,
        )
        self.assertNotIn('\nreturn {"code": 0', result)

    def test_run_formatter_keeps_user_import_between_markers(self):
        user_code = (
            "import json\n"
            "\n"
            "async def handler(ctx, request):\n"
            'print("123")\n'
            '    return {"code": 0, "msg": "success", "data": "Hello, World!"}\n'
        )
        source = (
            f"{PRELOAD_CONTENT_HEADER}\n"
            f"{USER_CODE_START_MARKER}\n"
            f"{user_code}\n"
            f"{USER_CODE_END_MARKER}\n"
        )

        def fake_autopep8(candidate: str):
            return candidate, formatter.is_valid_python(candidate)

        with patch.object(formatter, "run_autopep8", side_effect=fake_autopep8):
            result = formatter.run_formatter(source)

        start = result.find(USER_CODE_START_MARKER) + len(USER_CODE_START_MARKER)
        end = result.find(USER_CODE_END_MARKER)
        user_result = result[start:end].lstrip("\n")

        self.assertIn("import json\n", user_result)
        self.assertIn("async def handler(ctx, request):\n", user_result)
        self.assertIn('    print("123")\n', user_result)


if __name__ == "__main__":
    unittest.main()
