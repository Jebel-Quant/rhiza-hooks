"""Tests for the ``rhiza_hooks.check_license_metadata`` module."""

from __future__ import annotations

import runpy
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

from rhiza_hooks import check_license_metadata as clm

_CLASSIFIER = 'classifiers = ["License :: OSI Approved :: MIT License", "Private :: Do Not Upload"]'


def _pyproject(root: Path, body: str) -> None:
    """Write a pyproject.toml whose [project] table carries ``body``."""
    (root / "pyproject.toml").write_text(f'[project]\nname = "demo"\nversion = "1.0.0"\n{body}\n', encoding="utf-8")


def test_both_forms_error(tmp_path: Path) -> None:
    """An SPDX expression next to a License:: classifier is what breaks setuptools>=77."""
    _pyproject(tmp_path, f'license = "MIT"\n{_CLASSIFIER}')
    errors = clm.check_license_metadata(tmp_path)
    assert len(errors) == 1
    assert "'MIT'" in errors[0]
    assert "'License :: OSI Approved :: MIT License'" in errors[0]
    assert "setuptools>=77" in errors[0]


def test_every_offending_classifier_is_listed(tmp_path: Path) -> None:
    """All License:: classifiers are named, so one deletion pass fixes the file."""
    _pyproject(
        tmp_path,
        'license = "Apache-2.0"\nclassifiers = ["License :: OSI Approved :: Apache Software License", '
        '"License :: OSI Approved :: MIT License"]',
    )
    errors = clm.check_license_metadata(tmp_path)
    assert "Apache Software License" in errors[0]
    assert "MIT License" in errors[0]


def test_expression_alone_passes(tmp_path: Path) -> None:
    """A PEP 639 expression on its own is the modern, correct form."""
    _pyproject(tmp_path, 'license = "MIT"')
    assert clm.check_license_metadata(tmp_path) == []


def test_classifier_alone_passes(tmp_path: Path) -> None:
    """A classifier on its own is legacy but buildable."""
    _pyproject(tmp_path, _CLASSIFIER)
    assert clm.check_license_metadata(tmp_path) == []


@pytest.mark.parametrize("table", ['license = {file = "LICENSE"}', 'license = {text = "MIT"}'])
def test_legacy_table_with_classifier_passes(tmp_path: Path, table: str) -> None:
    """The pre-PEP-639 table form alongside a classifier is valid legacy metadata."""
    _pyproject(tmp_path, f"{table}\n{_CLASSIFIER}")
    assert clm.check_license_metadata(tmp_path) == []


def test_non_license_classifiers_are_ignored(tmp_path: Path) -> None:
    """Classifiers unrelated to licensing do not conflict with an expression."""
    _pyproject(tmp_path, 'license = "MIT"\nclassifiers = ["Programming Language :: Python :: 3.12"]')
    assert clm.check_license_metadata(tmp_path) == []


def test_malformed_classifiers_value_is_ignored(tmp_path: Path) -> None:
    """A classifiers value that is not a list yields nothing to compare."""
    _pyproject(tmp_path, 'license = "MIT"\nclassifiers = "License :: OSI Approved :: MIT License"')
    assert clm.check_license_metadata(tmp_path) == []


def test_non_string_classifier_entries_are_ignored(tmp_path: Path) -> None:
    """Odd entries inside classifiers do not crash the scan."""
    _pyproject(tmp_path, "license = \"MIT\"\nclassifiers = [42, 'Framework :: Pytest']")
    assert clm.check_license_metadata(tmp_path) == []


def test_no_license_passes_by_default(tmp_path: Path) -> None:
    """Declaring no licence is not an error unless asked for: a private package may have none."""
    _pyproject(tmp_path, 'description = "demo"')
    assert clm.check_license_metadata(tmp_path) == []


def test_no_license_errors_when_required(tmp_path: Path) -> None:
    """--require-license turns a missing licence into an error."""
    _pyproject(tmp_path, 'description = "demo"')
    errors = clm.check_license_metadata(tmp_path, require_license=True)
    assert len(errors) == 1
    assert errors[0].startswith("pyproject.toml declares no license")


def test_require_license_satisfied_by_classifier(tmp_path: Path) -> None:
    """A legacy classifier counts as declaring a licence."""
    _pyproject(tmp_path, _CLASSIFIER)
    assert clm.check_license_metadata(tmp_path, require_license=True) == []


def test_require_license_satisfied_by_table_form(tmp_path: Path) -> None:
    """The table form counts as declaring a licence even though it is not an SPDX expression."""
    _pyproject(tmp_path, 'license = {file = "LICENSE"}')
    assert clm.check_license_metadata(tmp_path, require_license=True) == []


def test_missing_pyproject_passes(tmp_path: Path) -> None:
    """No pyproject.toml means nothing to check."""
    assert clm.check_license_metadata(tmp_path, require_license=True) == []


def test_malformed_pyproject_passes(tmp_path: Path) -> None:
    """A pyproject.toml that will not parse is somebody else's error to report."""
    (tmp_path / "pyproject.toml").write_text("[project\nname =\n", encoding="utf-8")
    assert clm.check_license_metadata(tmp_path) == []


def test_pyproject_without_project_table_passes(tmp_path: Path) -> None:
    """A pyproject.toml with no [project] table declares no metadata to check."""
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 120\n", encoding="utf-8")
    assert clm.check_license_metadata(tmp_path) == []


def test_unreadable_pyproject_passes(tmp_path: Path) -> None:
    """An unreadable pyproject.toml is treated as absent rather than crashing the hook."""
    path = tmp_path / "pyproject.toml"
    path.write_bytes(b"\xff\xfe\x00")
    assert clm.check_license_metadata(tmp_path) == []


def test_this_repo_is_coherent() -> None:
    """rhiza-hooks itself declares its licence exactly once — the hook dogfoods clean."""
    assert clm.check_license_metadata(Path(__file__).resolve().parents[2], require_license=True) == []


def test_main_passes(tmp_path: Path, monkeypatch, capsys) -> None:
    """Coherent metadata exits 0 silently."""
    _pyproject(tmp_path, 'license = "MIT"')
    monkeypatch.setattr(clm, "find_repo_root", lambda: tmp_path)
    assert clm.main([]) == 0
    assert capsys.readouterr().out == ""


def test_main_reports_and_fails(tmp_path: Path, monkeypatch, capsys) -> None:
    """The conflicting combination exits 1 and prints an ERROR: line."""
    _pyproject(tmp_path, f'license = "MIT"\n{_CLASSIFIER}')
    monkeypatch.setattr(clm, "find_repo_root", lambda: tmp_path)
    assert clm.main(["pyproject.toml"]) == 1
    assert "ERROR: pyproject.toml declares both" in capsys.readouterr().err


def test_main_require_license_flag(tmp_path: Path, monkeypatch) -> None:
    """--require-license is threaded through to the check."""
    _pyproject(tmp_path, 'description = "demo"')
    monkeypatch.setattr(clm, "find_repo_root", lambda: tmp_path)
    assert clm.main([]) == 0
    assert clm.main(["--require-license"]) == 1


def test_module_executes_main(tmp_path: Path, monkeypatch) -> None:
    """Module execution calls main and exits with its return value."""
    _pyproject(tmp_path, 'license = "MIT"')
    monkeypatch.setattr(clm, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(clm.sys, "argv", ["check_license_metadata"])

    with patch("rhiza_hooks.check_license_metadata.sys.exit") as mock_exit:
        # The module is already imported (top-level test import), so runpy warns it was
        # "found in sys.modules ... prior to execution"; filter just that warning rather
        # than mutating sys.modules, which would break module identity for the tests above.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=r".*found in sys\.modules.*", category=RuntimeWarning)
            runpy.run_module("rhiza_hooks.check_license_metadata", run_name="__main__")
        mock_exit.assert_called_once_with(0)
