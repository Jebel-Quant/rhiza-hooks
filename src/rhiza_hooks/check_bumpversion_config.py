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

The same hook also checks the config's *targets* — the ``[[tool.bumpversion.files]]``
entries a release rewrites — because they fail equally late and just as quietly:

* An entry pointing at a template-owned file loses its pattern at the next sync,
  which restores that file. The release after that aborts, long after the commit
  that caused it.
* A pattern that no longer occurs in its file (or occurs twice) breaks the bump
  itself. bump-my-version reports that loudly, but only while cutting a version.

Locating and parsing the configuration lives in
:mod:`rhiza_hooks._bumpversion_config`, which owns the two on-disk formats and
normalises them into a :class:`~rhiza_hooks._bumpversion_config.BumpversionConfig`.
This module is the CLI/orchestration layer: it judges that result and reports.
That module is private, so the package's public surface is unchanged by the
split; within it a leading underscore marks a helper with no caller outside its
own file, which is why this module imports only unprefixed names from it.

Exit codes:
  0 - Validation passed
  1 - Validation failed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rhiza_hooks._bumpversion_config import (
    SEARCHED_FILENAMES,
    BumpversionTarget,
    find_config,
    load_toml,
)
from rhiza_hooks._managed import managed_paths
from rhiza_hooks._repo import find_repo_root

# Looks authoritative, is never auto-discovered. Named explicitly so the error can
# point at the actual cause rather than just reporting an absence.
_UNDISCOVERED = Path(".rhiza") / ".cfg.toml"


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
    data = load_toml(repo_root / "pyproject.toml")
    if data is None:
        return None
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    version = project.get("version")
    return version if isinstance(version, str) else None


def find_discoverable_config(repo_root: Path) -> tuple[str, str | None] | None:
    """Locate the first bumpversion section bump-my-version would actually read.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        A ``(filename, current_version)`` pair for the winning config, where
        ``current_version`` is None when the section omits that key. Returns None
        when no searched file carries a bumpversion section.
    """
    config = find_config(repo_root)
    if config is None:
        return None
    return config.filename, config.current_version


def _resolved_needle(target: BumpversionTarget, project_version: str) -> str | None:
    """Resolve a target's search pattern to the literal text a bump would look for.

    Returns None when the pattern cannot be resolved here and the check must be
    skipped: a ``regex`` entry (not countable literally — bump-my-version owns that
    check), or one whose pattern still holds a placeholder such as ``{new_version}``
    after ``{current_version}`` is substituted.
    """
    if target.regex:
        return None
    needle = (target.search or "{current_version}").replace("{current_version}", project_version)
    return None if "{" in needle else needle


def _occurrence_errors(path: Path, filename: str, needle: str) -> list[str]:
    """Report a pattern that appears in ``path`` zero times, or more than once.

    An unreadable or binary file yields no error: that is somebody else's problem to
    report, the same lenient stance :func:`~rhiza_hooks._bumpversion_config.load_toml`
    takes.
    """
    try:
        occurrences = path.read_text(encoding="utf-8").count(needle)
    except (OSError, UnicodeDecodeError):
        return []

    if occurrences == 0:
        return [f"Bumpversion pattern {needle!r} does not occur in {filename}, so the next release will abort."]
    if occurrences > 1:
        return [
            f"Bumpversion pattern {needle!r} occurs {occurrences} times in {filename}; "
            "it is ambiguous which line a bump rewrites."
        ]
    return []


def _check_target(repo_root: Path, project_version: str, target: BumpversionTarget, managed: set[str]) -> list[str]:
    """Check one bumpversion file entry: who owns it, and whether its pattern is there.

    Args:
        repo_root: Root directory of the repository.
        project_version: The version declared in pyproject.toml.
        target: A normalised entry from
            :func:`~rhiza_hooks._bumpversion_config.find_config`.
        managed: Repo-relative paths the template owns.

    Returns:
        List of error messages for this entry (empty when it is sound, or when
        there is nothing that can be checked).
    """
    if target.filename in managed:
        return [
            f"Bumpversion targets {target.filename}, which is owned by the rhiza template. "
            "The next sync restores it and wipes the pattern, so the release after "
            "that aborts. Point the entry at a file this project owns."
        ]

    path = repo_root / target.filename
    if not path.exists():
        # An entry may legitimately precede its file on a work-in-progress branch.
        return []

    needle = _resolved_needle(target, project_version)
    if needle is None:
        return []
    return _occurrence_errors(path, target.filename, needle)


def has_undiscovered_config(repo_root: Path) -> bool:
    """Report whether a bumpversion section sits in a file that is never searched.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        True if ``.rhiza/.cfg.toml`` carries a ``[tool.bumpversion]`` section.
    """
    data = load_toml(repo_root / _UNDISCOVERED)
    if data is None:
        return False
    tool = data.get("tool")
    return isinstance(tool, dict) and isinstance(tool.get("bumpversion"), dict)


def _no_config_message(repo_root: Path, project_version: str) -> str:
    """Explain that no discoverable config exists, and why that is silent rather than loud.

    Names ``.rhiza/.cfg.toml`` when the section is sitting there, so the error points
    at the actual cause instead of just reporting an absence.
    """
    searched = ", ".join(SEARCHED_FILENAMES)
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
    return message


def _version_mismatch(filename: str, declared: str | None, project_version: str) -> list[str]:
    """Report a config whose ``current_version`` disagrees with pyproject's.

    A config that declares no ``current_version`` at all is not a mismatch: there is
    no stale value to bump from.

    >>> _version_mismatch(".bumpversion.toml", "1.2.0", "1.2.0")
    []
    >>> _version_mismatch(".bumpversion.toml", None, "1.2.0")
    []
    >>> _version_mismatch(".bumpversion.toml", "1.1.0", "1.2.0")[0].startswith("Version mismatch:")
    True
    """
    if declared is None or declared == project_version:
        return []
    return [
        f"Version mismatch: {filename} declares current_version = {declared!r}, "
        f"but pyproject.toml [project].version is {project_version!r}. "
        "Bumping from the stale value will not match the version in the file."
    ]


def check_bumpversion_config(repo_root: Path) -> list[str]:
    """Check the bumpversion config: discoverable, agreeing with pyproject, and rewritable.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        List of error messages (empty when the configuration is sound).
    """
    project_version = read_project_version(repo_root)
    if project_version is None:
        # No statically declared version: nothing for bump-my-version to own.
        return []

    config = find_config(repo_root)
    if config is None:
        return [_no_config_message(repo_root, project_version)]

    errors = _version_mismatch(config.filename, config.current_version, project_version)

    managed = managed_paths(repo_root)
    for target in config.targets:
        errors.extend(_check_target(repo_root, project_version, target, managed))

    return errors


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
        print(f"ERROR: {error}", file=sys.stderr)

    return 1 if errors else 0


if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
