from __future__ import annotations

import ast
import os
import subprocess
import tempfile
import textwrap
from typing import Callable

from lsp.shim import USER_CODE_END_MARKER, USER_CODE_START_MARKER


def run_formatter(source: str) -> str:
    """Run autopep8 with a dedent fallback for indented user snippets."""
    user_code = extract_user_code(source)
    if user_code is not None:
        formatted_user_code = run_user_code_formatter(user_code.lstrip("\n"))
        return replace_user_code(source, formatted_user_code)

    for candidate in formatting_candidates(source):
        formatted, ok = run_autopep8(candidate)
        if ok and is_valid_python(formatted):
            return formatted
    return source


def run_user_code_formatter(source: str) -> str:
    """Format only user code so imports cannot move outside HYAC markers."""
    for candidate in formatting_candidates(source):
        formatted, ok = run_autopep8(candidate)
        if ok and is_valid_python(formatted):
            return formatted
    return source


def formatting_candidates(source: str) -> list[str]:
    """Build conservative formatting candidates, ordered from least invasive."""
    candidates = [source]
    for candidate in (
        repair_missing_block_indentation(source),
        format_dedented_source(source),
    ):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def run_autopep8(
    source: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[str, bool]:
    """Run autopep8 and return the formatted text plus process success state."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(source)
        tmp_path = f.name
    try:
        completed = runner(
            ["autopep8", "--in-place", "--aggressive", tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        with open(tmp_path, "r") as f:
            return f.read(), completed.returncode == 0
    finally:
        os.unlink(tmp_path)


def format_dedented_source(source: str) -> str | None:
    """Return a dedented formatting candidate when indentation breaks parsing."""
    dedented = dedent_if_indented(source)
    return dedented if dedented != source else None


def repair_missing_block_indentation(source: str) -> str | None:
    """Indent obvious block bodies that were typed flush-left by mistake."""
    repaired = repair_block_indentation(source)
    return repaired if repaired != source else None


def repair_block_indentation(source: str) -> str:
    lines = source.splitlines(keepends=True)
    repaired = lines[:]
    previous_significant: tuple[int, str] | None = None

    for index, line in enumerate(lines):
        if not line.strip():
            continue

        indent = leading_indent(line)
        indent_width = len(indent.expandtabs(4))

        stripped = line.lstrip()
        if previous_significant and previous_significant[1].rstrip().endswith(":"):
            parent_width = previous_significant[0]
            if indent_width <= parent_width:
                child_indent = next_child_indent(lines, index, parent_width)
                repaired[index] = f"{child_indent}{stripped}"
                indent_width = len(child_indent.expandtabs(4))

        previous_significant = (indent_width, repaired[index])

    return "".join(repaired)


def next_child_indent(lines: list[str], start: int, parent_width: int) -> str:
    for line in lines[start + 1:]:
        if not line.strip():
            continue
        indent = leading_indent(line)
        if len(indent.expandtabs(4)) > parent_width:
            return indent
    return " " * (parent_width + 4)


def leading_indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def is_valid_python(source: str) -> bool:
    try:
        ast.parse(source)
    except SyntaxError:
        return False
    return True


def extract_user_code(source: str) -> str | None:
    start_idx = source.find(USER_CODE_START_MARKER)
    end_idx = source.find(USER_CODE_END_MARKER)
    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        return None
    start_idx += len(USER_CODE_START_MARKER)
    return source[start_idx:end_idx]


def replace_user_code(source: str, user_code: str) -> str:
    start_idx = source.find(USER_CODE_START_MARKER) + len(USER_CODE_START_MARKER)
    end_idx = source.find(USER_CODE_END_MARKER)
    separator = "\n" if user_code and not user_code.startswith("\n") else ""
    trailer = "" if user_code.endswith("\n") else "\n"
    return f"{source[:start_idx]}{separator}{user_code}{trailer}{source[end_idx:]}"


def dedent_if_indented(source: str) -> str:
    lines = source.splitlines(keepends=True)
    code_lines = [line for line in lines if line.strip()]
    if not code_lines or not all(line[:1].isspace() for line in code_lines):
        return source
    return textwrap.dedent(source)
