#!/usr/bin/env python3
"""Work out which paths in this repo are owned by the template, not by the project.

A rhiza-managed repo syncs its development infrastructure from a template repo.
``.rhiza/template.lock`` records what the last sync wrote, and
``.rhiza/template.yml`` records what the project deliberately opted out of. The
set of *template-owned* paths is the first minus the second, and it is the answer
several hooks need: editing such a path is pointless (the next sync overwrites
it), and pointing release tooling at one is actively harmful.

The subtraction is not optional. The lock's ``files:`` block lists every path the
profile would deliver **including ones the project excludes** — and the lock's own
``exclude:`` key does not mirror ``template.yml``'s (it is ``[]`` in a repo with two
active exclusions). So ``template.yml`` is the only reliable source for the opt-outs,
and a caller that trusted ``files:`` alone would flag files the project legitimately
owns.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rhiza_hooks._yaml import YamlFailure, load_yaml_mapping

LOCK_PATH = Path(".rhiza") / "template.lock"
CONFIG_PATH = Path(".rhiza") / "template.yml"


def _string_list(data: dict[Any, Any], key: str) -> set[str]:
    """Read ``key`` from ``data`` as a set of strings, tolerating any other shape.

    A malformed value (absent, scalar, mapping) yields an empty set rather than an
    error: these hooks report on project files, and a broken ``.rhiza/`` document is
    ``check-rhiza-config``'s business to report, not theirs.
    """
    value = data.get(key)
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value}


def managed_paths(repo_root: Path) -> set[str]:
    """Return the repo-relative paths the template owns.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        Paths listed in ``.rhiza/template.lock``'s ``files:`` block, minus those
        the project excludes in ``.rhiza/template.yml``. Empty when the lock is
        missing or unusable — a repo that is managed but not yet synced owns
        everything, so callers then have nothing to enforce.
    """
    lock = load_yaml_mapping(repo_root / LOCK_PATH)
    if isinstance(lock, YamlFailure):
        return set()

    config = load_yaml_mapping(repo_root / CONFIG_PATH)
    excluded = set() if isinstance(config, YamlFailure) else _string_list(config, "exclude")

    return _string_list(lock, "files") - excluded


def template_repository(repo_root: Path) -> str | None:
    """Return the template repository recorded by the last sync, e.g. ``owner/repo``.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        The lock's ``repo`` value, or None when the lock is missing or does not
        record one. Callers use it to name where a managed file should be changed
        instead; the lock maps no file to its originating *bundle*, so the
        repository is as specific as this can get.
    """
    lock = load_yaml_mapping(repo_root / LOCK_PATH)
    if isinstance(lock, YamlFailure):
        return None
    repo = lock.get("repo")
    return repo if isinstance(repo, str) else None
