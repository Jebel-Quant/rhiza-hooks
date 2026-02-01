#!/usr/bin/env python3
"""Check that Makefile contains expected targets for rhiza projects."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Common targets expected in rhiza-based projects
RECOMMENDED_TARGETS = {
    "install",
    "test",
    "fmt",
    "help",
}

# Pattern to match Makefile target definitions
TARGET_PATTERN = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:", re.MULTILINE)


def extract_targets(content: str) -> set[str]:
    """Extract target names from Makefile content.

    Args:
        content: Contents of a Makefile

    Returns:
        Set of target names found
    """
    matches = TARGET_PATTERN.findall(content)
    return set(matches)


def check_makefile(filepath: Path) -> list[str]:
    """Check a Makefile for recommended targets.

    Args:
        filepath: Path to the Makefile

    Returns:
        List of warning messages (empty if all recommended targets exist)
    """
    warnings: list[str] = []

    try:
        content = filepath.read_text()
    except FileNotFoundError:
        return [f"File not found: {filepath}"]

    targets = extract_targets(content)

    # Only check the main Makefile for recommended targets
    if filepath.name == "Makefile":
        missing = RECOMMENDED_TARGETS - targets
        if missing:
            warnings.append(
                f"Missing recommended targets: {', '.join(sorted(missing))}"
            )

    return warnings


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the hook."""
    parser = argparse.ArgumentParser(
        description="Check Makefile for recommended targets"
    )
    parser.add_argument(
        "filenames",
        nargs="*",
        help="Filenames to check",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with error if recommended targets are missing",
    )
    args = parser.parse_args(argv)

    retval = 0
    for filename in args.filenames:
        filepath = Path(filename)
        warnings = check_makefile(filepath)
        if warnings:
            print(f"{filename}:")
            for warning in warnings:
                print(f"  - {warning}")
            if args.strict:
                retval = 1

    return retval


if __name__ == "__main__":
    sys.exit(main())
