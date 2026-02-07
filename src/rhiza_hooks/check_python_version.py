#!/usr/bin/env python3
"""Check that Python version is consistent across project files."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path


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

    content = version_file.read_text().strip()
    # Extract major.minor version
    match = re.match(r"(\d+\.\d+)", content)
    return match.group(1) if match else content


def parse_version(version_str: str) -> tuple[int, int]:
    """Parse a version string into a tuple of (major, minor).

    Args:
        version_str: Version string like "3.11" or "3.12"

    Returns:
        Tuple of (major, minor) integers
    """
    parts = version_str.split(".")
    return (int(parts[0]), int(parts[1]))


def get_pyproject_requires_python(repo_root: Path) -> tuple[str, str] | None:
    """Read requires-python constraint from pyproject.toml.

    Args:
        repo_root: Root directory of the repository

    Returns:
        Tuple of (operator, version) or None if not specified.
        For example: (">=", "3.11") or ("==", "3.12")
    """
    pyproject_file = repo_root / "pyproject.toml"
    if not pyproject_file.exists():
        return None

    try:
        with pyproject_file.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return None

    requires_python = data.get("project", {}).get("requires-python")
    if not requires_python:
        return None

    # Parse the constraint (e.g., ">=3.11", "==3.12", "~=3.11")
    match = re.match(r"([><=!~]+)?\s*(\d+\.\d+)", requires_python.strip())
    if not match:
        return None

    operator = match.group(1) or "=="  # Default to exact match if no operator
    version = match.group(2)
    return (operator, version)


def version_satisfies_constraint(version: str, operator: str, constraint_version: str) -> bool:
    """Check if a version satisfies a constraint.

    Args:
        version: The version to check (e.g., "3.12")
        operator: The comparison operator (e.g., ">=", "==")
        constraint_version: The version in the constraint (e.g., "3.11")

    Returns:
        True if version satisfies the constraint
    """
    v = parse_version(version)
    cv = parse_version(constraint_version)

    if operator == ">=":
        return v >= cv
    elif operator == ">":
        return v > cv
    elif operator == "<=":
        return v <= cv
    elif operator == "<":
        return v < cv
    elif operator == "==" or operator == "":
        return v == cv
    elif operator == "!=":
        return v != cv
    elif operator == "~=":
        # Compatible release: ~=3.11 means >=3.11, <4.0
        return v >= cv and v[0] == cv[0]
    else:
        # Unknown operator, be permissive
        return True


def check_version_consistency(repo_root: Path) -> list[str]:
    """Check Python version consistency across project files.

    Args:
        repo_root: Root directory of the repository

    Returns:
        List of error messages (empty if consistent)
    """
    errors: list[str] = []

    python_version = get_python_version_file(repo_root)
    requires_python = get_pyproject_requires_python(repo_root)

    if python_version is None or requires_python is None:
        # One or both files don't specify a version, that's okay
        return []

    operator, constraint_version = requires_python

    if not version_satisfies_constraint(python_version, operator, constraint_version):
        errors.append(
            f"Python version mismatch: .python-version has {python_version}, "
            f"but pyproject.toml requires-python is {operator}{constraint_version}"
        )

    return errors


def find_repo_root() -> Path:
    """Find the repository root directory.

    Returns:
        Path to the repository root
    """
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return Path.cwd()


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the hook."""
    parser = argparse.ArgumentParser(description="Check Python version consistency")
    parser.add_argument(
        "filenames",
        nargs="*",
        help="Filenames (ignored, checks repo root)",
    )
    args = parser.parse_args(argv)  # noqa: F841

    repo_root = find_repo_root()
    errors = check_version_consistency(repo_root)

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
