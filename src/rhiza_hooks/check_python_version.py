#!/usr/bin/env python3
"""Check that Python version is consistent across project files."""

from __future__ import annotations

import argparse
import operator
import re
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

from rhiza_hooks._repo import find_repo_root

# Version comparison is a table lookup keyed by the specifier operator. A bare
# specifier ("") is treated as equality, matching `_parse_specifier`, which
# normalizes a missing operator to "==". `~=` (compatible release) means "same
# major, at least this minor", i.e. `>=` plus an equal major component.
_COMPARATORS: dict[str, Callable[[tuple[int, int], tuple[int, int]], bool]] = {
    ">=": operator.ge,
    ">": operator.gt,
    "<=": operator.le,
    "<": operator.lt,
    "==": operator.eq,
    "": operator.eq,
    "!=": operator.ne,
    "~=": lambda v, cv: v >= cv and v[0] == cv[0],
}


def get_python_version_file(repo_root: Path) -> str | None:
    """Read Python version from .python-version file.

    Args:
        repo_root: Root directory of the repository

    Returns:
        Python version string or None if file doesn't exist
    """
    version_file = repo_root / ".python-version"
    if not version_file.exists():
        return None

    content = version_file.read_text(encoding="utf-8").strip()
    # Extract major.minor version
    match = re.match(r"(\d+\.\d+)", content)
    return match.group(1) if match else content


def parse_version(version_str: str) -> tuple[int, int]:
    """Parse a version string into a tuple of (major, minor).

    Args:
        version_str: Version string like "3.11" or "3.12"

    Returns:
        Tuple of (major, minor) integers

    >>> parse_version("3.11")
    (3, 11)
    >>> parse_version("3.12")
    (3, 12)
    """
    normalized = version_str.strip()
    if re.fullmatch(r"\d+\.\d+", normalized) is None:
        msg = f"Invalid version string: {version_str!r}. Expected 'major.minor'."
        raise ValueError(msg)

    parts = normalized.split(".")
    return (int(parts[0]), int(parts[1]))


def _parse_specifier(requires_python: str) -> list[tuple[str, str]]:
    """Parse a (possibly compound) requires-python specifier into clauses.

    The specifier is split on commas and the leading ``operator`` +
    ``major.minor`` is extracted from each clause, so ``">=3.11,<3.14"`` yields
    ``[(">=", "3.11"), ("<", "3.14")]``. A clause with no operator defaults to
    ``"=="``. Clauses that contain no recognizable ``major.minor`` version are
    skipped.

    Note: only the ``major.minor`` of each clause is considered; patch-level and
    wildcard parts (e.g. the ``.*`` in ``!=3.10.*``) are ignored, matching the
    granularity of :func:`version_satisfies_constraint`.

    Args:
        requires_python: The raw ``requires-python`` string from pyproject.toml.

    Returns:
        List of (operator, version) clauses (empty if none are parseable).
    """
    clauses: list[tuple[str, str]] = []
    for part in requires_python.split(","):
        match = re.match(r"\s*([><=!~]+)?\s*(\d+\.\d+)", part)
        if match is None:
            continue
        operator = match.group(1) or "=="  # Default to exact match if no operator
        clauses.append((operator, match.group(2)))
    return clauses


def get_pyproject_requires_python(repo_root: Path) -> list[tuple[str, str]] | None:
    """Read requires-python constraint(s) from pyproject.toml.

    Args:
        repo_root: Root directory of the repository

    Returns:
        List of (operator, version) clauses, or None if not specified or
        unparseable. A compound specifier yields one entry per comma-separated
        clause, e.g. ">=3.11,<3.14" -> [(">=", "3.11"), ("<", "3.14")].
    """
    pyproject_file = repo_root / "pyproject.toml"
    if not pyproject_file.exists():
        return None

    try:
        with pyproject_file.open("rb") as f:
            data = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError):
        # Malformed TOML, or filesystem-level access/open errors (for example:
        # path is a directory, permission denied, or the file disappears between
        # exists() and open()), are treated as "unspecified" rather than
        # crashing the hook. Anything else (e.g. a genuine bug) is left to
        # surface.
        return None

    requires_python = data.get("project", {}).get("requires-python")
    if not requires_python:
        return None

    clauses = _parse_specifier(requires_python)
    # No clause parsed (e.g. "invalid-version"): treat as unspecified.
    return clauses or None


def version_satisfies_constraint(version: str, operator: str, constraint_version: str) -> bool:
    """Check if a version satisfies a constraint.

    Args:
        version: The version to check (e.g., "3.12")
        operator: The comparison operator (e.g., ">=", "==")
        constraint_version: The version in the constraint (e.g., "3.11")

    Returns:
        True if version satisfies the constraint

    >>> version_satisfies_constraint("3.12", ">=", "3.11")
    True
    >>> version_satisfies_constraint("3.10", ">=", "3.11")
    False

    ``~=`` additionally pins the major component:

    >>> version_satisfies_constraint("3.12", "~=", "3.11")
    True
    >>> version_satisfies_constraint("4.0", "~=", "3.11")
    False

    An operator this hook does not model is treated permissively rather than as a
    violation — the hook reports disagreements it is sure about, not everything it
    cannot parse:

    >>> version_satisfies_constraint("3.10", "<>", "3.11")
    True
    """
    comparator = _COMPARATORS.get(operator)
    if comparator is None:
        # Unknown operator: be permissive.
        return True
    return comparator(parse_version(version), parse_version(constraint_version))


def _format_specifier(clauses: list[tuple[str, str]]) -> str:
    """Render specifier clauses back into a compact string (e.g. ``>=3.11,<3.14``)."""
    return ",".join(f"{operator}{version}" for operator, version in clauses)


def check_version_consistency(repo_root: Path) -> list[str]:
    """Check Python version consistency across project files.

    Args:
        repo_root: Root directory of the repository

    Returns:
        List of error messages (empty if consistent)
    """
    python_version = get_python_version_file(repo_root)
    requires_python = get_pyproject_requires_python(repo_root)

    if python_version is None or requires_python is None:
        # One or both files don't specify a version, that's okay
        return []

    # Every clause of a (possibly compound) specifier must be satisfied.
    unsatisfied = any(
        not version_satisfies_constraint(python_version, operator, constraint_version)
        for operator, constraint_version in requires_python
    )
    if not unsatisfied:
        return []

    return [
        f"Python version mismatch: .python-version has {python_version}, "
        f"but pyproject.toml requires-python is {_format_specifier(requires_python)}"
    ]


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the hook."""
    parser = argparse.ArgumentParser(description="Check Python version consistency")
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
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
