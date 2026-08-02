"""Tests for the check_rust_version hook.

Combines unit tests, subprocess-level integration tests and property-based
(Hypothesis) invariants for the ``rhiza_hooks.check_rust_version`` module.
"""

from __future__ import annotations

import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rhiza_hooks.check_rust_version import (
    _check_channel_satisfies_msrv,
    _load_toml,
    _string_value,
    _table,
    check_version_consistency,
    get_cargo_rust_versions,
    get_toolchain_channels,
    main,
    read_legacy_toolchain,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def _write(root: Path, name: str, content: str) -> None:
    """Write *content* to ``root/name``."""
    (root / name).write_text(content)


# ---------------------------------------------------------------------------
# Unit tests: _table
# ---------------------------------------------------------------------------
def test_table_returns_nested_table() -> None:
    """A present nested table is returned as-is."""
    assert _table({"workspace": {"package": {"rust-version": "1.75"}}}, "workspace", "package") == {
        "rust-version": "1.75"
    }


def test_table_missing_key_returns_empty() -> None:
    """A missing key yields an empty table rather than raising."""
    assert _table({}, "package") == {}


def test_table_non_table_leaf_returns_empty() -> None:
    """A leaf that is not a table yields an empty table (pins the final isinstance)."""
    assert _table({"toolchain": "stable"}, "toolchain") == {}


def test_table_non_table_midway_returns_empty() -> None:
    """A non-table hop mid-walk short-circuits (pins the in-loop isinstance)."""
    assert _table({"workspace": "oops"}, "workspace", "package") == {}


# ---------------------------------------------------------------------------
# Unit tests: _string_value
# ---------------------------------------------------------------------------
def test_string_value_strips() -> None:
    """A string value is returned stripped."""
    assert _string_value({"channel": "  1.75.0 "}, "channel") == "1.75.0"


def test_string_value_missing_returns_none() -> None:
    """A missing key yields None."""
    assert _string_value({}, "channel") is None


def test_string_value_non_string_returns_none() -> None:
    """A non-string value (e.g. a TOML table) yields None."""
    assert _string_value({"channel": {"nested": True}}, "channel") is None


def test_string_value_blank_returns_none() -> None:
    """A whitespace-only value is treated as absent."""
    assert _string_value({"channel": "   "}, "channel") is None


# ---------------------------------------------------------------------------
# Unit tests: _load_toml
# ---------------------------------------------------------------------------
def test_load_toml_reads_document(tmp_path: Path) -> None:
    """A valid TOML file is parsed into a dict."""
    _write(tmp_path, "Cargo.toml", '[package]\nrust-version = "1.75"\n')
    assert _load_toml(tmp_path / "Cargo.toml") == {"package": {"rust-version": "1.75"}}


def test_load_toml_missing_returns_none(tmp_path: Path) -> None:
    """A missing file yields None."""
    assert _load_toml(tmp_path / "Cargo.toml") is None


def test_load_toml_malformed_returns_none(tmp_path: Path) -> None:
    """Malformed TOML is treated as unspecified rather than crashing."""
    _write(tmp_path, "Cargo.toml", "this is not toml {{{{")
    assert _load_toml(tmp_path / "Cargo.toml") is None


def test_load_toml_unreadable_returns_none(tmp_path: Path) -> None:
    """An OSError on open (path is a directory) is treated as unspecified."""
    (tmp_path / "Cargo.toml").mkdir()
    assert _load_toml(tmp_path / "Cargo.toml") is None


def test_load_toml_unexpected_error_propagates(tmp_path: Path) -> None:
    """Errors other than TOMLDecodeError/OSError are not swallowed."""
    _write(tmp_path, "Cargo.toml", '[package]\nrust-version = "1.75"\n')

    def boom(_handle: object) -> None:
        """Raise a RuntimeError to simulate an unexpected tomllib failure."""
        raise RuntimeError("unexpected")

    with (
        patch("rhiza_hooks.check_rust_version.tomllib.load", side_effect=boom),
        pytest.raises(RuntimeError, match="unexpected"),
    ):
        _load_toml(tmp_path / "Cargo.toml")


# ---------------------------------------------------------------------------
# Unit tests: read_legacy_toolchain
# ---------------------------------------------------------------------------
def test_legacy_plain_text_channel(tmp_path: Path) -> None:
    """A bare channel name is read verbatim from the legacy plain-text form."""
    _write(tmp_path, "rust-toolchain", "1.75.0\n")
    assert read_legacy_toolchain(tmp_path / "rust-toolchain") == "1.75.0"


def test_legacy_plain_text_named_channel(tmp_path: Path) -> None:
    """A named channel is read verbatim (it is not valid TOML either)."""
    _write(tmp_path, "rust-toolchain", "nightly-2024-01-01\n")
    assert read_legacy_toolchain(tmp_path / "rust-toolchain") == "nightly-2024-01-01"


def test_legacy_toml_channel(tmp_path: Path) -> None:
    """The legacy filename may hold the modern TOML form."""
    _write(tmp_path, "rust-toolchain", '[toolchain]\nchannel = "1.76.0"\n')
    assert read_legacy_toolchain(tmp_path / "rust-toolchain") == "1.76.0"


def test_legacy_toml_without_channel_returns_none(tmp_path: Path) -> None:
    """Valid TOML that declares no channel yields None."""
    _write(tmp_path, "rust-toolchain", '[toolchain]\ncomponents = ["clippy"]\n')
    assert read_legacy_toolchain(tmp_path / "rust-toolchain") is None


def test_legacy_missing_returns_none(tmp_path: Path) -> None:
    """A missing legacy file yields None."""
    assert read_legacy_toolchain(tmp_path / "rust-toolchain") is None


def test_legacy_empty_returns_none(tmp_path: Path) -> None:
    """A blank legacy file declares no channel."""
    _write(tmp_path, "rust-toolchain", "   \n\n")
    assert read_legacy_toolchain(tmp_path / "rust-toolchain") is None


def test_legacy_unreadable_returns_none(tmp_path: Path) -> None:
    """An OSError on read (path is a directory) is treated as unspecified."""
    (tmp_path / "rust-toolchain").mkdir()
    assert read_legacy_toolchain(tmp_path / "rust-toolchain") is None


# ---------------------------------------------------------------------------
# Unit tests: get_toolchain_channels
# ---------------------------------------------------------------------------
def test_channels_from_modern_file(tmp_path: Path) -> None:
    """``rust-toolchain.toml`` contributes its channel under its own filename key."""
    _write(tmp_path, "rust-toolchain.toml", '[toolchain]\nchannel = "1.75.0"\n')
    assert get_toolchain_channels(tmp_path) == {"rust-toolchain.toml": "1.75.0"}


def test_channels_from_both_files(tmp_path: Path) -> None:
    """Both toolchain files are reported when both exist."""
    _write(tmp_path, "rust-toolchain.toml", '[toolchain]\nchannel = "1.75.0"\n')
    _write(tmp_path, "rust-toolchain", "1.75.0\n")
    assert get_toolchain_channels(tmp_path) == {
        "rust-toolchain.toml": "1.75.0",
        "rust-toolchain": "1.75.0",
    }


def test_channels_modern_file_without_channel(tmp_path: Path) -> None:
    """A toolchain file that declares no channel contributes nothing."""
    _write(tmp_path, "rust-toolchain.toml", '[toolchain]\ncomponents = ["rustfmt"]\n')
    assert get_toolchain_channels(tmp_path) == {}


def test_channels_none_declared(tmp_path: Path) -> None:
    """A repository with no toolchain files reports no channels."""
    assert get_toolchain_channels(tmp_path) == {}


# ---------------------------------------------------------------------------
# Unit tests: get_cargo_rust_versions
# ---------------------------------------------------------------------------
def test_cargo_package_msrv(tmp_path: Path) -> None:
    """``[package] rust-version`` is reported under the ``package`` label."""
    _write(tmp_path, "Cargo.toml", '[package]\nname = "demo"\nrust-version = "1.75"\n')
    assert get_cargo_rust_versions(tmp_path) == {"package": "1.75"}


def test_cargo_workspace_msrv(tmp_path: Path) -> None:
    """``[workspace.package] rust-version`` is reported under its dotted label."""
    _write(tmp_path, "Cargo.toml", '[workspace.package]\nrust-version = "1.75"\n')
    assert get_cargo_rust_versions(tmp_path) == {"workspace.package": "1.75"}


def test_cargo_both_msrvs(tmp_path: Path) -> None:
    """Both tables are reported when both declare an MSRV."""
    _write(
        tmp_path,
        "Cargo.toml",
        '[package]\nrust-version = "1.75"\n\n[workspace.package]\nrust-version = "1.76"\n',
    )
    assert get_cargo_rust_versions(tmp_path) == {"package": "1.75", "workspace.package": "1.76"}


def test_cargo_without_msrv(tmp_path: Path) -> None:
    """A Cargo.toml with no ``rust-version`` reports nothing."""
    _write(tmp_path, "Cargo.toml", '[package]\nname = "demo"\n')
    assert get_cargo_rust_versions(tmp_path) == {}


def test_cargo_missing_returns_empty(tmp_path: Path) -> None:
    """A missing Cargo.toml reports nothing."""
    assert get_cargo_rust_versions(tmp_path) == {}


def test_cargo_non_table_workspace_returns_empty(tmp_path: Path) -> None:
    """A ``workspace`` key that is not a table is ignored rather than crashing."""
    _write(tmp_path, "Cargo.toml", 'workspace = "oops"\n')
    assert get_cargo_rust_versions(tmp_path) == {}


# ---------------------------------------------------------------------------
# Unit tests: check_version_consistency
# ---------------------------------------------------------------------------
def test_consistent_project_has_no_errors(tmp_path: Path) -> None:
    """A toolchain at exactly the MSRV is consistent."""
    _write(tmp_path, "rust-toolchain.toml", '[toolchain]\nchannel = "1.75.0"\n')
    _write(tmp_path, "Cargo.toml", '[package]\nrust-version = "1.75"\n')
    assert check_version_consistency(tmp_path) == []


def test_toolchain_above_msrv_is_consistent(tmp_path: Path) -> None:
    """A toolchain newer than the MSRV is fine."""
    _write(tmp_path, "rust-toolchain.toml", '[toolchain]\nchannel = "1.80.0"\n')
    _write(tmp_path, "Cargo.toml", '[package]\nrust-version = "1.75"\n')
    assert check_version_consistency(tmp_path) == []


def test_toolchain_below_msrv_is_reported(tmp_path: Path) -> None:
    """A toolchain older than the MSRV cannot build the crate."""
    _write(tmp_path, "rust-toolchain.toml", '[toolchain]\nchannel = "1.70.0"\n')
    _write(tmp_path, "Cargo.toml", '[package]\nrust-version = "1.75"\n')
    assert check_version_consistency(tmp_path) == [
        "Rust version mismatch: rust-toolchain.toml pins channel 1.70.0, "
        "but Cargo.toml [package] rust-version is 1.75 "
        "(the pinned toolchain must be at least the MSRV)"
    ]


def test_named_channel_is_accepted(tmp_path: Path) -> None:
    """A named channel carries no version number, so nothing is compared."""
    _write(tmp_path, "rust-toolchain.toml", '[toolchain]\nchannel = "stable"\n')
    _write(tmp_path, "Cargo.toml", '[package]\nrust-version = "1.75"\n')
    assert check_version_consistency(tmp_path) == []


def test_unparseable_msrv_is_ignored(tmp_path: Path) -> None:
    """A non-numeric ``rust-version`` is treated as unspecified, as in the Python hook."""
    _write(tmp_path, "rust-toolchain.toml", '[toolchain]\nchannel = "1.70.0"\n')
    _write(tmp_path, "Cargo.toml", '[package]\nrust-version = "not-a-version"\n')
    assert check_version_consistency(tmp_path) == []


def test_toolchain_files_disagree(tmp_path: Path) -> None:
    """The modern and legacy toolchain files must pin the same channel."""
    _write(tmp_path, "rust-toolchain.toml", '[toolchain]\nchannel = "1.75.0"\n')
    _write(tmp_path, "rust-toolchain", "1.72.0\n")
    assert check_version_consistency(tmp_path) == [
        "Rust toolchain mismatch: rust-toolchain.toml pins channel 1.75.0, but rust-toolchain pins 1.72.0"
    ]


def test_toolchain_files_agree_modulo_trailing_zero(tmp_path: Path) -> None:
    """``1.75`` and ``1.75.0`` are the same pin, not a mismatch."""
    _write(tmp_path, "rust-toolchain.toml", '[toolchain]\nchannel = "1.75"\n')
    _write(tmp_path, "rust-toolchain", "1.75.0\n")
    assert check_version_consistency(tmp_path) == []


def test_only_legacy_toolchain_file_is_not_a_mismatch(tmp_path: Path) -> None:
    """One toolchain file alone can never disagree with the other."""
    _write(tmp_path, "rust-toolchain", "1.75.0\n")
    _write(tmp_path, "Cargo.toml", '[package]\nrust-version = "1.75"\n')
    assert check_version_consistency(tmp_path) == []


def test_only_modern_toolchain_file_is_not_a_mismatch(tmp_path: Path) -> None:
    """The modern file alone is not compared against an absent legacy file."""
    _write(tmp_path, "rust-toolchain.toml", '[toolchain]\nchannel = "1.75.0"\n')
    assert check_version_consistency(tmp_path) == []


def test_msrv_declarations_disagree(tmp_path: Path) -> None:
    """``[package]`` and ``[workspace.package]`` must declare the same MSRV."""
    _write(
        tmp_path,
        "Cargo.toml",
        '[package]\nrust-version = "1.70"\n\n[workspace.package]\nrust-version = "1.75"\n',
    )
    assert check_version_consistency(tmp_path) == [
        "Rust version mismatch: Cargo.toml [package] rust-version is 1.70, but [workspace.package] rust-version is 1.75"
    ]


def test_msrv_declarations_agree_modulo_trailing_zero(tmp_path: Path) -> None:
    """``1.75`` and ``1.75.0`` are the same MSRV in both tables."""
    _write(
        tmp_path,
        "Cargo.toml",
        '[package]\nrust-version = "1.75"\n\n[workspace.package]\nrust-version = "1.75.0"\n',
    )
    assert check_version_consistency(tmp_path) == []


def test_only_package_msrv_is_not_a_mismatch(tmp_path: Path) -> None:
    """A single MSRV declaration can never disagree with the other table."""
    _write(tmp_path, "Cargo.toml", '[package]\nrust-version = "1.75"\n')
    assert check_version_consistency(tmp_path) == []


def test_only_workspace_msrv_is_not_a_mismatch(tmp_path: Path) -> None:
    """``[workspace.package]`` alone is not compared against an absent ``[package]``."""
    _write(tmp_path, "Cargo.toml", '[workspace.package]\nrust-version = "1.75"\n')
    assert check_version_consistency(tmp_path) == []


def test_every_channel_is_checked_against_every_msrv(tmp_path: Path) -> None:
    """Errors are emitted per (toolchain file, MSRV table) pair, in sorted order.

    Pins both ``sorted()`` calls: channels sort ``rust-toolchain`` before
    ``rust-toolchain.toml``, and labels sort ``package`` before
    ``workspace.package``.
    """
    _write(tmp_path, "rust-toolchain.toml", '[toolchain]\nchannel = "1.60.0"\n')
    _write(tmp_path, "rust-toolchain", "1.60.0\n")
    _write(
        tmp_path,
        "Cargo.toml",
        '[package]\nrust-version = "1.70"\n\n[workspace.package]\nrust-version = "1.70"\n',
    )

    assert check_version_consistency(tmp_path) == [
        "Rust version mismatch: rust-toolchain pins channel 1.60.0, "
        "but Cargo.toml [package] rust-version is 1.70 (the pinned toolchain must be at least the MSRV)",
        "Rust version mismatch: rust-toolchain pins channel 1.60.0, "
        "but Cargo.toml [workspace.package] rust-version is 1.70 (the pinned toolchain must be at least the MSRV)",
        "Rust version mismatch: rust-toolchain.toml pins channel 1.60.0, "
        "but Cargo.toml [package] rust-version is 1.70 (the pinned toolchain must be at least the MSRV)",
        "Rust version mismatch: rust-toolchain.toml pins channel 1.60.0, "
        "but Cargo.toml [workspace.package] rust-version is 1.70 (the pinned toolchain must be at least the MSRV)",
    ]


def test_no_rust_files_is_consistent(tmp_path: Path) -> None:
    """A repository with no Rust files at all passes (this hook is opt-in per repo)."""
    assert check_version_consistency(tmp_path) == []


# ---------------------------------------------------------------------------
# Unit tests: main
# ---------------------------------------------------------------------------
def test_main_consistent_returns_zero(tmp_path: Path) -> None:
    """Returns 0 when versions are consistent."""
    _write(tmp_path, "rust-toolchain.toml", '[toolchain]\nchannel = "1.75.0"\n')
    _write(tmp_path, "Cargo.toml", '[package]\nrust-version = "1.75"\n')

    with patch("rhiza_hooks.check_rust_version.find_repo_root", return_value=tmp_path):
        assert main([]) == 0


def test_main_inconsistent_returns_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Returns 1 and prints each error with the ERROR prefix."""
    _write(tmp_path, "rust-toolchain.toml", '[toolchain]\nchannel = "1.70.0"\n')
    _write(tmp_path, "Cargo.toml", '[package]\nrust-version = "1.75"\n')

    with patch("rhiza_hooks.check_rust_version.find_repo_root", return_value=tmp_path):
        assert main([]) == 1

    assert capsys.readouterr().out == (
        "ERROR: Rust version mismatch: rust-toolchain.toml pins channel 1.70.0, "
        "but Cargo.toml [package] rust-version is 1.75 "
        "(the pinned toolchain must be at least the MSRV)\n"
    )


def test_main_no_files_returns_zero(tmp_path: Path) -> None:
    """Returns 0 when no Rust version files exist."""
    with patch("rhiza_hooks.check_rust_version.find_repo_root", return_value=tmp_path):
        assert main([]) == 0


def test_main_accepts_filenames_argument(tmp_path: Path) -> None:
    """Main accepts (and ignores) pre-commit's filename arguments."""
    with patch("rhiza_hooks.check_rust_version.find_repo_root", return_value=tmp_path):
        assert main(["Cargo.toml", "rust-toolchain.toml"]) == 0


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
    assert "Check Rust version consistency" in out
    assert "Filenames (ignored, checks repo root)" in out
    assert "filenames" in out


# ---------------------------------------------------------------------------
# Unit tests: module execution via if __name__ == '__main__'
# ---------------------------------------------------------------------------
def test_module_executes_main(tmp_path: Path) -> None:
    """Module execution calls main and exits with its return value."""
    with (
        patch("rhiza_hooks.check_rust_version.find_repo_root", return_value=tmp_path),
        patch("rhiza_hooks.check_rust_version.sys.argv", ["check_rust_version"]),
        patch("rhiza_hooks.check_rust_version.sys.exit") as mock_exit,
    ):
        import runpy
        import warnings

        # The module is already imported (top-level test import), so runpy warns
        # it was "found in sys.modules ... prior to execution"; filter just that
        # warning rather than mutating sys.modules.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=r".*found in sys\.modules.*", category=RuntimeWarning)
            runpy.run_module("rhiza_hooks.check_rust_version", run_name="__main__")
        mock_exit.assert_called_once_with(0)


# ---------------------------------------------------------------------------
# Subprocess-level integration tests
# ---------------------------------------------------------------------------
def test_subprocess_consistent(mock_project: Callable[[dict[str, str]], Path]) -> None:
    """A consistent Rust project exits 0 when run as a module."""
    project = mock_project(
        {
            "rust-toolchain.toml": '[toolchain]\nchannel = "1.75.0"\n',
            "Cargo.toml": '[package]\nname = "demo"\nrust-version = "1.75"\n',
        }
    )

    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "rhiza_hooks.check_rust_version"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


def test_subprocess_inconsistent(mock_project: Callable[[dict[str, str]], Path]) -> None:
    """An MSRV above the pinned toolchain exits 1 when run as a module."""
    project = mock_project(
        {
            "rust-toolchain.toml": '[toolchain]\nchannel = "1.70.0"\n',
            "Cargo.toml": '[package]\nname = "demo"\nrust-version = "1.75"\n',
        }
    )

    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "rhiza_hooks.check_rust_version"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "rust-version is 1.75" in result.stdout


def test_subprocess_on_this_project(project_root: Path) -> None:
    """This (Python-only) repository declares no Rust versions, so the hook passes."""
    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "rhiza_hooks.check_rust_version"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Property-based tests (Hypothesis)
# ---------------------------------------------------------------------------
# Hypothesis rejects function-scoped fixtures, so these drive the pure
# comparison layer directly rather than materialising files under tmp_path.
_minor = st.integers(min_value=0, max_value=99)


@given(_minor, _minor)
def test_property_toolchain_at_or_above_msrv_never_errors(first: int, second: int) -> None:
    """Whenever the pinned toolchain is at least the MSRV, the check is silent."""
    toolchain, msrv = max(first, second), min(first, second)
    channels = {"rust-toolchain.toml": f"1.{toolchain}.0"}
    msrvs = {"package": f"1.{msrv}"}

    assert _check_channel_satisfies_msrv(channels, msrvs) == []


@given(_minor, _minor)
def test_property_toolchain_below_msrv_always_errors(first: int, second: int) -> None:
    """Whenever the pinned toolchain is strictly below the MSRV, exactly one error is raised."""
    toolchain, msrv = min(first, second), max(first, second)
    if toolchain == msrv:
        return
    channels = {"rust-toolchain.toml": f"1.{toolchain}.0"}
    msrvs = {"package": f"1.{msrv}"}

    errors = _check_channel_satisfies_msrv(channels, msrvs)
    assert len(errors) == 1
    assert f"rust-version is 1.{msrv}" in errors[0]


@given(st.sampled_from(["stable", "beta", "nightly", "nightly-2024-01-01"]), _minor)
def test_property_named_channels_are_never_compared(channel: str, msrv: int) -> None:
    """A named channel is accepted against any MSRV, however high."""
    assert _check_channel_satisfies_msrv({"rust-toolchain.toml": channel}, {"package": f"1.{msrv}"}) == []
