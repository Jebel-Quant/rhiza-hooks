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
"""

from __future__ import annotations

import argparse
import configparser
import sys
import tomllib
from pathlib import Path
from typing import Any

from rhiza_hooks._managed import managed_paths
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
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError):
        # tomllib decodes the stream itself, so invalid UTF-8 surfaces as
        # UnicodeDecodeError rather than a TOML error — without this the hook
        # crashed with a traceback on a binary pyproject.toml.
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


def _toml_target(entry: Any) -> dict[str, Any] | None:
    """Normalise one ``[[tool.bumpversion.files]]`` entry, or None if it is unusable.

    The normalised shape is ``{"filename", "search", "regex"}``, where ``search`` is
    None when the entry omits it (or gives a non-string) — bump-my-version then
    defaults to ``{current_version}``. An entry that is not a table, or carries no
    string ``filename``, has nothing checkable about it.
    """
    if not isinstance(entry, dict):
        return None
    filename = entry.get("filename")
    if not isinstance(filename, str):
        return None
    search = entry.get("search")
    return {
        "filename": filename,
        "search": search if isinstance(search, str) else None,
        "regex": bool(entry.get("regex")),
    }


def _toml_targets(section: dict[Any, Any]) -> list[dict[str, Any]]:
    """Normalise a TOML section's ``[[tool.bumpversion.files]]`` entries, dropping unusable ones."""
    entries = section.get("files")
    if not isinstance(entries, list):
        return []
    return [target for entry in entries if (target := _toml_target(entry)) is not None]


def _ini_targets(parser: configparser.ConfigParser) -> list[dict[str, Any]]:
    """Normalise an INI parser's ``[bumpversion:file:<path>]`` sections.

    The INI format encodes the target path in the section name rather than in a
    ``filename`` key, so the two formats need separate readers even though they
    produce the same shape.
    """
    prefix = "bumpversion:file:"
    return [
        {
            "filename": name[len(prefix) :],
            "search": parser.get(name, "search", fallback=None),
            "regex": parser.getboolean(name, "regex", fallback=False),
        }
        for name in parser.sections()
        if name.startswith(prefix)
    ]


def _find_toml_config(repo_root: Path) -> tuple[str, str | None, list[dict[str, Any]]] | None:
    """Locate the first TOML candidate carrying a bumpversion section."""
    for name in _TOML_CANDIDATES:
        section = _toml_bumpversion_section(repo_root / name)
        if section is not None:
            declared = section.get("current_version")
            return name, declared if isinstance(declared, str) else None, _toml_targets(section)
    return None


def _find_ini_config(repo_root: Path) -> tuple[str, str | None, list[dict[str, Any]]] | None:
    """Locate the first INI candidate carrying a ``[bumpversion]`` section.

    Unlike the TOML reader this keeps the whole parser, because an INI config's
    targets live in sibling ``[bumpversion:file:<path>]`` sections rather than
    inside the main one.
    """
    for name in _INI_CANDIDATES:
        parser = _load_ini(repo_root / name)
        if parser is not None and parser.has_section("bumpversion"):
            declared = parser.get("bumpversion", "current_version", fallback=None)
            return name, declared, _ini_targets(parser)
    return None


def _find_config(repo_root: Path) -> tuple[str, str | None, list[dict[str, Any]]] | None:
    """Locate the bumpversion config bump-my-version would read, with its file entries.

    TOML candidates are searched before INI candidates, and the first file carrying
    a section wins — bump-my-version's own search order.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        ``(filename, current_version, targets)`` for the winning config, where
        ``current_version`` is None when the section omits that key and ``targets``
        holds its normalised file entries. None when no searched file carries a
        bumpversion section.
    """
    return _find_toml_config(repo_root) or _find_ini_config(repo_root)


def find_discoverable_config(repo_root: Path) -> tuple[str, str | None] | None:
    """Locate the first bumpversion section bump-my-version would actually read.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        A ``(filename, current_version)`` pair for the winning config, where
        ``current_version`` is None when the section omits that key. Returns None
        when no searched file carries a bumpversion section.
    """
    found = _find_config(repo_root)
    if found is None:
        return None
    filename, declared, _targets = found
    return filename, declared


def _resolved_needle(target: dict[str, Any], project_version: str) -> str | None:
    """Resolve a target's search pattern to the literal text a bump would look for.

    Returns None when the pattern cannot be resolved here and the check must be
    skipped: a ``regex`` entry (not countable literally — bump-my-version owns that
    check), or one whose pattern still holds a placeholder such as ``{new_version}``
    after ``{current_version}`` is substituted.
    """
    if target["regex"]:
        return None
    needle = (target["search"] or "{current_version}").replace("{current_version}", project_version)
    return None if "{" in needle else needle


def _occurrence_errors(path: Path, filename: str, needle: str) -> list[str]:
    """Report a pattern that appears in ``path`` zero times, or more than once.

    An unreadable or binary file yields no error: that is somebody else's problem to
    report, the same lenient stance :func:`_load_toml` takes.
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


def _check_target(repo_root: Path, project_version: str, target: dict[str, Any], managed: set[str]) -> list[str]:
    """Check one bumpversion file entry: who owns it, and whether its pattern is there.

    Args:
        repo_root: Root directory of the repository.
        project_version: The version declared in pyproject.toml.
        target: A normalised entry from :func:`_toml_targets` / :func:`_ini_targets`.
        managed: Repo-relative paths the template owns.

    Returns:
        List of error messages for this entry (empty when it is sound, or when
        there is nothing that can be checked).
    """
    filename = target["filename"]
    if filename in managed:
        return [
            f"Bumpversion targets {filename}, which is owned by the rhiza template. "
            "The next sync restores it and wipes the pattern, so the release after "
            "that aborts. Point the entry at a file this project owns."
        ]

    path = repo_root / filename
    if not path.exists():
        # An entry may legitimately precede its file on a work-in-progress branch.
        return []

    needle = _resolved_needle(target, project_version)
    if needle is None:
        return []
    return _occurrence_errors(path, filename, needle)


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


def _no_config_message(repo_root: Path, project_version: str) -> str:
    """Explain that no discoverable config exists, and why that is silent rather than loud.

    Names ``.rhiza/.cfg.toml`` when the section is sitting there, so the error points
    at the actual cause instead of just reporting an absence.
    """
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
    return message


def _version_mismatch(filename: str, declared: str | None, project_version: str) -> list[str]:
    """Report a config whose ``current_version`` disagrees with pyproject's.

    A config that declares no ``current_version`` at all is not a mismatch: there is
    no stale value to bump from.
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

    found = _find_config(repo_root)
    if found is None:
        return [_no_config_message(repo_root, project_version)]

    filename, declared, targets = found
    errors = _version_mismatch(filename, declared, project_version)

    managed = managed_paths(repo_root)
    for target in targets:
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
        print(f"ERROR: {error}")

    return 1 if errors else 0


if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
