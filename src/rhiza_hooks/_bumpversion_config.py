#!/usr/bin/env python3
"""Read bump-my-version's configuration out of the filenames it auto-discovers.

This module is responsible solely for *obtaining* a bumpversion configuration —
locating the file bump-my-version would actually read, and normalising whichever
of its two formats that file uses into a :class:`BumpversionConfig`. Judging the
result (is it discoverable at all, does it agree with pyproject, are its targets
rewritable) lives in :mod:`rhiza_hooks.check_bumpversion_config`.

The two formats disagree about more than syntax, which is why they need separate
readers even though they produce the same shape:

* TOML holds the section at the top level (``.bumpversion.toml``) or nested under
  ``[tool]`` (``pyproject.toml``), and its targets are ``[[tool.bumpversion.files]]``
  tables carrying a ``filename`` key.
* INI holds a flat ``[bumpversion]`` section, and encodes each target's path in a
  sibling section *name* — ``[bumpversion:file:<path>]`` — rather than in a key.

Both readers take the same lenient stance as the rest of this package: a file that
is missing, malformed, or unreadable reads as absent rather than raising. A broken
``pyproject.toml`` is somebody else's error to report.
"""

from __future__ import annotations

import configparser
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# The only filenames bump-my-version auto-discovers, in its own search order. It
# stops at the first file carrying a bumpversion section. Any other path — however
# well-formed — is read only when passed explicitly via --config-file.
TOML_CANDIDATES = (".bumpversion.toml", "pyproject.toml")
INI_CANDIDATES = (".bumpversion.cfg", "setup.cfg")

# Every searched filename, TOML before INI, for error messages that need to name
# where the tool actually looked.
SEARCHED_FILENAMES = (*TOML_CANDIDATES, *INI_CANDIDATES)


@dataclass(frozen=True)
class BumpversionTarget:
    """One file entry a release would rewrite, normalised across both formats.

    ``search`` is None when the entry omits it (or gives a non-string) —
    bump-my-version then defaults to ``{current_version}``. ``regex`` marks an
    entry whose pattern is a regular expression, which cannot be counted
    literally; bump-my-version owns that check.
    """

    filename: str
    search: str | None
    regex: bool


@dataclass(frozen=True)
class BumpversionConfig:
    """The bumpversion configuration bump-my-version would read, and its targets.

    ``current_version`` is None when the section omits that key: there is then no
    stale value to bump from, which is different from one that disagrees with the
    project's. ``targets`` holds the normalised file entries, unusable ones dropped.
    """

    filename: str
    current_version: str | None
    targets: list[BumpversionTarget]


def load_toml(path: Path) -> dict[str, Any] | None:
    """Parse a TOML file, treating unreadable or malformed input as absent.

    Part of this module's cross-module surface: :mod:`check_bumpversion_config`
    reads ``[project].version`` and probes the undiscovered ``.rhiza/.cfg.toml``
    with it, so both go through the same lenient parse as the candidate search.

    Args:
        path: File to parse.

    Returns:
        The parsed mapping, or None if the file is missing, malformed, or cannot
        be opened.
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


def _toml_bumpversion_section(path: Path) -> dict[Any, Any] | None:
    """Return the bumpversion section of a TOML candidate, or None if it has none.

    ``.bumpversion.toml`` holds the section at the top level; ``pyproject.toml``
    nests it under ``[tool]``. Accept whichever this file uses. A section that is
    present but not a table reads as absent, like a malformed file.
    """
    data = load_toml(path)
    if data is None:
        return None
    tool = data.get("tool")
    section = tool.get("bumpversion") if isinstance(tool, dict) else None
    if section is None:
        section = data.get("bumpversion")
    return section if isinstance(section, dict) else None


def _toml_target(entry: Any) -> BumpversionTarget | None:
    """Normalise one ``[[tool.bumpversion.files]]`` entry, or None if it is unusable.

    An entry that is not a table, or carries no string ``filename``, has nothing
    checkable about it.
    """
    if not isinstance(entry, dict):
        return None
    filename = entry.get("filename")
    if not isinstance(filename, str):
        return None
    search = entry.get("search")
    return BumpversionTarget(
        filename=filename,
        search=search if isinstance(search, str) else None,
        regex=bool(entry.get("regex")),
    )


def _toml_targets(section: dict[Any, Any]) -> list[BumpversionTarget]:
    """Normalise a TOML section's ``[[tool.bumpversion.files]]`` entries, dropping unusable ones."""
    entries = section.get("files")
    if not isinstance(entries, list):
        return []
    return [target for entry in entries if (target := _toml_target(entry)) is not None]


def _ini_targets(parser: configparser.ConfigParser) -> list[BumpversionTarget]:
    """Normalise an INI parser's ``[bumpversion:file:<path>]`` sections.

    The INI format encodes the target path in the section name rather than in a
    ``filename`` key, so the two formats need separate readers even though they
    produce the same shape.
    """
    prefix = "bumpversion:file:"
    return [
        BumpversionTarget(
            filename=name[len(prefix) :],
            search=parser.get(name, "search", fallback=None),
            regex=parser.getboolean(name, "regex", fallback=False),
        )
        for name in parser.sections()
        if name.startswith(prefix)
    ]


def _find_toml_config(repo_root: Path) -> BumpversionConfig | None:
    """Locate the first TOML candidate carrying a bumpversion section."""
    for name in TOML_CANDIDATES:
        section = _toml_bumpversion_section(repo_root / name)
        if section is not None:
            declared = section.get("current_version")
            return BumpversionConfig(
                filename=name,
                current_version=declared if isinstance(declared, str) else None,
                targets=_toml_targets(section),
            )
    return None


def _find_ini_config(repo_root: Path) -> BumpversionConfig | None:
    """Locate the first INI candidate carrying a ``[bumpversion]`` section.

    Unlike the TOML reader this keeps the whole parser, because an INI config's
    targets live in sibling ``[bumpversion:file:<path>]`` sections rather than
    inside the main one.
    """
    for name in INI_CANDIDATES:
        parser = _load_ini(repo_root / name)
        if parser is not None and parser.has_section("bumpversion"):
            return BumpversionConfig(
                filename=name,
                current_version=parser.get("bumpversion", "current_version", fallback=None),
                targets=_ini_targets(parser),
            )
    return None


def find_config(repo_root: Path) -> BumpversionConfig | None:
    """Locate the bumpversion config bump-my-version would read, with its file entries.

    TOML candidates are searched before INI candidates, and the first file carrying
    a section wins — bump-my-version's own search order.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        The winning :class:`BumpversionConfig`, or None when no searched file
        carries a bumpversion section.
    """
    return _find_toml_config(repo_root) or _find_ini_config(repo_root)
