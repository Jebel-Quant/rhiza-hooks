"""Tests for the canonical test-layout checker (``scripts/check_test_layout.py``).

This file lives in ``tests/meta/`` — an exempt directory declared via
``[tool.check_test_layout] exempt_dirs = ["meta"]`` in ``pyproject.toml`` — so
the checker itself does not flag it as an orphan when it finds no matching
``src/check_test_layout.py``.
"""

from __future__ import annotations

from pathlib import Path

import check_test_layout as ctl
import pytest


def _write(path: Path, text: str = "") -> None:
    """Create *path* (and any parents) and write *text* to it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_repo_layout_passes() -> None:
    """The current repository layout satisfies the canonical checker."""
    root = Path(__file__).resolve().parent.parent.parent
    config = ctl._read_config(root / "pyproject.toml")
    errors = ctl.check(root / "src", root / "tests", config)
    assert errors == []


def test_top_level_classes(tmp_path: Path) -> None:
    """Only top-level class definitions are returned, not nested or functions."""
    f = tmp_path / "m.py"
    f.write_text("class A:\n    pass\n\n\ndef g():\n    pass\n", encoding="utf-8")
    assert ctl._top_level_classes(f) == {"A"}


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


# --- configuration & opt-out --------------------------------------------------


def test_coerce_scalar() -> None:
    """``_coerce_scalar`` converts the TOML subset used by the config table."""
    assert ctl._coerce_scalar('"hello"') == "hello"
    assert ctl._coerce_scalar("'hello'") == "hello"
    assert ctl._coerce_scalar('"tail # not a comment"') == "tail # not a comment"
    assert ctl._coerce_scalar("true") is True
    assert ctl._coerce_scalar("false  # inline comment") is False
    assert ctl._coerce_scalar("bare") == "bare"
    assert ctl._coerce_scalar('[ "a", "b" ]') == ["a", "b"]
    assert ctl._coerce_scalar("[]") == []
    assert ctl._coerce_scalar('"unterminated') == "unterminated"
    assert ctl._coerce_scalar('["unterminated') == ["unterminated"]


def test_parse_flat_section() -> None:
    """``_parse_flat_section`` extracts the named table from raw TOML text."""
    text = (
        "# comment\n"
        "[project]\n"
        'name = "x"\n'
        "\n"
        "[tool.check_test_layout]\n"
        "enforce = false\n"
        "# a comment line\n"
        'reason = "grouped by behaviour"\n'
        'exempt_dirs = ["integration"]\n'
        "\n"
        "[tool.other]\n"
        "ignored = true\n"
    )
    section = ctl._parse_flat_section(text, "tool.check_test_layout")
    assert section == {
        "enforce": False,
        "reason": "grouped by behaviour",
        "exempt_dirs": ["integration"],
    }


def test_read_config_absent(tmp_path: Path) -> None:
    """``_read_config`` returns an empty dict when ``pyproject.toml`` is missing."""
    assert ctl._read_config(tmp_path / "pyproject.toml") == {}


def test_read_config_via_tomllib(tmp_path: Path) -> None:
    """``_read_config`` parses the section when ``tomllib``/``tomli`` is available."""
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


def test_read_config_fallback_without_tomllib(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The flat-table fallback reader works when ``tomllib`` is unavailable."""
    monkeypatch.setattr(ctl, "tomllib", None)
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.check_test_layout]\nenforce = false\nreason = "behaviour-grouped"\n',
        encoding="utf-8",
    )
    assert ctl._read_config(pyproject) == {"enforce": False, "reason": "behaviour-grouped"}


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
