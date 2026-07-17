#!/usr/bin/env python3
"""Check the repository's intentional flat test layout.

This repository keeps its tests flat under ``tests/`` by *concern* rather than
mirroring ``src/rhiza_hooks/`` 1:1:

* dedicated unit tests usually live in ``tests/test_<module>.py``;
* private helper modules may be covered by a broader public-module test file;
* cross-cutting integration/property/end-to-end tests are allowed when they
  still trace back to one or more package modules.

The check enforced here is therefore "every source module is covered by at
least one test file, and every ``tests/test_*.py`` file is either covering a
package module or explicitly allowed as repository meta-test".
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "src" / "rhiza_hooks"
DEFAULT_TESTS = ROOT / "tests"
PACKAGE = "rhiza_hooks"
_IGNORED = {"__init__.py", "conftest.py"}

# Cross-cutting tests that exercise modules via subprocess / pre-commit wiring
# rather than direct Python imports.
_EXPLICIT_TEST_COVERAGE: dict[str, set[str]] = {
    "test_precommit_e2e.py": {"check_python_version.py"},
    "test_scripts.py": {
        "check_makefile_targets.py",
        "check_python_version.py",
        "check_rhiza_config.py",
        "check_template_bundles.py",
        "check_workflow_names.py",
        "update_readme_help.py",
    },
}

# Meta-tests for the checker itself are intentionally unrelated to src/rhiza_hooks.
_IGNORED_TESTS = {"test_check_test_layout.py"}


def _source_modules(src: Path) -> list[Path]:
    """Return package modules under *src*."""
    return sorted(p for p in src.rglob("*.py") if p.name not in _IGNORED)


def _test_files(tests: Path) -> list[Path]:
    """Return ``tests/test_*.py`` files."""
    return sorted(p for p in tests.rglob("test_*.py") if p.name not in _IGNORED)


def _module_path_from_import(module: str, *, package: str) -> Path | None:
    """Map ``rhiza_hooks.foo`` to ``foo.py`` relative to the package root."""
    if module == package:
        return None
    prefix = f"{package}."
    if not module.startswith(prefix):
        return None
    return Path(*module.removeprefix(prefix).split(".")).with_suffix(".py")


def _imported_modules(test_file: Path, *, package: str) -> set[Path]:
    """Return package modules imported by *test_file*."""
    tree = ast.parse(test_file.read_text(encoding="utf-8"), filename=str(test_file))
    modules: set[Path] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_path = _module_path_from_import(alias.name, package=package)
                if module_path is not None:
                    modules.add(module_path)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            module_path = _module_path_from_import(node.module, package=package)
            if module_path is not None:
                modules.add(module_path)
    return modules


def _covered_modules(
    test_file: Path,
    tests: Path,
    *,
    package: str,
    explicit_test_coverage: dict[str, set[str]],
) -> set[Path]:
    """Return the source modules covered by *test_file*."""
    rel = test_file.relative_to(tests).as_posix()
    imported = _imported_modules(test_file, package=package)
    explicit = {Path(name) for name in explicit_test_coverage.get(rel, set())}
    return imported | explicit


def check(
    src: Path,
    tests: Path,
    *,
    package: str = PACKAGE,
    explicit_test_coverage: dict[str, set[str]] | None = None,
    ignored_tests: set[str] | None = None,
) -> list[str]:
    """Return layout violations for the repository's concern-based test scheme."""
    explicit_test_coverage = explicit_test_coverage or _EXPLICIT_TEST_COVERAGE
    ignored_tests = ignored_tests or _IGNORED_TESTS

    errors: list[str] = []
    source_modules = {module.relative_to(src) for module in _source_modules(src)}
    covered_by_source = {module: [] for module in source_modules}

    for test_file in _test_files(tests):
        rel = test_file.relative_to(tests)
        rel_str = rel.as_posix()
        if rel_str in ignored_tests:
            continue

        covered = _covered_modules(
            test_file,
            tests,
            package=package,
            explicit_test_coverage=explicit_test_coverage,
        )
        known = sorted(module for module in covered if module in source_modules)
        unknown = sorted(module for module in covered if module not in source_modules)

        if not known:
            errors.append(f"unmapped test file {test_file} (no covered module in {src})")
            continue

        for module in known:
            covered_by_source[module].append(rel_str)
        for module in unknown:
            errors.append(f"unknown module mapping {module} referenced by {test_file}")

    for module, covering_tests in sorted(covered_by_source.items()):
        if not covering_tests:
            errors.append(f"missing test coverage for source module {src / module}")

    return errors


def main(argv: list[str] | None = None) -> int:
    """Entry point: validate the repository's flat test layout."""
    parser = argparse.ArgumentParser(description="Check the repo's concern-based test layout.")
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC, help="Package source directory.")
    parser.add_argument("--tests", type=Path, default=DEFAULT_TESTS, help="Tests directory.")
    parser.add_argument("--package", default=PACKAGE, help="Package import root.")
    args = parser.parse_args(argv)

    errors = check(args.src, args.tests, package=args.package)
    if errors:
        print("Test-layout check failed:", file=sys.stderr)
        for err in errors:
            print(f"  ✗ {err}", file=sys.stderr)
        return 1

    print("Test layout OK: flat concern-based tests cover all source modules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
