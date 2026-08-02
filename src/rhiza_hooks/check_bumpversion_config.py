#!/usr/bin/env python3
"""Check that bump-my-version can actually discover this project's version config.

bump-my-version reads its configuration from a fixed set of filenames. When it
finds none it does **not** fail — it falls back to ``git describe`` and reports
the last reachable tag as the current version. Release tooling then computes
bump candidates from that number instead of the project's own, which can offer a
version that has already been published.

That failure is silent by construction, so this hook makes it loud: if the
project declares a version, a bumpversion section must live somewhere the tool
will look.

The specific trap this was written for: rhiza syncs a fully-formed
``[tool.bumpversion]`` block into ``.rhiza/.cfg.toml``, which is *not* one of the
searched filenames, so it never takes effect.
"""

from __future__ import annotations

import argparse
import configparser
import sys
import tomllib
from pathlib import Path
from typing import Any

from rhiza_hooks._repo import find_repo_root

# The only filenames bump-my-version auto-discovers, in its own search order. It
# stops at the first file carrying a bumpversion section. Any other path — however
# well-formed — is read only when passed explicitly via --config-file.
_TOML_CANDIDATES = (".bumpversion.toml", "pyproject.toml")
_INI_CANDIDATES = (".bumpversion.cfg", "setup.cfg")

# Looks authoritative, is never auto-discovered. Named explicitly so the error can
# point at the actual cause rather than just reporting an absence.
_UNDISCOVERED = Path(".rhiza") / ".cfg.toml"


def _load_toml(path: Path) -> dict[str, object] | None:
    """Parse a TOML file, treating unreadable or malformed input as absent.

    Args:
        path: File to parse.

    Returns:
        The parsed mapping, or None if the file is missing, malformed, or cannot
        be opened. Other hooks in this package take the same lenient stance: a
        broken pyproject.toml is somebody else's error to report.
    """
    if not path.exists():
        return None
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (tomllib.TOMLDecodeError, OSError):
        return None


def _load_ini(path: Path) -> configparser.ConfigParser | None:
    """Parse an INI file, treating unreadable or malformed input as absent.

    Args:
        path: File to parse.

    Returns:
        The parser, or None if the file is missing, malformed, or unreadable.
    """
    if not path.exists():
        return None
    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return None
    return parser


def read_project_version(repo_root: Path) -> str | None:
    """Read ``[project].version`` from pyproject.toml.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        The declared version, or None when there is no pyproject.toml, no
        ``[project]`` table, or no static ``version`` key. A project using
        ``dynamic = ["version"]`` therefore reads as None and is not checked —
        its version does not live in a file bump-my-version would rewrite.
    """
    data = _load_toml(repo_root / "pyproject.toml")
    if data is None:
        return None
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    version = project.get("version")
    return version if isinstance(version, str) else None


def _toml_bumpversion_section(path: Path) -> dict[Any, Any] | None:
    """Return the bumpversion section of a TOML candidate, or None if it has none.

    ``.bumpversion.toml`` holds the section at the top level; ``pyproject.toml``
    nests it under ``[tool]``. Accept whichever this file uses. A section that is
    present but not a table reads as absent, like a malformed file.
    """
    data = _load_toml(path)
    if data is None:
        return None
    tool = data.get("tool")
    section = tool.get("bumpversion") if isinstance(tool, dict) else None
    if section is None:
        section = data.get("bumpversion")
    return section if isinstance(section, dict) else None


def _ini_bumpversion_section(path: Path) -> configparser.SectionProxy | None:
    """Return the ``[bumpversion]`` section of an INI candidate, or None if it has none."""
    parser = _load_ini(path)
    if parser is None or not parser.has_section("bumpversion"):
        return None
    return parser["bumpversion"]


def find_discoverable_config(repo_root: Path) -> tuple[str, str | None] | None:
    """Locate the first bumpversion section bump-my-version would actually read.

    TOML candidates are searched before INI candidates, and the first file
    carrying a section wins — bump-my-version's own search order.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        A ``(filename, current_version)`` pair for the winning config, where
        ``current_version`` is None when the section omits that key. Returns None
        when no searched file carries a bumpversion section.
    """
    for name in _TOML_CANDIDATES:
        toml_section = _toml_bumpversion_section(repo_root / name)
        if toml_section is not None:
            declared = toml_section.get("current_version")
            return name, declared if isinstance(declared, str) else None

    for name in _INI_CANDIDATES:
        ini_section = _ini_bumpversion_section(repo_root / name)
        if ini_section is not None:
            return name, ini_section.get("current_version")

    return None


def has_undiscovered_config(repo_root: Path) -> bool:
    """Report whether a bumpversion section sits in a file that is never searched.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        True if ``.rhiza/.cfg.toml`` carries a ``[tool.bumpversion]`` section.
    """
    data = _load_toml(repo_root / _UNDISCOVERED)
    if data is None:
        return False
    tool = data.get("tool")
    return isinstance(tool, dict) and isinstance(tool.get("bumpversion"), dict)


def check_bumpversion_config(repo_root: Path) -> list[str]:
    """Check that a discoverable bumpversion config exists and agrees with pyproject.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        List of error messages (empty when the configuration is sound).
    """
    project_version = read_project_version(repo_root)
    if project_version is None:
        # No statically declared version: nothing for bump-my-version to own.
        return []

    found = find_discoverable_config(repo_root)
    if found is None:
        searched = ", ".join((*_TOML_CANDIDATES, *_INI_CANDIDATES))
        message = (
            f"pyproject.toml declares version {project_version!r}, but no bumpversion "
            f"config was found in any file bump-my-version searches ({searched}). "
            "It will silently fall back to `git describe` and report the last "
            "reachable tag as the current version."
        )
        if has_undiscovered_config(repo_root):
            message += (
                f" A [tool.bumpversion] section exists in {_UNDISCOVERED.as_posix()}, "
                "but that path is never auto-discovered — move it, or add a "
                "[tool.bumpversion] table to pyproject.toml."
            )
        return [message]

    filename, declared = found
    if declared is not None and declared != project_version:
        return [
            f"Version mismatch: {filename} declares current_version = {declared!r}, "
            f"but pyproject.toml [project].version is {project_version!r}. "
            "Bumping from the stale value will not match the version in the file."
        ]

    return []


def main(argv: list[str] | None = None) -> int:
    """Run the hook and return a process exit code."""
    parser = argparse.ArgumentParser(description="Check bump-my-version configuration is discoverable")
    parser.add_argument(
        "filenames",
        nargs="*",
        help="Filenames (ignored, checks repo root)",
    )
    parser.parse_args(argv)  # validate/consume pre-commit's filename args; result unused

    errors = check_bumpversion_config(find_repo_root())

    for error in errors:
        print(f"ERROR: {error}")

    return 1 if errors else 0


if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
