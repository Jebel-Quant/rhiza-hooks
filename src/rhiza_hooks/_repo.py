#!/usr/bin/env python3
"""Shared internal helpers for rhiza hooks."""

from __future__ import annotations

from pathlib import Path


def find_repo_root() -> Path:
    """Find the repository root directory.

    Walks up from the current working directory looking for a ``.git`` entry.

    Returns:
        Path to the nearest ancestor containing ``.git``, or the current
        working directory if none is found.
    """
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return Path.cwd()
