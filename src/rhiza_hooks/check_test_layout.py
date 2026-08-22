#!/usr/bin/env python3
"""Check that the test layout mirrors the source layout.

Enforces a strict test/source parity so tests are easy to locate and no test
drifts loose from what it covers:

  * every source module ``<src>/…/xyz.py`` has a test file
    ``<tests>/…/test_xyz.py`` (nested packages are mirrored);
  * every top-level ``class A`` in a source module has a matching ``TestA``
    class in that test file;
  * no test file lacks a corresponding source module (no orphan test files);
  * no ``Test*`` class lacks a corresponding source class (no orphan test
    classes).

The reverse direction is the one that pays for itself: a renamed or retired
module leaves its tests behind, and those tests keep passing against nothing.

``__init__.py`` and ``conftest.py`` are ignored on both sides, and the
``tests/benchmarks/`` and ``tests/stress/`` trees are exempt entirely — those
hold benchmarks and stress tests that need not mirror a source module. Test
*functions* are unconstrained — the rules bind files and classes only.

Repositories that deliberately organise tests by *behaviour* rather than 1:1
mirroring (and guarantee per-module coverage another way, e.g. a 100% coverage
gate) can opt out via a ``[tool.check_test_layout]`` table in ``pyproject.toml``::

    [tool.check_test_layout]
    enforce = false
    reason = "Tests are grouped by behaviour; coverage is enforced by pytest."

``enforce = false`` requires a non-empty ``reason`` so the deviation is always
documented — an undocumented opt-out is indistinguishable from neglect. The same
table accepts ``exempt_dirs = [...]`` to extend the built-in benchmarks/stress
exemptions when parity *is* enforced, and ``exempt_files = [...]`` to exempt
individual test files by their path relative to the tests root — for a single
loose file, ``exempt_dirs`` cannot express it, since its first path component is
the file itself and exempting that reads as a directory that does not exist.

The configuration lives in ``pyproject.toml`` rather than under ``.rhiza/``
deliberately: the layout it describes is a property of the Python project, not of
the template that syncs its infrastructure, and a repo that is not rhiza-managed
must still be able to configure this hook.

Exit codes:
  0 - the layout is clean, or parity is intentionally not enforced
  1 - violations were found (every one is listed), or the opt-out is misconfigured
"""

from __future__ import annotations

import argparse
import ast
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path

from rhiza_hooks._repo import find_repo_root

_IGNORED = {"__init__.py", "conftest.py"}

# Top-level directories under the tests root that are exempt from parity by
# default: they hold benchmarks / stress tests that need not mirror a source
# module. A repo can extend this set via ``[tool.check_test_layout] exempt_dirs``.
_DEFAULT_EXEMPT_DIRS = {"benchmarks", "stress"}


def _read_config(pyproject: Path) -> dict[str, object]:
    """Return the ``[tool.check_test_layout]`` table from *pyproject* (empty if absent).

    A missing, malformed or unreadable pyproject.toml is somebody else's error to
    report — the same lenient stance the other hooks in this package take.

    Args:
        pyproject: Path to the ``pyproject.toml`` to read.

    Returns:
        The configuration table, or an empty dict when it cannot be read.
    """
    if not pyproject.is_file():
        return {}
    try:
        with pyproject.open("rb") as handle:
            data = tomllib.load(handle)
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError):
        # tomllib decodes the stream itself, so invalid UTF-8 surfaces as
        # UnicodeDecodeError rather than a TOML error.
        return {}
    section = data.get("tool", {}).get("check_test_layout", {})
    return section if isinstance(section, dict) else {}


def _exempt_dirs(config: Mapping[str, object]) -> set[str]:
    """Return the exempt top-level test dirs: defaults plus any from *config*."""
    dirs = set(_DEFAULT_EXEMPT_DIRS)
    extra = config.get("exempt_dirs")
    if isinstance(extra, list):
        dirs |= {str(d) for d in extra}
    return dirs


def _exempt_files(config: Mapping[str, object]) -> set[str]:
    """Return the exempt test files from *config* (none are exempt by default).

    Entries are paths relative to the tests root (POSIX separators), not bare
    names, so exempting one file cannot silently exempt a same-named file
    elsewhere in the tree.
    """
    entries = config.get("exempt_files")
    if not isinstance(entries, list):
        return set()
    return {str(f) for f in entries}


def _top_level_classes(path: Path) -> set[str]:
    """Return the names of top-level classes defined in *path*.

    The source is handed to :func:`ast.parse` as *bytes*, not text. Decoding it here
    would mean choosing an encoding, and the platform default is the wrong choice —
    on Windows that is cp1252, where any test file containing an em dash or an
    accented word raises ``UnicodeDecodeError`` and takes the whole check down.
    ``ast.parse`` decodes bytes per PEP 263, honouring a ``# -*- coding: -*-`` cookie
    and defaulting to UTF-8, which is exactly the rule the interpreter itself applies
    to the file.
    """
    tree = ast.parse(path.read_bytes(), filename=str(path))
    return {node.name for node in tree.body if isinstance(node, ast.ClassDef)}


def _source_modules(src: Path) -> list[Path]:
    """Return the source ``.py`` modules under *src* (ignoring dunder/conftest)."""
    return sorted(p for p in src.rglob("*.py") if p.name not in _IGNORED)


def _test_files(tests: Path, exempt: set[str] | None = None, exempt_files: set[str] | None = None) -> list[Path]:
    """Return the ``test_*.py`` files under *tests* (ignoring conftest/exempt dirs and files)."""
    exempt = _DEFAULT_EXEMPT_DIRS if exempt is None else exempt
    exempt_files = exempt_files or set()
    return sorted(
        p
        for p in tests.rglob("test_*.py")
        if p.name not in _IGNORED
        and p.relative_to(tests).parts[0] not in exempt
        and p.relative_to(tests).as_posix() not in exempt_files
    )


def check(src: Path, tests: Path, config: Mapping[str, object] | None = None) -> list[str]:
    """Return a list of layout violations (empty when the layout is clean)."""
    config = config or {}
    exempt = _exempt_dirs(config)
    exempt_files = _exempt_files(config)
    errors: list[str] = []

    # Forward: every source module needs a mirrored test file + Test* classes.
    for module in _source_modules(src):
        rel = module.relative_to(src)
        test_path = tests / rel.parent / f"test_{module.stem}.py"
        if not test_path.exists():
            errors.append(f"missing test file {test_path} for source module {module}")
            continue
        test_classes = _top_level_classes(test_path)
        for cls in sorted(_top_level_classes(module)):
            if f"Test{cls}" not in test_classes:
                errors.append(f"missing class Test{cls} in {test_path} for class {cls} in {module}")

    # Reverse: every test file/class must trace back to a source module/class.
    for test_file in _test_files(tests, exempt, exempt_files):
        rel = test_file.relative_to(tests)
        source_name = test_file.stem[len("test_") :]
        source_path = src / rel.parent / f"{source_name}.py"
        if not source_path.exists():
            errors.append(f"orphan test file {test_file} (no source module {source_path})")
            continue
        source_classes = _top_level_classes(source_path)
        for cls in sorted(_top_level_classes(test_file)):
            if cls.startswith("Test") and cls[len("Test") :] not in source_classes:
                errors.append(
                    f"orphan test class {cls} in {test_file} (no class {cls[len('Test') :]} in {source_path})"
                )

    return errors


def main(argv: list[str] | None = None) -> int:
    """Run the hook and return a process exit code.

    ``--src``/``--tests``/``--config`` are resolved against the current working
    directory (pre-commit runs hooks from the repository root); the defaults are
    anchored to the repository root itself, so the hook also behaves when invoked
    from a subdirectory by hand.
    """
    parser = argparse.ArgumentParser(description="Check test/source layout parity.")
    parser.add_argument(
        "filenames",
        nargs="*",
        help="Filenames (ignored: parity is a property of the whole tree, not of one file)",
    )
    parser.add_argument("--src", default=None, help="Source directory (default: <repo root>/src).")
    parser.add_argument("--tests", default=None, help="Tests directory (default: <repo root>/tests).")
    parser.add_argument(
        "--config",
        default=None,
        help="pyproject.toml providing [tool.check_test_layout] (default: <repo root>/pyproject.toml).",
    )
    args = parser.parse_args(argv)

    repo_root = find_repo_root()
    src = Path(args.src) if args.src else repo_root / "src"
    tests = Path(args.tests) if args.tests else repo_root / "tests"
    config = _read_config(Path(args.config) if args.config else repo_root / "pyproject.toml")

    if not config.get("enforce", True):
        reason = str(config.get("reason", "")).strip()
        if not reason:
            print(
                "Test-layout check misconfigured: [tool.check_test_layout] enforce=false "
                "requires a non-empty 'reason' documenting the intentional layout.",
                file=sys.stderr,
            )
            return 1
        print(f"Test layout OK: parity not enforced by request — {reason}")
        return 0

    errors = check(src, tests, config)
    if errors:
        print("Test-layout check failed:", file=sys.stderr)
        for err in errors:
            print(f"  ✗ {err}", file=sys.stderr)
        return 1
    print("Test layout OK: tests mirror sources 1:1")
    return 0


if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
