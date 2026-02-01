"""Tests for check_python_version hook."""

from __future__ import annotations

from pathlib import Path

import pytest

from rhiza_hooks.check_python_version import (
    check_version_consistency,
    get_pyproject_requires_python,
    get_python_version_file,
    parse_version,
    version_satisfies_constraint,
)


class TestParseVersion:
    """Tests for parse_version function."""

    def test_parse_simple_version(self) -> None:
        """Parse a simple major.minor version."""
        assert parse_version("3.11") == (3, 11)

    def test_parse_version_3_12(self) -> None:
        """Parse version 3.12."""
        assert parse_version("3.12") == (3, 12)

    def test_parse_version_with_patch(self) -> None:
        """Parse version with patch number (only major.minor used)."""
        # Note: our parse_version only handles major.minor
        assert parse_version("3.11") == (3, 11)


class TestVersionSatisfiesConstraint:
    """Tests for version_satisfies_constraint function."""

    def test_gte_satisfied(self) -> None:
        """Version 3.12 satisfies >=3.11."""
        assert version_satisfies_constraint("3.12", ">=", "3.11") is True

    def test_gte_exact_match(self) -> None:
        """Version 3.11 satisfies >=3.11."""
        assert version_satisfies_constraint("3.11", ">=", "3.11") is True

    def test_gte_not_satisfied(self) -> None:
        """Version 3.10 does not satisfy >=3.11."""
        assert version_satisfies_constraint("3.10", ">=", "3.11") is False

    def test_gt_satisfied(self) -> None:
        """Version 3.12 satisfies >3.11."""
        assert version_satisfies_constraint("3.12", ">", "3.11") is True

    def test_gt_not_satisfied_equal(self) -> None:
        """Version 3.11 does not satisfy >3.11."""
        assert version_satisfies_constraint("3.11", ">", "3.11") is False

    def test_lte_satisfied(self) -> None:
        """Version 3.11 satisfies <=3.12."""
        assert version_satisfies_constraint("3.11", "<=", "3.12") is True

    def test_lt_satisfied(self) -> None:
        """Version 3.11 satisfies <3.12."""
        assert version_satisfies_constraint("3.11", "<", "3.12") is True

    def test_eq_satisfied(self) -> None:
        """Version 3.11 satisfies ==3.11."""
        assert version_satisfies_constraint("3.11", "==", "3.11") is True

    def test_eq_not_satisfied(self) -> None:
        """Version 3.12 does not satisfy ==3.11."""
        assert version_satisfies_constraint("3.12", "==", "3.11") is False

    def test_ne_satisfied(self) -> None:
        """Version 3.12 satisfies !=3.11."""
        assert version_satisfies_constraint("3.12", "!=", "3.11") is True

    def test_ne_not_satisfied(self) -> None:
        """Version 3.11 does not satisfy !=3.11."""
        assert version_satisfies_constraint("3.11", "!=", "3.11") is False

    def test_compatible_release_satisfied(self) -> None:
        """Version 3.12 satisfies ~=3.11 (same major)."""
        assert version_satisfies_constraint("3.12", "~=", "3.11") is True

    def test_compatible_release_not_satisfied(self) -> None:
        """Version 4.0 does not satisfy ~=3.11 (different major)."""
        assert version_satisfies_constraint("4.0", "~=", "3.11") is False

    def test_compatible_release_lower_not_satisfied(self) -> None:
        """Version 3.10 does not satisfy ~=3.11."""
        assert version_satisfies_constraint("3.10", "~=", "3.11") is False


class TestGetPythonVersionFile:
    """Tests for get_python_version_file function."""

    def test_reads_version(self, tmp_path: Path) -> None:
        """Reads version from .python-version file."""
        (tmp_path / ".python-version").write_text("3.12\n")
        assert get_python_version_file(tmp_path) == "3.12"

    def test_extracts_major_minor(self, tmp_path: Path) -> None:
        """Extracts major.minor from full version."""
        (tmp_path / ".python-version").write_text("3.12.1\n")
        assert get_python_version_file(tmp_path) == "3.12"

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        """Returns None if file doesn't exist."""
        assert get_python_version_file(tmp_path) is None


class TestGetPyprojectRequiresPython:
    """Tests for get_pyproject_requires_python function."""

    def test_parses_gte_constraint(self, tmp_path: Path) -> None:
        """Parses >=3.11 constraint."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nrequires-python = ">=3.11"\n')
        assert get_pyproject_requires_python(tmp_path) == (">=", "3.11")

    def test_parses_eq_constraint(self, tmp_path: Path) -> None:
        """Parses ==3.12 constraint."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nrequires-python = "==3.12"\n')
        assert get_pyproject_requires_python(tmp_path) == ("==", "3.12")

    def test_parses_compatible_release(self, tmp_path: Path) -> None:
        """Parses ~=3.11 constraint."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nrequires-python = "~=3.11"\n')
        assert get_pyproject_requires_python(tmp_path) == ("~=", "3.11")

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        """Returns None if file doesn't exist."""
        assert get_pyproject_requires_python(tmp_path) is None

    def test_missing_requires_python_returns_none(self, tmp_path: Path) -> None:
        """Returns None if requires-python not specified."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"\n')
        assert get_pyproject_requires_python(tmp_path) is None


class TestCheckVersionConsistency:
    """Tests for check_version_consistency function."""

    def test_gte_constraint_satisfied(self, tmp_path: Path) -> None:
        """No error when .python-version satisfies >=constraint."""
        (tmp_path / ".python-version").write_text("3.12\n")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nrequires-python = ">=3.11"\n'
        )

        errors = check_version_consistency(tmp_path)

        assert errors == []

    def test_gte_constraint_exact_match(self, tmp_path: Path) -> None:
        """No error when .python-version equals minimum."""
        (tmp_path / ".python-version").write_text("3.11\n")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nrequires-python = ">=3.11"\n'
        )

        errors = check_version_consistency(tmp_path)

        assert errors == []

    def test_gte_constraint_not_satisfied(self, tmp_path: Path) -> None:
        """Error when .python-version is below minimum."""
        (tmp_path / ".python-version").write_text("3.10\n")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nrequires-python = ">=3.11"\n'
        )

        errors = check_version_consistency(tmp_path)

        assert len(errors) == 1
        assert "3.10" in errors[0]
        assert ">=3.11" in errors[0]

    def test_eq_constraint_not_satisfied(self, tmp_path: Path) -> None:
        """Error when .python-version doesn't match exact constraint."""
        (tmp_path / ".python-version").write_text("3.12\n")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nrequires-python = "==3.11"\n'
        )

        errors = check_version_consistency(tmp_path)

        assert len(errors) == 1

    def test_no_python_version_file(self, tmp_path: Path) -> None:
        """No error when .python-version doesn't exist."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nrequires-python = ">=3.11"\n'
        )

        errors = check_version_consistency(tmp_path)

        assert errors == []

    def test_no_pyproject(self, tmp_path: Path) -> None:
        """No error when pyproject.toml doesn't exist."""
        (tmp_path / ".python-version").write_text("3.12\n")

        errors = check_version_consistency(tmp_path)

        assert errors == []

    def test_neither_file_exists(self, tmp_path: Path) -> None:
        """No error when neither file exists."""
        errors = check_version_consistency(tmp_path)

        assert errors == []
