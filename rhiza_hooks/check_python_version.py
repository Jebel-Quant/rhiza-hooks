#!/usr/bin/env python3
"""Check that Python version is consistent across project files."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]


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


def get_pyproject_python_version(repo_root: Path) -> str | None:
    """Read minimum Python version from pyproject.toml.

    Args:
        repo_root: Root directory of the repository

    Returns:
        Python version string or None if not specified
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

    # Extract version from requires-python (e.g., ">=3.11" -> "3.11")
    match = re.search(r"(\d+\.\d+)", requires_python)
    return match.group(1) if match else None


def check_version_consistency(repo_root: Path) -> list[str]:
    """Check Python version consistency across project files.

    Args:
        repo_root: Root directory of the repository

    Returns:
        List of error messages (empty if consistent)
    """
    errors: list[str] = []

    python_version = get_python_version_file(repo_root)
    pyproject_version = get_pyproject_python_version(repo_root)

    if python_version is None and pyproject_version is None:
        # Neither file specifies a version, that's okay
        return []

    if python_version is not None and pyproject_version is not None:
        if python_version != pyproject_version:
            errors.append(
                f"Python version mismatch: .python-version has {python_version}, "
                f"pyproject.toml requires-python has {pyproject_version}"
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
    parser = argparse.ArgumentParser(
        description="Check Python version consistency"
    )
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
