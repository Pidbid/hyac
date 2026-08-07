#!/usr/bin/env python3
"""Verify that an OCI image index contains exactly the supported Linux platforms."""

from __future__ import annotations

import json
import sys
from pathlib import Path


EXPECTED_PLATFORMS = {"linux/amd64", "linux/arm64"}


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} MANIFEST.json", file=sys.stderr)
        return 2

    try:
        document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        manifests = document["manifests"]
        platforms = {
            f"{platform['os']}/{platform['architecture']}"
            for manifest in manifests
            if (platform := manifest.get("platform", {})).get("os") == "linux"
        }
    except (OSError, AttributeError, KeyError, TypeError, ValueError) as exc:
        print(f"invalid OCI manifest: {exc}", file=sys.stderr)
        return 2

    if platforms != EXPECTED_PLATFORMS:
        print(
            f"unexpected Linux platforms: {sorted(platforms)}; "
            f"expected {sorted(EXPECTED_PLATFORMS)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
