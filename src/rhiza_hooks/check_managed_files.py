#!/usr/bin/env python3
"""Refuse to commit an edit to a file the rhiza template owns.

A rhiza-managed repo syncs its development infrastructure from a template repo,
and every such repo's CLAUDE.md opens with the same rule: do not edit the managed
files, because the next sync overwrites them. Until this hook there was nothing
enforcing it — `make validate`, the one drift check that existed, was removed
upstream after rhiza v1.1.3.

So the failure mode was silent and total: edit a managed file, watch it work, get
it reviewed and merged, and lose it at the next sync with no error at any point.
This hook makes that loud at the commit that causes it.

The check is path-based, because ``.rhiza/template.lock`` records paths and no
content hashes. That is the right signal anyway — the objection is not "your edit
is wrong" but "this file is not yours to edit".

Only a file that actually **differs from HEAD** is reported, not merely one that is
managed and present. pre-commit normally passes just the staged paths, but under
``--all-files`` — which ``make fmt`` and CI use — it passes every tracked file, and
without this the hook would report all sixty-odd managed files on a clean tree.
When git cannot answer (no HEAD yet, or no git at all) the hook falls back to
trusting the paths it was given, which is pre-commit's normal contract.

Bypassing it:
  - a path listed under ``exclude:`` in ``.rhiza/template.yml`` is not synced, so it
    is not managed and never reported (see :mod:`rhiza_hooks._managed`);
  - ``--allow PATH`` waives one path for a deliberate, knowingly-temporary override;
  - ``SKIP=check-managed-files git commit`` waives the whole hook, which is what a
    ``rhiza sync`` commit needs, since rewriting managed files wholesale is exactly
    its job.

Exit codes:
  0 - no managed file is being modified
  1 - at least one managed file is being modified
"""

from __future__ import annotations

import argparse
import subprocess  # nosec B404
import sys
from pathlib import Path

from rhiza_hooks._managed import CONFIG_PATH, managed_paths, template_repository
from rhiza_hooks._repo import find_repo_root


def repo_relative(filename: str, repo_root: Path) -> str:
    """Normalise a hook argument to a repo-relative POSIX path for comparison.

    pre-commit already passes repo-relative paths, but a hand-run invocation may
    pass absolute or ``./``-prefixed ones. A path outside the repository is
    returned as-is: it cannot match a managed path, so it is reported by nobody.

    Args:
        filename: Path as given on the command line.
        repo_root: Root directory of the repository.

    Returns:
        The path, relative to ``repo_root`` where possible, with forward slashes.
    """
    path = Path(filename)
    if path.is_absolute():
        try:
            path = path.relative_to(repo_root)
        except ValueError:
            return path.as_posix()
    return path.as_posix()


def modified_paths(repo_root: Path) -> set[str] | None:
    """Return the tracked paths that differ from HEAD, staged or not.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        Repo-relative paths with changes, or None when git cannot answer — no git on
        PATH, no commits yet, or not a work tree. The caller then trusts the paths it
        was handed instead of narrowing them.
    """
    try:
        result = subprocess.run(  # nosec B603 B607
            ["git", "diff", "--name-only", "HEAD"],  # noqa: S607
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _offenders(filenames: list[str], repo_root: Path, managed: set[str], allowed: set[str]) -> list[str]:
    """Return the managed paths being modified among ``filenames``, in a stable order."""
    given = {repo_relative(filename, repo_root) for filename in filenames}
    modified = modified_paths(repo_root)
    if modified is not None:
        given &= modified
    return sorted((given & managed) - allowed)


def check_managed_files(filenames: list[str], repo_root: Path, allowed: set[str]) -> list[str]:
    """Report each given path that the template owns.

    Args:
        filenames: Paths being committed, as passed by pre-commit.
        repo_root: Root directory of the repository.
        allowed: Paths waived via ``--allow``.

    Returns:
        List of error messages, one per offending path (empty when none is managed).
    """
    managed = managed_paths(repo_root)
    if not managed:
        # Not managed, or managed but never synced: nothing is owned upstream.
        return []

    origin = template_repository(repo_root) or "the template repository"
    return [
        f"{path} is owned by {origin} and will be overwritten by the next sync. "
        f"Change it upstream and re-sync, or add it to exclude: in {CONFIG_PATH.as_posix()}."
        for path in _offenders(filenames, repo_root, managed, allowed)
    ]


def main(argv: list[str] | None = None) -> int:
    """Run the hook and return a process exit code."""
    parser = argparse.ArgumentParser(description="Refuse edits to files owned by the rhiza template")
    parser.add_argument(
        "filenames",
        nargs="*",
        help="Filenames to check (passed by pre-commit)",
    )
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="PATH",
        help="Waive one managed path; repeatable. Prefer exclude: in .rhiza/template.yml for anything permanent.",
    )
    args = parser.parse_args(argv)

    errors = check_managed_files(args.filenames, find_repo_root(), set(args.allow))

    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        print("Bypass this hook for a sync commit with: SKIP=check-managed-files git commit ...")

    return 1 if errors else 0


if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
