#!/usr/bin/env python3
"""Shared lenient TOML loader.

Every hook that reads a TOML file — ``pyproject.toml``, ``Cargo.toml``,
``rust-toolchain.toml``, ``.bumpversion.toml`` — treats a missing, malformed or
unreadable file as "unspecified": a broken manifest is somebody else's error to
report, not a reason to crash the commit. That stance used to be implemented
separately in five modules, whose ``except`` tuples drifted apart until two of
them crashed on invalid UTF-8 (#396). This module is now the only place that
calls :func:`tomllib.load`.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def load_toml(path: Path) -> dict[str, Any] | None:
    """Parse a TOML file, treating unreadable or malformed input as absent.

    Args:
        path: File to parse.

    Returns:
        The parsed mapping, or None if the file is missing, malformed, not valid
        UTF-8, or cannot be opened (for example, the path is a directory).
    """
    if not path.exists():
        return None
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError):
        # tomllib decodes the stream itself, so invalid UTF-8 surfaces as
        # UnicodeDecodeError rather than a TOML error. Anything else (e.g. a
        # genuine bug) is left to surface.
        return None
