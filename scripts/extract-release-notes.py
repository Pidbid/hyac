#!/usr/bin/env python3
"""Extract one stable release section from both Hyac changelogs."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


SEMVER_NUMBER = r"(?:0|[1-9]\d*)"
STABLE_TAG = re.compile(rf"^v{SEMVER_NUMBER}\.{SEMVER_NUMBER}\.{SEMVER_NUMBER}$")


def extract_section(path: Path, tag: str) -> str:
    source = path.read_text(encoding="utf-8")
    heading = re.compile(rf"^## \[{re.escape(tag)}\](?:\s+-\s+.*)?\s*$", re.MULTILINE)
    matches = list(heading.finditer(source))
    if len(matches) != 1:
        raise ValueError(
            f"{path}: expected exactly one section for {tag}, found {len(matches)}"
        )

    start = matches[0].end()
    next_heading = re.search(r"^## \[", source[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(source)
    body = source[start:end].strip()
    if not body:
        raise ValueError(f"{path}: release section for {tag} is empty")
    return body


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--zh", type=Path, required=True)
    parser.add_argument("--en", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not STABLE_TAG.fullmatch(args.tag):
        print(
            f"release tag must match vX.Y.Z exactly: {args.tag}",
            file=sys.stderr,
        )
        return 2

    inputs = {args.zh.resolve(), args.en.resolve()}
    if args.output.resolve() in inputs:
        print("output must not overwrite a changelog", file=sys.stderr)
        return 2

    try:
        chinese = extract_section(args.zh, args.tag)
        english = extract_section(args.en, args.tag)
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        f"## 中文\n\n{chinese}\n\n## English\n\n{english}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
