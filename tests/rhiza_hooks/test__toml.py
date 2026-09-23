"""Tests for the shared lenient TOML loader, ``rhiza_hooks._toml``.

Every hook that reads a TOML file goes through :func:`load_toml`, so the
"unusable file reads as absent" stance is pinned here once. The hooks' own test
modules keep a regression test each for the input that used to crash them (#396).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from rhiza_hooks._toml import load_toml

PYPROJECT = '[project]\nname = "demo"\nversion = "1.2.3"\n'


def test_loads_a_well_formed_toml_file(tmp_path: Path) -> None:
    """A parseable file is returned as its mapping."""
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    assert load_toml(tmp_path / "pyproject.toml") == {"project": {"name": "demo", "version": "1.2.3"}}


def test_missing_file_reads_none(tmp_path: Path) -> None:
    """A missing file yields None."""
    assert load_toml(tmp_path / "pyproject.toml") is None


def test_malformed_toml_reads_none(tmp_path: Path) -> None:
    """Malformed TOML is treated as absent, not raised."""
    (tmp_path / "pyproject.toml").write_text("[project\nversion =", encoding="utf-8")
    assert load_toml(tmp_path / "pyproject.toml") is None


def test_directory_reads_none(tmp_path: Path) -> None:
    """A directory at the path exists() but raises OSError on open; it reads as absent."""
    (tmp_path / "pyproject.toml").mkdir()
    assert load_toml(tmp_path / "pyproject.toml") is None


def test_unreadable_file_reads_none(tmp_path: Path) -> None:
    """An OSError while opening is treated as absent."""
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    with patch("pathlib.Path.open", side_effect=OSError("boom")):
        assert load_toml(tmp_path / "pyproject.toml") is None


def test_binary_file_reads_none(tmp_path: Path) -> None:
    """A file that is not valid UTF-8 is treated as absent, not a traceback.

    tomllib decodes the byte stream itself, so invalid UTF-8 arrives as
    UnicodeDecodeError rather than TOMLDecodeError.
    """
    (tmp_path / "pyproject.toml").write_bytes(b"\xff\xfe\x00[project]")
    assert load_toml(tmp_path / "pyproject.toml") is None


def test_unexpected_error_propagates(tmp_path: Path) -> None:
    """Errors other than TOMLDecodeError/OSError/UnicodeDecodeError are not swallowed (issue #174)."""
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")

    def boom(_handle: object) -> None:
        """Raise a RuntimeError to simulate an unexpected tomllib failure."""
        raise RuntimeError("unexpected")

    with (
        patch("rhiza_hooks._toml.tomllib.load", side_effect=boom),
        pytest.raises(RuntimeError, match="unexpected"),
    ):
        load_toml(tmp_path / "pyproject.toml")
