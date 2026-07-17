"""Tests for the repository-specific ``scripts/check_test_layout.py`` checker."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_checker():
    root = Path(__file__).resolve().parent.parent
    path = root / "scripts" / "check_test_layout.py"
    spec = importlib.util.spec_from_file_location("check_test_layout", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ctl = _load_checker()


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_repo_layout_passes() -> None:
    """The current repository layout satisfies the local checker."""
    root = Path(__file__).resolve().parent.parent
    assert ctl.check(root / "src" / "rhiza_hooks", root / "tests") == []


def test_import_and_explicit_coverage_count(tmp_path: Path) -> None:
    """Imported modules and explicit mappings both satisfy coverage."""
    src = tmp_path / "src" / "rhiza_hooks"
    tests = tmp_path / "tests"
    _write(src / "alpha.py", "VALUE = 1\n")
    _write(src / "beta.py", "VALUE = 2\n")
    _write(tests / "test_alpha.py", "from rhiza_hooks.alpha import VALUE\n")
    _write(tests / "test_runner.py", "def test_runner():\n    assert True\n")

    assert (
        ctl.check(
            src,
            tests,
            explicit_test_coverage={"test_runner.py": {"beta.py"}},
            ignored_tests=set(),
        )
        == []
    )


def test_missing_coverage_is_reported(tmp_path: Path) -> None:
    """A source module with no covering test is reported."""
    src = tmp_path / "src" / "rhiza_hooks"
    tests = tmp_path / "tests"
    _write(src / "alpha.py", "VALUE = 1\n")
    tests.mkdir()

    errors = ctl.check(src, tests, explicit_test_coverage={}, ignored_tests=set())
    assert any("missing test coverage for source module" in error for error in errors)


def test_unmapped_test_file_is_reported(tmp_path: Path) -> None:
    """A ``tests/test_*.py`` file must map to a module or be explicitly allowed."""
    src = tmp_path / "src" / "rhiza_hooks"
    tests = tmp_path / "tests"
    src.mkdir(parents=True)
    _write(tests / "test_misc.py", "def test_misc():\n    assert True\n")

    errors = ctl.check(src, tests, explicit_test_coverage={}, ignored_tests=set())
    assert any("unmapped test file" in error for error in errors)
