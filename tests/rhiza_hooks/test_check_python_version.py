"""Tests for the check_python_version hook.

Combines unit tests, subprocess-level integration tests, property-based
(Hypothesis) invariants, and a pre-commit end-to-end test for the
``rhiza_hooks.check_python_version`` module.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rhiza_hooks.check_python_version import (
    check_version_consistency,
    find_repo_root,
    get_pyproject_requires_python,
    get_python_version_file,
    main,
    parse_version,
    version_satisfies_constraint,
)

if TYPE_CHECKING:
    from collections.abc import Callable


# ---------------------------------------------------------------------------
# Unit tests: parse_version
# ---------------------------------------------------------------------------
def test_parse_simple_version() -> None:
    """Parse a simple major.minor version."""
    assert parse_version("3.11") == (3, 11)


def test_parse_version_3_12() -> None:
    """Parse version 3.12."""
    assert parse_version("3.12") == (3, 12)


def test_parse_version_with_patch() -> None:
    """Parse version with patch number (only major.minor used)."""
    # Note: our parse_version only handles major.minor
    assert parse_version("3.11") == (3, 11)


@pytest.mark.parametrize("bad", ["", "3", "3.x", "3.11.5", "abc", "3,11"])
def test_parse_version_rejects_invalid(bad: str) -> None:
    """Reject anything that is not exactly 'major.minor'."""
    with pytest.raises(ValueError, match="Invalid version string"):
        parse_version(bad)


# ---------------------------------------------------------------------------
# Unit tests: version_satisfies_constraint
# ---------------------------------------------------------------------------
def test_gte_satisfied() -> None:
    """Version 3.12 satisfies >=3.11."""
    assert version_satisfies_constraint("3.12", ">=", "3.11") is True


def test_gte_exact_match() -> None:
    """Version 3.11 satisfies >=3.11."""
    assert version_satisfies_constraint("3.11", ">=", "3.11") is True


def test_gte_not_satisfied() -> None:
    """Version 3.10 does not satisfy >=3.11."""
    assert version_satisfies_constraint("3.10", ">=", "3.11") is False


def test_gt_satisfied() -> None:
    """Version 3.12 satisfies >3.11."""
    assert version_satisfies_constraint("3.12", ">", "3.11") is True


def test_gt_not_satisfied_equal() -> None:
    """Version 3.11 does not satisfy >3.11."""
    assert version_satisfies_constraint("3.11", ">", "3.11") is False


def test_lte_satisfied() -> None:
    """Version 3.11 satisfies <=3.12."""
    assert version_satisfies_constraint("3.11", "<=", "3.12") is True


def test_lt_satisfied() -> None:
    """Version 3.11 satisfies <3.12."""
    assert version_satisfies_constraint("3.11", "<", "3.12") is True


def test_eq_satisfied() -> None:
    """Version 3.11 satisfies ==3.11."""
    assert version_satisfies_constraint("3.11", "==", "3.11") is True


def test_eq_not_satisfied() -> None:
    """Version 3.12 does not satisfy ==3.11."""
    assert version_satisfies_constraint("3.12", "==", "3.11") is False


def test_ne_satisfied() -> None:
    """Version 3.12 satisfies !=3.11."""
    assert version_satisfies_constraint("3.12", "!=", "3.11") is True


def test_ne_not_satisfied() -> None:
    """Version 3.11 does not satisfy !=3.11."""
    assert version_satisfies_constraint("3.11", "!=", "3.11") is False


def test_compatible_release_satisfied() -> None:
    """Version 3.12 satisfies ~=3.11 (same major)."""
    assert version_satisfies_constraint("3.12", "~=", "3.11") is True


def test_compatible_release_not_satisfied() -> None:
    """Version 4.0 does not satisfy ~=3.11 (different major)."""
    assert version_satisfies_constraint("4.0", "~=", "3.11") is False


def test_compatible_release_lower_not_satisfied() -> None:
    """Version 3.10 does not satisfy ~=3.11."""
    assert version_satisfies_constraint("3.10", "~=", "3.11") is False


def test_unknown_operator_returns_true() -> None:
    """Unknown operator is permissive and returns True."""
    assert version_satisfies_constraint("3.12", "???", "3.11") is True


def test_lte_exact_match_is_true() -> None:
    """<= is inclusive: 3.11 <= 3.11 holds (distinguishes <= from <)."""
    assert version_satisfies_constraint("3.11", "<=", "3.11") is True


def test_lte_above_is_false() -> None:
    """3.12 does not satisfy <=3.11 (pins the '<=' operator branch)."""
    assert version_satisfies_constraint("3.12", "<=", "3.11") is False


def test_lt_exact_match_is_false() -> None:
    """< is exclusive: 3.11 < 3.11 is false (distinguishes < from <=)."""
    assert version_satisfies_constraint("3.11", "<", "3.11") is False


def test_lt_above_is_false() -> None:
    """3.12 does not satisfy <3.11 (pins the '<' operator branch)."""
    assert version_satisfies_constraint("3.12", "<", "3.11") is False


def test_empty_operator_unequal_is_false() -> None:
    """Empty operator means equality: 3.10 does not equal 3.11 (pins the '' branch)."""
    assert version_satisfies_constraint("3.10", "", "3.11") is False


def test_compatible_release_exact_match_is_true() -> None:
    """~= is inclusive of the floor: 3.11 satisfies ~=3.11 (pins '>=' inside ~=)."""
    assert version_satisfies_constraint("3.11", "~=", "3.11") is True


# ---------------------------------------------------------------------------
# Unit tests: get_python_version_file
# ---------------------------------------------------------------------------
def test_reads_version(tmp_path: Path) -> None:
    """Reads version from .python-version file."""
    (tmp_path / ".python-version").write_text("3.12\n")
    assert get_python_version_file(tmp_path) == "3.12"


def test_extracts_major_minor(tmp_path: Path) -> None:
    """Extracts major.minor from full version."""
    (tmp_path / ".python-version").write_text("3.12.1\n")
    assert get_python_version_file(tmp_path) == "3.12"


def test_missing_file_returns_none(tmp_path: Path) -> None:
    """Returns None if file doesn't exist."""
    assert get_python_version_file(tmp_path) is None


# ---------------------------------------------------------------------------
# Unit tests: get_pyproject_requires_python
# ---------------------------------------------------------------------------
def test_parses_gte_constraint(tmp_path: Path) -> None:
    """Parses >=3.11 constraint into a single clause."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nrequires-python = ">=3.11"\n')
    assert get_pyproject_requires_python(tmp_path) == [(">=", "3.11")]


def test_parses_eq_constraint(tmp_path: Path) -> None:
    """Parses ==3.12 constraint into a single clause."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nrequires-python = "==3.12"\n')
    assert get_pyproject_requires_python(tmp_path) == [("==", "3.12")]


def test_parses_compatible_release(tmp_path: Path) -> None:
    """Parses ~=3.11 constraint into a single clause."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nrequires-python = "~=3.11"\n')
    assert get_pyproject_requires_python(tmp_path) == [("~=", "3.11")]


def test_bare_version_defaults_to_equality_operator(tmp_path: Path) -> None:
    """A bare version with no operator defaults to '==' (pins the default literal)."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nrequires-python = "3.11"\n')
    assert get_pyproject_requires_python(tmp_path) == [("==", "3.11")]


def test_parses_compound_specifier(tmp_path: Path) -> None:
    """A compound specifier yields one clause per comma-separated part, in order."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nrequires-python = ">=3.11,<3.14"\n')
    assert get_pyproject_requires_python(tmp_path) == [(">=", "3.11"), ("<", "3.14")]


def test_compound_specifier_skips_unparseable_clause(tmp_path: Path) -> None:
    """An unparseable clause is skipped (not a stop) so a later valid clause is still kept.

    The bad clause is placed *first* so this distinguishes ``continue`` (skip and
    keep scanning) from ``break`` (abandon the rest).
    """
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nrequires-python = "invalid,>=3.11"\n')
    assert get_pyproject_requires_python(tmp_path) == [(">=", "3.11")]


def test_get_pyproject_requires_python_missing_file_returns_none(tmp_path: Path) -> None:
    """Returns None if file doesn't exist."""
    assert get_pyproject_requires_python(tmp_path) is None


def test_missing_requires_python_returns_none(tmp_path: Path) -> None:
    """Returns None if requires-python not specified."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "test"\n')
    assert get_pyproject_requires_python(tmp_path) is None


def test_invalid_toml_returns_none(tmp_path: Path) -> None:
    """Returns None if pyproject.toml is invalid."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("this is not valid toml {{{{")
    assert get_pyproject_requires_python(tmp_path) is None


def test_invalid_version_format_returns_none(tmp_path: Path) -> None:
    """Returns None if requires-python has invalid format."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nrequires-python = "invalid-version"\n')
    assert get_pyproject_requires_python(tmp_path) is None


def test_unreadable_file_returns_none(tmp_path: Path) -> None:
    """An OSError opening pyproject.toml (e.g. it is a directory) is treated as unspecified."""
    # A directory at the expected path exists() == True but raises OSError on open().
    (tmp_path / "pyproject.toml").mkdir()
    assert get_pyproject_requires_python(tmp_path) is None


def test_unexpected_error_propagates(tmp_path: Path) -> None:
    """Errors other than TOMLDecodeError/OSError are no longer swallowed (issue #174)."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nrequires-python = ">=3.11"\n')

    def boom(_f: object) -> None:
        """Raise a RuntimeError to simulate an unexpected tomllib failure."""
        raise RuntimeError("unexpected")

    with (
        patch("rhiza_hooks.check_python_version.tomllib.load", side_effect=boom),
        pytest.raises(RuntimeError, match="unexpected"),
    ):
        get_pyproject_requires_python(tmp_path)


# ---------------------------------------------------------------------------
# Unit tests: check_version_consistency
# ---------------------------------------------------------------------------
def test_gte_constraint_satisfied(tmp_path: Path) -> None:
    """No error when .python-version satisfies >=constraint."""
    (tmp_path / ".python-version").write_text("3.12\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')

    errors = check_version_consistency(tmp_path)

    assert errors == []


def test_gte_constraint_exact_match(tmp_path: Path) -> None:
    """No error when .python-version equals minimum."""
    (tmp_path / ".python-version").write_text("3.11\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')

    errors = check_version_consistency(tmp_path)

    assert errors == []


def test_gte_constraint_not_satisfied(tmp_path: Path) -> None:
    """Error when .python-version is below minimum."""
    (tmp_path / ".python-version").write_text("3.10\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')

    errors = check_version_consistency(tmp_path)

    # Exact match pins both halves of the mismatch message.
    assert errors == ["Python version mismatch: .python-version has 3.10, but pyproject.toml requires-python is >=3.11"]


def test_eq_constraint_not_satisfied(tmp_path: Path) -> None:
    """Error when .python-version doesn't match exact constraint."""
    (tmp_path / ".python-version").write_text("3.12\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = "==3.11"\n')

    errors = check_version_consistency(tmp_path)

    assert len(errors) == 1


def test_compound_specifier_satisfied(tmp_path: Path) -> None:
    """No error when .python-version satisfies every clause of a compound specifier."""
    (tmp_path / ".python-version").write_text("3.12\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11,<3.14"\n')

    errors = check_version_consistency(tmp_path)

    assert errors == []


def test_compound_specifier_upper_bound_violated(tmp_path: Path) -> None:
    """Error when an upper-bound clause is violated even though the lower bound holds.

    Pins the per-clause check (3.14 satisfies >=3.11 but not <3.14) and the
    comma-joined constraint string in the message.
    """
    (tmp_path / ".python-version").write_text("3.14\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11,<3.14"\n')

    errors = check_version_consistency(tmp_path)

    assert errors == [
        "Python version mismatch: .python-version has 3.14, but pyproject.toml requires-python is >=3.11,<3.14"
    ]


def test_no_python_version_file(tmp_path: Path) -> None:
    """No error when .python-version doesn't exist."""
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')

    errors = check_version_consistency(tmp_path)

    assert errors == []


def test_no_pyproject(tmp_path: Path) -> None:
    """No error when pyproject.toml doesn't exist."""
    (tmp_path / ".python-version").write_text("3.12\n")

    errors = check_version_consistency(tmp_path)

    assert errors == []


def test_neither_file_exists(tmp_path: Path) -> None:
    """No error when neither file exists."""
    errors = check_version_consistency(tmp_path)

    assert errors == []


# ---------------------------------------------------------------------------
# Unit tests: find_repo_root
# ---------------------------------------------------------------------------
def test_finds_git_dir(tmp_path: Path) -> None:
    """Returns directory containing .git."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    subdir = tmp_path / "src" / "package"
    subdir.mkdir(parents=True)

    with patch("rhiza_hooks.check_python_version.Path.cwd", return_value=subdir):
        result = find_repo_root()
        assert result == tmp_path


def test_no_git_dir_returns_cwd(tmp_path: Path) -> None:
    """Returns cwd when no .git found."""
    subdir = tmp_path / "src" / "package"
    subdir.mkdir(parents=True)

    with patch("rhiza_hooks.check_python_version.Path.cwd", return_value=subdir):
        result = find_repo_root()
        assert result == subdir


# ---------------------------------------------------------------------------
# Unit tests: main
# ---------------------------------------------------------------------------
def test_main_consistent_returns_zero(tmp_path: Path) -> None:
    """Returns 0 when versions are consistent."""
    (tmp_path / ".python-version").write_text("3.12\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / ".git").mkdir()

    with patch("rhiza_hooks.check_python_version.find_repo_root", return_value=tmp_path):
        result = main([])
        assert result == 0


def test_main_inconsistent_returns_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Returns 1 when versions are inconsistent."""
    (tmp_path / ".python-version").write_text("3.10\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / ".git").mkdir()

    with patch("rhiza_hooks.check_python_version.find_repo_root", return_value=tmp_path):
        result = main([])
        assert result == 1
        captured = capsys.readouterr()
        # Exact stdout pins the "ERROR: {error}" print format.
        assert captured.out == (
            "ERROR: Python version mismatch: .python-version has 3.10, but pyproject.toml requires-python is >=3.11\n"
        )


def test_main_no_files_returns_zero(tmp_path: Path) -> None:
    """Returns 0 when no version files exist."""
    (tmp_path / ".git").mkdir()

    with patch("rhiza_hooks.check_python_version.find_repo_root", return_value=tmp_path):
        result = main([])
        assert result == 0


def test_main_accepts_filenames_argument(tmp_path: Path) -> None:
    """Main accepts filenames argument (ignored)."""
    (tmp_path / ".git").mkdir()

    with patch("rhiza_hooks.check_python_version.find_repo_root", return_value=tmp_path):
        result = main(["some_file.py", "another.py"])
        assert result == 0


def test_unknown_flag_exits() -> None:
    """An unknown flag is parsed and rejected (pins parse_args, not a no-op)."""
    with pytest.raises(SystemExit):
        main(["--definitely-not-a-flag"])


def test_help_text(capsys: pytest.CaptureFixture[str]) -> None:
    """--help renders the exact argparse description, arg name, and help strings."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "XX" not in out  # no mutated literal survived into the rendered help
    assert "Check Python version consistency" in out
    assert "Filenames (ignored, checks repo root)" in out
    assert "filenames" in out


# ---------------------------------------------------------------------------
# Unit tests: module execution via if __name__ == '__main__'
# ---------------------------------------------------------------------------
def test_module_executes_main(tmp_path: Path) -> None:
    """Module execution calls main and exits with its return value."""
    (tmp_path / ".git").mkdir()

    with (
        patch("rhiza_hooks.check_python_version.find_repo_root", return_value=tmp_path),
        patch("rhiza_hooks.check_python_version.sys.argv", ["check_python_version"]),
        patch("rhiza_hooks.check_python_version.sys.exit") as mock_exit,
    ):
        import runpy
        import warnings

        # The module is already imported (top-level test import), so runpy warns
        # it was "found in sys.modules ... prior to execution"; filter just that
        # warning rather than mutating sys.modules, which would break module
        # identity for other tests that monkeypatch this module.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=r".*found in sys\.modules.*", category=RuntimeWarning)
            runpy.run_module("rhiza_hooks.check_python_version", run_name="__main__")
        mock_exit.assert_called_once_with(0)


# ---------------------------------------------------------------------------
# Subprocess-level integration tests
# ---------------------------------------------------------------------------
def test_consistent_versions(mock_project: Callable[[dict[str, str]], Path]) -> None:
    """Test with consistent Python versions."""
    pyproject = """
[project]
requires-python = ">=3.11"
"""
    project = mock_project(
        {
            ".python-version": "3.11\n",
            "pyproject.toml": pyproject,
        }
    )

    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "rhiza_hooks.check_python_version"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


def test_inconsistent_versions(mock_project: Callable[[dict[str, str]], Path]) -> None:
    """Test with inconsistent Python versions."""
    pyproject = """
[project]
requires-python = ">=3.11"
"""
    project = mock_project(
        {
            ".python-version": "3.10\n",
            "pyproject.toml": pyproject,
        }
    )

    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "rhiza_hooks.check_python_version"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1


def test_check_python_version_on_project(project_root: Path) -> None:
    """Test check-python-version-consistency on actual project."""
    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "rhiza_hooks.check_python_version"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    # Project should have consistent Python versions
    assert result.returncode == 0


def test_module_is_importable() -> None:
    """Test that the module is importable."""
    result = subprocess.run(  # nosec B603
        [sys.executable, "-c", "import rhiza_hooks.check_python_version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Failed to import rhiza_hooks.check_python_version: {result.stderr}"


def test_module_has_main_function() -> None:
    """Test that the module has a main function."""
    result = subprocess.run(  # nosec B603
        [
            sys.executable,
            "-c",
            "import rhiza_hooks.check_python_version; assert hasattr(rhiza_hooks.check_python_version, 'main')",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, "Module rhiza_hooks.check_python_version has no main function"


def test_module_handles_nonexistent_directory(tmp_path: Path) -> None:
    """Test that the module handles nonexistent directories gracefully."""
    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "rhiza_hooks.check_python_version"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    # Script should not crash
    assert result.returncode in (0, 1)


def test_module_python_importable() -> None:
    """Test that the module is importable."""
    result = subprocess.run(  # nosec B603
        [sys.executable, "-c", "import rhiza_hooks.check_python_version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Failed to import rhiza_hooks.check_python_version: {result.stderr}"


# ---------------------------------------------------------------------------
# Property-based tests (Hypothesis)
# ---------------------------------------------------------------------------
# Version components kept small but representative; the helpers only ever compare
# (major, minor) tuples, so the exact magnitude is irrelevant to the invariants.
_components = st.integers(min_value=0, max_value=99)


def _version_str(major: int, minor: int) -> str:
    """Format a (major, minor) pair as a dotted version string."""
    return f"{major}.{minor}"


@given(_components, _components)
def test_property_parse_version_roundtrip(major: int, minor: int) -> None:
    """Formatting a (major, minor) pair and parsing it returns the pair."""
    assert parse_version(_version_str(major, minor)) == (major, minor)


@given(_components, _components, _components, _components)
def test_property_ge_is_mirror_of_le(a_maj: int, a_min: int, b_maj: int, b_min: int) -> None:
    """Mirror identity: a >= b holds exactly when b <= a."""
    a, b = _version_str(a_maj, a_min), _version_str(b_maj, b_min)
    assert version_satisfies_constraint(a, ">=", b) == version_satisfies_constraint(b, "<=", a)


@given(_components, _components, _components, _components)
def test_property_gt_is_mirror_of_lt(a_maj: int, a_min: int, b_maj: int, b_min: int) -> None:
    """Mirror identity: a > b holds exactly when b < a."""
    a, b = _version_str(a_maj, a_min), _version_str(b_maj, b_min)
    assert version_satisfies_constraint(a, ">", b) == version_satisfies_constraint(b, "<", a)


@given(_components, _components, _components, _components)
def test_property_ge_negates_lt(a_maj: int, a_min: int, b_maj: int, b_min: int) -> None:
    """Total order: a >= b is exactly the negation of a < b."""
    a, b = _version_str(a_maj, a_min), _version_str(b_maj, b_min)
    assert version_satisfies_constraint(a, ">=", b) != version_satisfies_constraint(a, "<", b)


@given(_components, _components, _components, _components)
def test_property_eq_negates_ne(a_maj: int, a_min: int, b_maj: int, b_min: int) -> None:
    """Equality is exactly the negation of inequality (== versus !=)."""
    a, b = _version_str(a_maj, a_min), _version_str(b_maj, b_min)
    assert version_satisfies_constraint(a, "==", b) != version_satisfies_constraint(a, "!=", b)


@given(_components, _components)
def test_property_empty_operator_means_equality(major: int, minor: int) -> None:
    """An empty operator behaves like '==' (documented default)."""
    v = _version_str(major, minor)
    assert version_satisfies_constraint(v, "", v) is True


@given(_components, _components, _components, _components)
def test_property_compatible_release_implies_lower_bound(a_maj: int, a_min: int, b_maj: int, b_min: int) -> None:
    """Compatible-release ~= refines >=: it never accepts what >= rejects."""
    a, b = _version_str(a_maj, a_min), _version_str(b_maj, b_min)
    if version_satisfies_constraint(a, "~=", b):
        assert version_satisfies_constraint(a, ">=", b)
        assert a_maj == b_maj


@given(_components, _components, _components, _components)
def test_property_unknown_operator_is_permissive(a_maj: int, a_min: int, b_maj: int, b_min: int) -> None:
    """Unrecognised operators are accepted permissively (documented behaviour)."""
    a, b = _version_str(a_maj, a_min), _version_str(b_maj, b_min)
    assert version_satisfies_constraint(a, "?!", b) is True


# ---------------------------------------------------------------------------
# End-to-end test through pre-commit (issue #184)
# ---------------------------------------------------------------------------
# Phrases that indicate pre-commit itself could not run the hook environment
# (network, build backend, resolver, or an internal pre-commit crash) rather
# than a genuine wiring failure. When any appears we skip instead of failing,
# so a hostile environment does not break CI.
_ENV_FAILURE_MARKERS = (
    "InstallError",
    "Failed to install",
    "Could not install",
    "ResolutionImpossible",
    "Connection",
    "Temporary failure in name resolution",
    "Network is unreachable",
    "ReadTimeoutError",
    "SSLError",
    # pre-commit's generic banner for an internal crash (exit code 3). It is
    # printed for environment problems, never for hook-wiring errors (those get
    # clean messages like "No hook with id ..."). The most common offender is
    # GitHub's Windows runner, where the workspace (D:) and the pre-commit cache
    # (C:) sit on different drives: `ValueError: path is on mount 'D:', start on
    # mount 'C:'`.
    "An unexpected error has occurred",
    "path is on mount",
)

# A self-contained hook with no network use and ``pass_filenames: false`` /
# ``always_run: true`` — ideal for a deterministic end-to-end run.
_HOOK_ID = "check-python-version-consistency"


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command, capturing text output, with a generous timeout."""
    return subprocess.run(  # nosec B603
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


@pytest.mark.timeout(600)
def test_hook_runs_through_pre_commit_try_repo(project_root: Path, tmp_path: Path) -> None:
    """`pre-commit try-repo` builds this repo's hooks and runs one successfully.

    Proves the ``.pre-commit-hooks.yaml`` entry resolves to the installed
    ``[project.scripts]`` console script end to end.
    """
    if shutil.which("git") is None:
        pytest.skip("git is required for the end-to-end test")

    # A throwaway git repo with versions that the hook considers consistent, so a
    # correctly wired hook must exit 0.
    (tmp_path / ".python-version").write_text("3.11\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "e2e"\nrequires-python = ">=3.11"\n')

    init = _run(["git", "init"], cwd=tmp_path)
    assert init.returncode == 0, init.stderr
    # try-repo / --all-files operate on tracked files.
    _run(["git", "add", "-A"], cwd=tmp_path)

    # Prefer the installed console entry point; fall back to `python -m pre_commit`.
    if shutil.which("pre-commit") is not None:
        base = ["pre-commit"]
    elif importlib.util.find_spec("pre_commit") is not None:
        base = [sys.executable, "-m", "pre_commit"]
    else:
        pytest.skip("pre-commit is required for the end-to-end test")

    try:
        result = _run(
            [*base, "try-repo", str(project_root), _HOOK_ID, "--all-files", "--verbose"],
            cwd=tmp_path,
        )
    except FileNotFoundError:
        pytest.skip("pre-commit is not installed")
    except subprocess.TimeoutExpired:
        pytest.skip("pre-commit try-repo timed out (slow/no network for the isolated build)")

    combined = f"{result.stdout}\n{result.stderr}"

    if result.returncode != 0 and any(marker in combined for marker in _ENV_FAILURE_MARKERS):
        pytest.skip(f"pre-commit could not build the hook environment:\n{combined}")

    # A clean run proves the wiring: pre-commit found the hook in the manifest,
    # installed the console script from [project.scripts], and ran it to success.
    assert result.returncode == 0, f"try-repo failed:\n{combined}"
    assert _HOOK_ID in combined or "Check Python version consistency" in combined, combined
