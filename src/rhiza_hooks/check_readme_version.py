#!/usr/bin/env python3
"""Check that the README quick-start rev: matches pyproject.toml version."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path


def get_pyproject_version(repo_root: Path) -> str | None:
    """Read version from pyproject.toml.

    Args:
        repo_root: Root directory of the repository

    Returns:
        Version string (e.g. "0.5.1") or None if not found.
    """
    pyproject_file = repo_root / "pyproject.toml"
    if not pyproject_file.exists():
        return None

    try:
        with pyproject_file.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return None

    return data.get("project", {}).get("version")


def get_readme_rev(repo_root: Path) -> str | None:
    """Read the rev: value for the rhiza-hooks entry from README.md.

    Looks for a YAML code block containing a ``repo:`` line that references
    ``Jebel-Quant/rhiza-hooks`` and returns the value on the adjacent
    ``rev:`` line, stripping any trailing inline comment.

    Args:
        repo_root: Root directory of the repository

    Returns:
        Rev string (e.g. "v0.5.1") or None if not found.
    """
    readme_file = repo_root / "README.md"
    if not readme_file.exists():
        return None

    content = readme_file.read_text()

    # Match the rev: line that immediately follows a repo: line for rhiza-hooks.
    # The pattern handles optional whitespace and inline comments.
    pattern = re.compile(
        r"repo:\s+https://github\.com/[Jj]ebel-[Qq]uant/rhiza-hooks\s*\n"
        r"\s*rev:\s*([^\s#]+)",
        re.IGNORECASE,
    )
    match = pattern.search(content)
    if not match:
        return None

    return match.group(1)


def check_readme_version(repo_root: Path) -> list[str]:
    """Check that README quick-start rev: matches pyproject.toml version.

    Args:
        repo_root: Root directory of the repository

    Returns:
        List of error messages (empty if consistent).
    """
    errors: list[str] = []

    pyproject_version = get_pyproject_version(repo_root)
    if pyproject_version is None:
        return []

    readme_rev = get_readme_rev(repo_root)
    if readme_rev is None:
        errors.append(
            "README.md: could not find a rev: entry for "
            "https://github.com/Jebel-Quant/rhiza-hooks in a quick-start block"
        )
        return errors

    # Normalise: strip a leading "v" before comparing
    normalised_rev = readme_rev.lstrip("v")
    if normalised_rev != pyproject_version:
        errors.append(
            f"README.md quick-start rev: '{readme_rev}' does not match "
            f"pyproject.toml version '{pyproject_version}'. "
            f"Update README.md to use rev: v{pyproject_version}"
        )

    return errors


def find_repo_root() -> Path:
    """Find the repository root directory.

    Returns:
        Path to the repository root.
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
        description="Check README quick-start rev: matches pyproject.toml version"
    )
    parser.add_argument(
        "filenames",
        nargs="*",
        help="Filenames (ignored, checks repo root)",
    )
    args = parser.parse_args(argv)  # noqa: F841

    repo_root = find_repo_root()
    errors = check_readme_version(repo_root)

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
