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

# Pattern to match Makefile target definitions.
#
# A rule is `name:` or, for double-colon rules, `name::`. Variable assignments
# (`name := ...`, `name ::= ...`) must NOT be mistaken for targets, so the
# colon-run is matched possessively (`:++`, Python 3.11+) and a following `=`
# is rejected with a negative lookahead — `:++` cannot backtrack to a shorter
# run to dodge the lookahead, so `name :=` and `name ::=` are excluded while
# `name:` and `name::` still match. Leading `[a-zA-Z_]` already excludes
# dot-special targets (`.PHONY`) and pattern rules (`%.o`).
TARGET_PATTERN = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*)[ \t]*:++(?!=)", re.MULTILINE)


def extract_targets(content: str) -> set[str]:
    """Extract target names from Makefile content.

    Args:
        content: Contents of a Makefile

    Returns:
        Set of target names found
    """
    matches = TARGET_PATTERN.findall(content)
    return set(matches)


def check_makefile(filepath: Path, recommended: set[str] = RECOMMENDED_TARGETS) -> list[str]:
    """Check a Makefile for recommended targets.

    Args:
        filepath: Path to the Makefile
        recommended: Target names that must be present (defaults to RECOMMENDED_TARGETS)

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
        missing = recommended - targets
        if missing:
            warnings.append(f"Missing recommended targets: {', '.join(sorted(missing))}")

    return warnings


def resolve_recommended_targets(targets: list[str] | None, extra_targets: list[str] | None) -> set[str]:
    """Build the effective set of required targets from the CLI options.

    Args:
        targets: Values of ``--target``. When non-empty they *replace* the defaults.
        extra_targets: Values of ``--extend-target``, always *added* to the active set.

    Returns:
        The set of target names a Makefile is expected to define.
    """
    base = set(targets) if targets else set(RECOMMENDED_TARGETS)
    return base | set(extra_targets or [])


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the hook."""
    parser = argparse.ArgumentParser(description="Check Makefile for recommended targets")
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
    parser.add_argument(
        "--target",
        action="append",
        metavar="NAME",
        help="Required target name; repeatable. When given, replaces the default set.",
    )
    parser.add_argument(
        "--extend-target",
        action="append",
        metavar="NAME",
        help="Extra required target name; repeatable. Added on top of the active set.",
    )
    args = parser.parse_args(argv)

    recommended = resolve_recommended_targets(args.target, args.extend_target)

    retval = 0
    for filename in args.filenames:
        filepath = Path(filename)
        warnings = check_makefile(filepath, recommended)
        if warnings:
            print(f"{filename}:")
            for warning in warnings:
                print(f"  - {warning}")
            if args.strict:
                retval = 1

    return retval


if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
