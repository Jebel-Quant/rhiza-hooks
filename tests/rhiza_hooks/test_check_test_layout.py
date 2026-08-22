"""Tests for the ``rhiza_hooks.check_test_layout`` module.

This file is itself the hook's own dogfood: ``test_repo_layout_passes`` runs the
checker over this repository, so the mirroring rule it publishes is the rule its
own tree is held to.
"""

from __future__ import annotations

import runpy
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

from rhiza_hooks import check_test_layout as ctl


def _write(path: Path, text: str = "") -> None:
    """Create *path* (and any parents) and write *text* to it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_repo_layout_passes() -> None:
    """The current repository layout satisfies the checker."""
    root = Path(__file__).resolve().parent.parent.parent
    config = ctl._read_config(root / "pyproject.toml")
    errors = ctl.check(root / "src", root / "tests", config)
    assert errors == []


def test_top_level_classes(tmp_path: Path) -> None:
    """Only top-level class definitions are returned, not nested or functions."""
    f = tmp_path / "m.py"
    f.write_text("class A:\n    pass\n\n\ndef g():\n    pass\n", encoding="utf-8")
    assert ctl._top_level_classes(f) == {"A"}


def test_top_level_classes_reads_non_ascii_source(tmp_path: Path) -> None:
    """A source file holding non-ASCII UTF-8 is parsed, not decoded by the platform default.

    The bytes are written explicitly so the file on disk is UTF-8 whatever the host's
    default happens to be. Reading it back with that default is what used to fail: on
    Windows (cp1252) the em dash below raised ``UnicodeDecodeError`` and took down the
    whole layout check, which reads every test file in the repo.
    """
    f = tmp_path / "m.py"
    f.write_bytes("# rôle : générer — voilà 🪝\nclass Café:\n    pass\n".encode())
    assert ctl._top_level_classes(f) == {"Café"}


def test_discovery_ignores_dunder_and_conftest(tmp_path: Path) -> None:
    """``__init__.py`` and ``conftest.py`` are silently excluded from both sides."""
    src = tmp_path / "src"
    _write(src / "a.py")
    _write(src / "__init__.py")
    _write(src / "conftest.py")
    tests = tmp_path / "tests"
    _write(tests / "test_a.py")
    _write(tests / "conftest.py")
    assert [p.name for p in ctl._source_modules(src)] == ["a.py"]
    assert [p.name for p in ctl._test_files(tests)] == ["test_a.py"]


def test_clean_layout_has_no_errors(tmp_path: Path) -> None:
    """A perfectly mirrored layout (including nested packages) reports no errors."""
    src, tests = tmp_path / "src", tmp_path / "tests"
    _write(src / "pkg" / "foo.py", "class Bar:\n    pass\n")
    _write(tests / "pkg" / "test_foo.py", "class TestBar:\n    pass\n")
    assert ctl.check(src, tests) == []


def test_missing_test_file(tmp_path: Path) -> None:
    """A source module with no matching test file is reported."""
    src, tests = tmp_path / "src", tmp_path / "tests"
    _write(src / "foo.py", "x = 1\n")
    tests.mkdir()
    assert any("missing test file" in e for e in ctl.check(src, tests))


def test_missing_test_class(tmp_path: Path) -> None:
    """A source class with no matching ``Test*`` class in the test file is reported."""
    src, tests = tmp_path / "src", tmp_path / "tests"
    _write(src / "foo.py", "class Bar:\n    pass\n")
    _write(tests / "test_foo.py", "def test_x():\n    pass\n")
    assert any("missing class TestBar" in e for e in ctl.check(src, tests))


def test_benchmarks_and_stress_are_exempt(tmp_path: Path) -> None:
    """``benchmarks/`` and ``stress/`` are exempt from orphan detection by default."""
    src, tests = tmp_path / "src", tmp_path / "tests"
    src.mkdir()
    _write(tests / "benchmarks" / "test_speed.py", "def test_x():\n    pass\n")
    _write(tests / "stress" / "test_load.py", "class TestGhost:\n    pass\n")
    assert ctl.check(src, tests) == []


def test_orphan_test_file(tmp_path: Path) -> None:
    """A test file with no corresponding source module is reported as an orphan."""
    src, tests = tmp_path / "src", tmp_path / "tests"
    src.mkdir()
    _write(tests / "test_ghost.py", "def test_x():\n    pass\n")
    assert any("orphan test file" in e for e in ctl.check(src, tests))


def test_orphan_test_class(tmp_path: Path) -> None:
    """A ``Test*`` class with no matching source class is reported as an orphan."""
    src, tests = tmp_path / "src", tmp_path / "tests"
    _write(src / "foo.py", "x = 1\n")
    _write(tests / "test_foo.py", "class TestBar:\n    pass\n")
    assert any("orphan test class TestBar" in e for e in ctl.check(src, tests))


def test_main_ok(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """``main()`` exits 0 and prints the success message for a clean layout."""
    src, tests = tmp_path / "src", tmp_path / "tests"
    _write(src / "foo.py", "class Bar:\n    pass\n")
    _write(tests / "test_foo.py", "class TestBar:\n    pass\n")
    assert ctl.main(["--src", str(src), "--tests", str(tests)]) == 0
    assert "Test layout OK" in capsys.readouterr().out


def test_main_reports_and_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """``main()`` exits 1 and prints all violations for a broken layout."""
    src, tests = tmp_path / "src", tmp_path / "tests"
    _write(src / "foo.py", "x = 1\n")
    tests.mkdir()
    assert ctl.main(["--src", str(src), "--tests", str(tests)]) == 1
    assert "check failed" in capsys.readouterr().err


def test_main_ignores_passed_filenames(tmp_path: Path) -> None:
    """Positional filenames are accepted and ignored.

    The manifest sets ``pass_filenames: false`` because parity is a property of the
    whole tree, but a consumer who flips that flag must not get an argparse error.
    """
    src, tests = tmp_path / "src", tmp_path / "tests"
    _write(src / "foo.py", "class Bar:\n    pass\n")
    _write(tests / "test_foo.py", "class TestBar:\n    pass\n")
    assert ctl.main(["src/foo.py", "--src", str(src), "--tests", str(tests)]) == 0


def test_main_defaults_to_the_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With no flags the hook checks ``<repo root>/src`` against ``<repo root>/tests``.

    pre-commit runs hooks from the repository root, but a hand invocation from a
    subdirectory must not silently check two directories that do not exist and
    report a clean layout.
    """
    _write(tmp_path / "src" / "foo.py", "class Bar:\n    pass\n")
    _write(tmp_path / "tests" / "test_foo.py", "def test_x():\n    pass\n")
    monkeypatch.setattr(ctl, "find_repo_root", lambda: tmp_path)
    assert ctl.main([]) == 1


def test_module_executes_main() -> None:
    """Module execution calls main and exits with its return value."""
    with patch("rhiza_hooks.check_test_layout.sys.exit") as mock_exit:
        # The module is already imported (top-level test import), so runpy warns it was
        # "found in sys.modules ... prior to execution"; filter just that warning rather
        # than mutating sys.modules, which would break module identity for the tests above.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=r".*found in sys\.modules.*", category=RuntimeWarning)
            with patch.object(ctl.sys, "argv", ["check-test-layout"]):
                runpy.run_module("rhiza_hooks.check_test_layout", run_name="__main__")
        mock_exit.assert_called_once_with(0)


# --- configuration & opt-out --------------------------------------------------


def test_read_config_absent(tmp_path: Path) -> None:
    """``_read_config`` returns an empty dict when ``pyproject.toml`` is missing."""
    assert ctl._read_config(tmp_path / "pyproject.toml") == {}


def test_read_config_reads_the_section(tmp_path: Path) -> None:
    """``_read_config`` parses the ``[tool.check_test_layout]`` table."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.check_test_layout]\nenforce = false\nreason = "behaviour-grouped"\n',
        encoding="utf-8",
    )
    assert ctl._read_config(pyproject) == {"enforce": False, "reason": "behaviour-grouped"}


def test_read_config_no_section(tmp_path: Path) -> None:
    """``_read_config`` returns an empty dict when the section is absent."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\n', encoding="utf-8")
    assert ctl._read_config(pyproject) == {}


def test_read_config_section_not_a_table(tmp_path: Path) -> None:
    """``_read_config`` returns an empty dict when the section is not a table."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[tool]\ncheck_test_layout = "oops"\n', encoding="utf-8")
    assert ctl._read_config(pyproject) == {}


def test_read_config_malformed_toml(tmp_path: Path) -> None:
    """``_read_config`` returns an empty dict for unparseable TOML."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("this is = = not toml [\n", encoding="utf-8")
    assert ctl._read_config(pyproject) == {}


def test_read_config_invalid_utf8(tmp_path: Path) -> None:
    """``_read_config`` returns an empty dict for a file that is not valid UTF-8.

    tomllib decodes the stream itself, so bad bytes surface as ``UnicodeDecodeError``
    rather than as a TOML error — a separate arm of the same ``except``.
    """
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_bytes(b'[tool.check_test_layout]\nreason = "\xff\xfe"\n')
    assert ctl._read_config(pyproject) == {}


def test_exempt_dirs_extends_defaults() -> None:
    """``_exempt_dirs`` merges config entries with the built-in defaults."""
    assert ctl._exempt_dirs({}) == {"benchmarks", "stress"}
    assert ctl._exempt_dirs({"exempt_dirs": ["integration"]}) == {
        "benchmarks",
        "stress",
        "integration",
    }
    assert ctl._exempt_dirs({"exempt_dirs": "nope"}) == {"benchmarks", "stress"}


def test_check_respects_config_exempt_dirs(tmp_path: Path) -> None:
    """An ``exempt_dirs`` entry in config clears orphan errors for that subtree."""
    src, tests = tmp_path / "src", tmp_path / "tests"
    src.mkdir()
    _write(tests / "integration" / "test_flow.py", "def test_x():\n    pass\n")
    assert any("orphan test file" in e for e in ctl.check(src, tests))
    assert ctl.check(src, tests, {"exempt_dirs": ["integration"]}) == []


def test_exempt_files_from_config() -> None:
    """``_exempt_files`` reads the config list and defaults to exempting nothing."""
    assert ctl._exempt_files({}) == set()
    assert ctl._exempt_files({"exempt_files": ["test_ghost.py"]}) == {"test_ghost.py"}
    assert ctl._exempt_files({"exempt_files": "nope"}) == set()


def test_check_respects_config_exempt_files(tmp_path: Path) -> None:
    """An ``exempt_files`` entry clears orphan errors for that one file only.

    Entries are matched on the path relative to the tests root, so a same-named
    file in a subdirectory keeps being reported.
    """
    src, tests = tmp_path / "src", tmp_path / "tests"
    src.mkdir()
    _write(tests / "test_ghost.py", "class TestNothing:\n    pass\n")
    assert any("orphan test file" in e for e in ctl.check(src, tests))
    assert ctl.check(src, tests, {"exempt_files": ["test_ghost.py"]}) == []

    _write(tests / "pkg" / "test_ghost.py", "def test_x():\n    pass\n")
    errors = ctl.check(src, tests, {"exempt_files": ["test_ghost.py"]})
    assert [e for e in errors if "pkg" in e]


def test_main_enforce_false_ok(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """``enforce = false`` with a reason exits 0 and prints the opt-out message."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.check_test_layout]\nenforce = false\nreason = "behaviour-grouped suite"\n',
        encoding="utf-8",
    )
    assert ctl.main(["--src", str(tmp_path / "src"), "--config", str(pyproject)]) == 0
    out = capsys.readouterr().out
    assert "parity not enforced" in out
    assert "behaviour-grouped suite" in out


def test_main_enforce_false_requires_reason(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """``enforce = false`` without a ``reason`` exits 1 with a configuration error."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[tool.check_test_layout]\nenforce = false\n", encoding="utf-8")
    assert ctl.main(["--config", str(pyproject)]) == 1
    assert "requires a non-empty 'reason'" in capsys.readouterr().err
