#!/usr/bin/env python3
"""Check that the Go version is consistent across project files.

A Go project states its version in up to three places:

* ``go.mod`` — the ``go`` directive, the minimum language version the module
  requires;
* ``go.mod`` — the optional ``toolchain`` directive, the toolchain the ``go``
  command switches to for this module;
* ``.go-version`` — the toolchain pin honoured by goenv and ``actions/setup-go``.

The hook enforces the three relationships between them: the ``toolchain``
directive may not be below the ``go`` directive (the go command itself rejects
that), ``.go-version`` may not be below the ``go`` directive (the pinned
toolchain could not build the module), and ``.go-version`` must name the same
version as the ``toolchain`` directive when both are present.

Values that are not dotted-numeric (``toolchain default``, ``toolchain local``)
carry no version number, so they are accepted without comparison. A leading
``go`` prefix (``go1.22.5``) is stripped before parsing.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from rhiza_hooks._repo import find_repo_root
from rhiza_hooks._version import parse_version, same_version, version_at_least

GO_MOD_FILE = "go.mod"
GO_VERSION_FILE = ".go-version"

# Top-level ``go``/``toolchain`` directives. Anchored and requiring whitespace
# after the keyword, so a module path such as ``go.uber.org/zap v1.27.0`` inside
# a require block never matches.
_DIRECTIVE = re.compile(r"^(go|toolchain)\s+(\S+)")


def _normalize(value: str) -> str:
    """Strip surrounding whitespace and the ``go`` version prefix (``go1.22`` -> ``1.22``)."""
    return value.strip().removeprefix("go")


def parse_go_mod(text: str) -> dict[str, str]:
    """Extract the ``go`` and ``toolchain`` directives from ``go.mod`` text.

    Parenthesised blocks (``require (`` … ``)``) are skipped so their contents
    can never be mistaken for a top-level directive. A directive repeated at top
    level — which the go command rejects anyway — keeps its last occurrence.

    Args:
        text: Full contents of a ``go.mod`` file.

    Returns:
        Mapping of directive name to its normalized value, containing only the
        directives actually present.
    """
    directives: dict[str, str] = {}
    in_block = False

    for raw_line in text.splitlines():
        line = raw_line.split("//", 1)[0].strip()

        if in_block:
            in_block = line != ")"
            continue
        if line.endswith("("):
            in_block = True
            continue

        match = _DIRECTIVE.match(line)
        if match is not None:
            directives[match.group(1)] = _normalize(match.group(2))

    return directives


def get_go_mod_directives(repo_root: Path) -> dict[str, str]:
    """Read the ``go`` and ``toolchain`` directives from the repository's ``go.mod``.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        Mapping of directive name to value; empty when ``go.mod`` is missing or
        unreadable.
    """
    path = repo_root / GO_MOD_FILE
    if not path.exists():
        return {}
    try:
        text = path.read_text()
    except OSError:
        # A directory at the path, permission denied, or a race between exists()
        # and read: treat as "unspecified" rather than crashing the hook.
        return {}
    return parse_go_mod(text)


def get_go_version_file(repo_root: Path) -> str | None:
    """Read the toolchain pin from ``.go-version``.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        The normalized version string, or None if the file is missing,
        unreadable, or empty.
    """
    path = repo_root / GO_VERSION_FILE
    if not path.exists():
        return None
    try:
        text = path.read_text()
    except OSError:
        return None
    return _normalize(text) or None


def _is_below(source_value: str | None, minimum_value: str | None) -> bool:
    """Whether *source_value* names a version strictly below *minimum_value*.

    False whenever there is nothing to compare: either side absent (the project
    does not declare it) or not dotted-numeric (``toolchain default``).

    Args:
        source_value: Raw version text being checked, or None if undeclared.
        minimum_value: Raw version text of the lower bound, or None if undeclared.

    Returns:
        True only when both sides carry a version number and *source_value* is
        the lower of the two.
    """
    if source_value is None or minimum_value is None:
        return False
    source = parse_version(source_value)
    minimum = parse_version(minimum_value)
    if source is None or minimum is None:
        return False
    return not version_at_least(source, minimum)


def _check_at_least(
    source_label: str,
    source_value: str | None,
    minimum_label: str,
    minimum_value: str | None,
) -> list[str]:
    """Report an error when *source_value* names a version below *minimum_value*.

    Accepts None on either side so callers need no presence guard of their own —
    an undeclared version simply yields no error.
    """
    if not _is_below(source_value, minimum_value):
        return []
    return [f"Go version mismatch: {source_label} is {source_value}, which is below {minimum_label} {minimum_value}"]


def _check_pin_matches_toolchain(pinned: str | None, toolchain: str | None) -> list[str]:
    """Report a disagreement between ``.go-version`` and the ``toolchain`` directive."""
    if pinned is None or toolchain is None or same_version(pinned, toolchain):
        return []
    return [f"Go version mismatch: .go-version pins {pinned}, but the go.mod toolchain directive pins {toolchain}"]


def check_version_consistency(repo_root: Path) -> list[str]:
    """Check Go version consistency across project files.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        List of error messages (empty if consistent, or if the repository
        declares no Go versions at all).
    """
    directives = get_go_mod_directives(repo_root)
    go_directive = directives.get("go")
    toolchain = directives.get("toolchain")
    pinned = get_go_version_file(repo_root)

    # Each helper tolerates an undeclared (None) side, so the three relationships
    # read as a flat list rather than a nest of presence guards.
    return [
        *_check_at_least("go.mod toolchain", toolchain, "the go.mod go directive", go_directive),
        *_check_at_least(".go-version", pinned, "the go.mod go directive", go_directive),
        *_check_pin_matches_toolchain(pinned, toolchain),
    ]


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the hook."""
    parser = argparse.ArgumentParser(description="Check Go version consistency")
    parser.add_argument(
        "filenames",
        nargs="*",
        help="Filenames (ignored, checks repo root)",
    )
    parser.parse_args(argv)  # validate/consume pre-commit's filename args; result unused

    repo_root = find_repo_root()
    errors = check_version_consistency(repo_root)

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    return 0


if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
