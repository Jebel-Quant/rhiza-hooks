"""Tests for the check_bumpversion_config hook.

Combines unit tests, subprocess-level integration tests and property-based
(Hypothesis) invariants for the ``rhiza_hooks.check_bumpversion_config`` module.
"""

from __future__ import annotations

import subprocess  # nosec B404
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rhiza_hooks.check_bumpversion_config import (
    _load_ini,
    _load_toml,
    check_bumpversion_config,
    find_discoverable_config,
    has_undiscovered_config,
    main,
    read_project_version,
)


def _write(root: Path, name: str, body: str) -> Path:
    """Write *body* to ``root/name``, creating parent directories."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


PYPROJECT = '[project]\nname = "demo"\nversion = "1.2.3"\n'
BUMP_TABLE = "\n[tool.bumpversion]\nallow_dirty = false\n"


# ---------------------------------------------------------------------------
# read_project_version
# ---------------------------------------------------------------------------
def test_reads_static_version(tmp_path: Path) -> None:
    """A static [project].version is returned verbatim."""
    _write(tmp_path, "pyproject.toml", PYPROJECT)
    assert read_project_version(tmp_path) == "1.2.3"


def test_missing_pyproject_reads_none(tmp_path: Path) -> None:
    """No pyproject.toml at all yields None."""
    assert read_project_version(tmp_path) is None


def test_missing_project_table_reads_none(tmp_path: Path) -> None:
    """A pyproject.toml without a [project] table yields None."""
    _write(tmp_path, "pyproject.toml", "[tool.black]\nline-length = 100\n")
    assert read_project_version(tmp_path) is None


def test_project_not_a_table_reads_none(tmp_path: Path) -> None:
    """A [project] key that is not a table yields None rather than raising."""
    _write(tmp_path, "pyproject.toml", 'project = "oops"\n')
    assert read_project_version(tmp_path) is None


def test_dynamic_version_reads_none(tmp_path: Path) -> None:
    """A dynamic version has no static string to compare against."""
    _write(tmp_path, "pyproject.toml", '[project]\nname = "demo"\ndynamic = ["version"]\n')
    assert read_project_version(tmp_path) is None


def test_non_string_version_reads_none(tmp_path: Path) -> None:
    """A non-string version is ignored rather than coerced."""
    _write(tmp_path, "pyproject.toml", "[project]\nversion = 3\n")
    assert read_project_version(tmp_path) is None


def test_malformed_toml_reads_none(tmp_path: Path) -> None:
    """Malformed TOML is treated as absent, not raised."""
    _write(tmp_path, "pyproject.toml", "[project\nversion =")
    assert read_project_version(tmp_path) is None


def test_unreadable_toml_reads_none(tmp_path: Path) -> None:
    """An OSError while opening is treated as absent."""
    _write(tmp_path, "pyproject.toml", PYPROJECT)
    with patch("pathlib.Path.open", side_effect=OSError("boom")):
        assert _load_toml(tmp_path / "pyproject.toml") is None


# ---------------------------------------------------------------------------
# find_discoverable_config
# ---------------------------------------------------------------------------
def test_finds_pyproject_tool_table(tmp_path: Path) -> None:
    """[tool.bumpversion] in pyproject.toml is discoverable."""
    _write(tmp_path, "pyproject.toml", PYPROJECT + BUMP_TABLE)
    assert find_discoverable_config(tmp_path) == ("pyproject.toml", None)


def test_finds_declared_current_version(tmp_path: Path) -> None:
    """A declared current_version is returned alongside the filename."""
    _write(tmp_path, "pyproject.toml", PYPROJECT + BUMP_TABLE + 'current_version = "1.2.3"\n')
    assert find_discoverable_config(tmp_path) == ("pyproject.toml", "1.2.3")


def test_non_string_current_version_reads_none(tmp_path: Path) -> None:
    """A non-string current_version is reported as absent."""
    _write(tmp_path, "pyproject.toml", PYPROJECT + BUMP_TABLE + "current_version = 123\n")
    assert find_discoverable_config(tmp_path) == ("pyproject.toml", None)


def test_bumpversion_toml_wins_over_pyproject(tmp_path: Path) -> None:
    """.bumpversion.toml is searched before pyproject.toml."""
    _write(tmp_path, "pyproject.toml", PYPROJECT + BUMP_TABLE + 'current_version = "9.9.9"\n')
    _write(tmp_path, ".bumpversion.toml", '[tool.bumpversion]\ncurrent_version = "1.2.3"\n')
    assert find_discoverable_config(tmp_path) == (".bumpversion.toml", "1.2.3")


def test_top_level_bumpversion_section(tmp_path: Path) -> None:
    """A top-level [bumpversion] table (not nested under [tool]) is accepted."""
    _write(tmp_path, ".bumpversion.toml", '[bumpversion]\ncurrent_version = "1.2.3"\n')
    assert find_discoverable_config(tmp_path) == (".bumpversion.toml", "1.2.3")


def test_tool_table_without_bumpversion_is_skipped(tmp_path: Path) -> None:
    """A [tool] table lacking a bumpversion section does not count as a config."""
    _write(tmp_path, "pyproject.toml", PYPROJECT + "\n[tool.ruff]\nline-length = 100\n")
    assert find_discoverable_config(tmp_path) is None


def test_tool_not_a_table_is_skipped(tmp_path: Path) -> None:
    """A [tool] key that is not a table does not crash the search."""
    _write(tmp_path, "pyproject.toml", 'tool = "oops"\n')
    assert find_discoverable_config(tmp_path) is None


def test_bumpversion_section_not_a_table_is_skipped(tmp_path: Path) -> None:
    """A bumpversion key that is not a table is not a usable config."""
    _write(tmp_path, "pyproject.toml", '[tool]\nbumpversion = "oops"\n')
    assert find_discoverable_config(tmp_path) is None


def test_finds_setup_cfg_section(tmp_path: Path) -> None:
    """A [bumpversion] section in setup.cfg is discoverable."""
    _write(tmp_path, "setup.cfg", "[bumpversion]\ncurrent_version = 1.2.3\n")
    assert find_discoverable_config(tmp_path) == ("setup.cfg", "1.2.3")


def test_finds_bumpversion_cfg_without_current_version(tmp_path: Path) -> None:
    """An INI config lacking current_version reports None for it."""
    _write(tmp_path, ".bumpversion.cfg", "[bumpversion]\ntag = True\n")
    assert find_discoverable_config(tmp_path) == (".bumpversion.cfg", None)


def test_setup_cfg_without_bumpversion_section_is_skipped(tmp_path: Path) -> None:
    """An unrelated setup.cfg does not count as a bumpversion config."""
    _write(tmp_path, "setup.cfg", "[metadata]\nname = demo\n")
    assert find_discoverable_config(tmp_path) is None


def test_malformed_ini_is_skipped(tmp_path: Path) -> None:
    """Malformed INI is treated as absent, not raised."""
    _write(tmp_path, "setup.cfg", "not an ini at all\n= = =\n")
    assert find_discoverable_config(tmp_path) is None


def test_missing_ini_reads_none(tmp_path: Path) -> None:
    """A missing INI file yields None from the loader."""
    assert _load_ini(tmp_path / "setup.cfg") is None


def test_unreadable_ini_reads_none(tmp_path: Path) -> None:
    """An OSError while reading an INI file is treated as absent."""
    _write(tmp_path, "setup.cfg", "[bumpversion]\n")
    with patch("configparser.ConfigParser.read", side_effect=OSError("boom")):
        assert _load_ini(tmp_path / "setup.cfg") is None


def test_no_config_anywhere(tmp_path: Path) -> None:
    """An empty tree has no discoverable config."""
    assert find_discoverable_config(tmp_path) is None


# ---------------------------------------------------------------------------
# has_undiscovered_config
# ---------------------------------------------------------------------------
def test_detects_rhiza_cfg_toml(tmp_path: Path) -> None:
    """The rhiza .cfg.toml trap is detected."""
    _write(tmp_path, ".rhiza/.cfg.toml", "[tool.bumpversion]\ntag = true\n")
    assert has_undiscovered_config(tmp_path) is True


def test_absent_rhiza_cfg_toml(tmp_path: Path) -> None:
    """No .rhiza/.cfg.toml means nothing undiscovered."""
    assert has_undiscovered_config(tmp_path) is False


def test_rhiza_cfg_toml_without_bumpversion(tmp_path: Path) -> None:
    """A .cfg.toml carrying other tool config is not the trap."""
    _write(tmp_path, ".rhiza/.cfg.toml", "[tool.other]\nkey = 1\n")
    assert has_undiscovered_config(tmp_path) is False


def test_rhiza_cfg_toml_tool_not_a_table(tmp_path: Path) -> None:
    """A non-table [tool] key in .cfg.toml is handled."""
    _write(tmp_path, ".rhiza/.cfg.toml", 'tool = "oops"\n')
    assert has_undiscovered_config(tmp_path) is False


# ---------------------------------------------------------------------------
# check_bumpversion_config
# ---------------------------------------------------------------------------
def test_sound_config_passes(tmp_path: Path) -> None:
    """A discoverable config with no current_version is accepted."""
    _write(tmp_path, "pyproject.toml", PYPROJECT + BUMP_TABLE)
    assert check_bumpversion_config(tmp_path) == []


def test_matching_current_version_passes(tmp_path: Path) -> None:
    """A current_version equal to [project].version is accepted."""
    _write(tmp_path, "pyproject.toml", PYPROJECT + BUMP_TABLE + 'current_version = "1.2.3"\n')
    assert check_bumpversion_config(tmp_path) == []


def test_no_project_version_skips(tmp_path: Path) -> None:
    """A project with no static version is out of scope."""
    _write(tmp_path, "pyproject.toml", '[project]\nname = "demo"\ndynamic = ["version"]\n')
    assert check_bumpversion_config(tmp_path) == []


def test_missing_config_is_an_error(tmp_path: Path) -> None:
    """A versioned project with no discoverable config fails."""
    _write(tmp_path, "pyproject.toml", PYPROJECT)
    (error,) = check_bumpversion_config(tmp_path)
    assert "no bumpversion config was found" in error
    assert "git describe" in error
    assert ".rhiza" not in error


def test_missing_config_names_the_rhiza_trap(tmp_path: Path) -> None:
    """When the inert rhiza config is present, the error points at it."""
    _write(tmp_path, "pyproject.toml", PYPROJECT)
    _write(tmp_path, ".rhiza/.cfg.toml", "[tool.bumpversion]\ntag = true\n")
    (error,) = check_bumpversion_config(tmp_path)
    assert ".rhiza/.cfg.toml" in error
    assert "never auto-discovered" in error


def test_drifted_current_version_is_an_error(tmp_path: Path) -> None:
    """A current_version that disagrees with [project].version fails."""
    _write(tmp_path, "pyproject.toml", PYPROJECT + BUMP_TABLE + 'current_version = "0.9.0"\n')
    (error,) = check_bumpversion_config(tmp_path)
    assert "'0.9.0'" in error
    assert "'1.2.3'" in error


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def test_main_returns_zero_when_sound(tmp_path: Path) -> None:
    """main() exits 0 for a sound configuration."""
    _write(tmp_path, "pyproject.toml", PYPROJECT + BUMP_TABLE)
    with patch("rhiza_hooks.check_bumpversion_config.find_repo_root", return_value=tmp_path):
        assert main([]) == 0


def test_main_returns_one_and_prints(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """main() exits 1 and reports the problem on stdout."""
    _write(tmp_path, "pyproject.toml", PYPROJECT)
    with patch("rhiza_hooks.check_bumpversion_config.find_repo_root", return_value=tmp_path):
        assert main([]) == 1
    assert "ERROR:" in capsys.readouterr().out


def test_main_ignores_passed_filenames(tmp_path: Path) -> None:
    """Filenames supplied by pre-commit are consumed and ignored."""
    _write(tmp_path, "pyproject.toml", PYPROJECT + BUMP_TABLE)
    with patch("rhiza_hooks.check_bumpversion_config.find_repo_root", return_value=tmp_path):
        assert main(["pyproject.toml", "setup.cfg"]) == 0


def test_module_is_executable() -> None:
    """The module runs as a script and exits cleanly on this repo."""
    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "rhiza_hooks.check_bumpversion_config"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_module_executes_main(tmp_path: Path) -> None:
    """Module execution calls main and exits with its return value."""
    (tmp_path / ".git").mkdir()
    _write(tmp_path, "pyproject.toml", PYPROJECT + BUMP_TABLE)

    with (
        patch("rhiza_hooks.check_bumpversion_config.find_repo_root", return_value=tmp_path),
        patch("rhiza_hooks.check_bumpversion_config.sys.argv", ["check_bumpversion_config"]),
        patch("rhiza_hooks.check_bumpversion_config.sys.exit") as mock_exit,
    ):
        import runpy
        import warnings

        # The module is already imported (top-level test import), so runpy warns
        # it was "found in sys.modules ... prior to execution"; filter just that
        # warning rather than mutating sys.modules, which would break module
        # identity for other tests that monkeypatch this module.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=r".*found in sys\.modules.*", category=RuntimeWarning)
            runpy.run_module("rhiza_hooks.check_bumpversion_config", run_name="__main__")
        mock_exit.assert_called_once_with(0)


# ---------------------------------------------------------------------------
# Property-based invariants
# ---------------------------------------------------------------------------
# TOML basic strings forbid raw control characters, and " / \ would need escaping.
# Restricting the alphabet keeps the generated pyproject.toml parseable, so these
# properties exercise the comparison rather than the TOML error path (which the
# unit tests above cover explicitly).
_TOML_SAFE = st.text(
    alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E, blacklist_characters='"\\'),
    min_size=1,
    max_size=20,
)


@given(version=_TOML_SAFE)
def test_matching_versions_never_error(tmp_path_factory: pytest.TempPathFactory, version: str) -> None:
    """Whenever the two versions agree, the check passes."""
    root = tmp_path_factory.mktemp("match")
    _write(
        root,
        "pyproject.toml",
        f'[project]\nname = "demo"\nversion = "{version}"\n{BUMP_TABLE}current_version = "{version}"\n',
    )
    assert check_bumpversion_config(root) == []


@given(left=_TOML_SAFE, right=_TOML_SAFE)
def test_differing_versions_always_error(tmp_path_factory: pytest.TempPathFactory, left: str, right: str) -> None:
    """Whenever the two versions differ, exactly one error is reported."""
    if left == right:
        return
    root = tmp_path_factory.mktemp("differ")
    _write(
        root,
        "pyproject.toml",
        f'[project]\nname = "demo"\nversion = "{left}"\n{BUMP_TABLE}current_version = "{right}"\n',
    )
    assert len(check_bumpversion_config(root)) == 1
