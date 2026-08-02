#!/usr/bin/env python3
"""Check that pyproject.toml does not declare its licence twice over.

Declaring both a PEP 639 ``license`` expression and a legacy
``License :: OSI Approved :: …`` trove classifier is not merely redundant — it makes
the project **unbuildable**. ``setuptools>=77`` refuses outright:

    License classifiers have been superseded by license expressions … Please remove

and ``uv_build`` warns. The two are therefore mutually exclusive in practice, and the
failure shows up at build or publish time rather than at the commit that caused it.

This is a live problem in this ecosystem: rhiza's own synced test
``test_license_classifier_present`` still asserts the trove classifier through
template v1.2.1, which makes it unsatisfiable for exactly the PEP 639 layout
``/rhiza:license`` produces (filed upstream as jebel-quant/rhiza#1440). A hook cannot
fix the upstream test, but it can stop the broken combination reaching a build.

Only the *combination* is an error. Either form alone is fine, and so is the
pre-PEP-639 table form (``license = {file = "LICENSE"}``) alongside a classifier —
that combination is valid legacy metadata, and rejecting it would fail projects that
have not migrated and do not need to.

Validating the SPDX expression's syntax is deliberately out of scope: that needs a
license-expression library, and the value here is the rule that breaks builds.

Exit codes:
  0 - licence metadata is coherent
  1 - both forms are declared (or, with --require-license, neither is)
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path
from typing import Any

from rhiza_hooks._repo import find_repo_root

_CLASSIFIER_PREFIX = "License :: "


def _load_project_table(repo_root: Path) -> dict[str, Any] | None:
    """Read ``[project]`` from pyproject.toml, treating unusable input as absent.

    A missing, malformed or unreadable pyproject.toml is somebody else's error to
    report — the same lenient stance the other hooks in this package take.
    """
    path = repo_root / "pyproject.toml"
    if not path.exists():
        return None
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError):
        # tomllib decodes the stream itself, so invalid UTF-8 surfaces as
        # UnicodeDecodeError rather than a TOML error.
        return None
    project = data.get("project")
    return project if isinstance(project, dict) else None


def license_classifiers(project: dict[str, Any]) -> list[str]:
    """Return the ``License :: …`` trove classifiers declared in ``[project]``."""
    classifiers = project.get("classifiers")
    if not isinstance(classifiers, list):
        return []
    return [c for c in classifiers if isinstance(c, str) and c.startswith(_CLASSIFIER_PREFIX)]


def spdx_expression(project: dict[str, Any]) -> str | None:
    """Return the PEP 639 SPDX ``license`` expression, if that is the form in use.

    PEP 639 makes ``license`` a string. The older table forms
    (``{file = …}`` / ``{text = …}``) are *not* SPDX expressions and do not conflict
    with a classifier, so they read as absent here.
    """
    value = project.get("license")
    return value if isinstance(value, str) else None


def _conflicting_declaration(expression: str | None, classifiers: list[str]) -> list[str]:
    """Report the unbuildable combination: a PEP 639 expression *and* a classifier."""
    if expression is None or not classifiers:
        return []
    listed = ", ".join(repr(c) for c in classifiers)
    return [
        f"pyproject.toml declares both the PEP 639 license expression {expression!r} and "
        f"the classifier(s) {listed}. setuptools>=77 refuses to build a project that has "
        "both. Delete the classifier(s) and keep the expression."
    ]


def _missing_declaration(project: dict[str, Any], expression: str | None, classifiers: list[str]) -> list[str]:
    """Report a project that declares no licence in any form.

    ``"license" not in project`` is checked as well as the two accessors, so a table
    form (``license = {file = "LICENSE"}``) — which is a declaration, just not an
    SPDX expression — is not reported as absent.
    """
    if expression is None and not classifiers and "license" not in project:
        return ['pyproject.toml declares no license: add a PEP 639 license expression, e.g. license = "MIT".']
    return []


def check_license_metadata(repo_root: Path, require_license: bool = False) -> list[str]:
    """Check the licence metadata in pyproject.toml.

    Args:
        repo_root: Root directory of the repository.
        require_license: Also report a project that declares no licence at all.

    Returns:
        List of error messages (empty when the metadata is coherent).
    """
    project = _load_project_table(repo_root)
    if project is None:
        return []

    expression = spdx_expression(project)
    classifiers = license_classifiers(project)

    conflict = _conflicting_declaration(expression, classifiers)
    if conflict:
        return conflict
    if require_license:
        return _missing_declaration(project, expression, classifiers)
    return []


def main(argv: list[str] | None = None) -> int:
    """Run the hook and return a process exit code."""
    parser = argparse.ArgumentParser(description="Check pyproject.toml licence metadata is coherent")
    parser.add_argument(
        "filenames",
        nargs="*",
        help="Filenames (ignored, checks the repo's pyproject.toml)",
    )
    parser.add_argument(
        "--require-license",
        action="store_true",
        help="Also fail when no license is declared at all (off by default: a private package may have none)",
    )
    args = parser.parse_args(argv)

    errors = check_license_metadata(find_repo_root(), require_license=args.require_license)

    for error in errors:
        print(f"ERROR: {error}")

    return 1 if errors else 0


if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
