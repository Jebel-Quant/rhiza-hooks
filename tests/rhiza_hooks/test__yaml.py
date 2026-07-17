"""Tests for the shared YAML mapping loader (:mod:`rhiza_hooks._yaml`)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from rhiza_hooks._yaml import YamlError, YamlFailure, load_yaml_mapping


def test_missing_file_returns_not_found(tmp_path: Path) -> None:
    """A missing file yields a ``NOT_FOUND`` failure."""
    result = load_yaml_mapping(tmp_path / "absent.yml")
    assert result == YamlFailure(YamlError.NOT_FOUND)


def test_valid_mapping_is_returned(tmp_path: Path) -> None:
    """A well-formed mapping is parsed and returned as a dict."""
    path = tmp_path / "ok.yml"
    path.write_text("a: 1\nb: two\n", encoding="utf-8")
    assert load_yaml_mapping(path) == {"a": 1, "b": "two"}


def test_empty_file_returns_empty(tmp_path: Path) -> None:
    """An empty file yields an ``EMPTY`` failure."""
    path = tmp_path / "empty.yml"
    path.write_text("", encoding="utf-8")
    assert load_yaml_mapping(path) == YamlFailure(YamlError.EMPTY)


def test_non_mapping_returns_not_mapping(tmp_path: Path) -> None:
    """A top-level sequence yields a ``NOT_MAPPING`` failure."""
    path = tmp_path / "list.yml"
    path.write_text("- 1\n- 2\n", encoding="utf-8")
    assert load_yaml_mapping(path) == YamlFailure(YamlError.NOT_MAPPING)


def test_syntax_error_returns_invalid(tmp_path: Path) -> None:
    """Malformed YAML syntax yields an ``INVALID`` failure."""
    path = tmp_path / "bad.yml"
    path.write_text("a: [1, 2\n", encoding="utf-8")
    result = load_yaml_mapping(path)
    assert isinstance(result, YamlFailure)
    assert result.kind is YamlError.INVALID


def test_oversized_unicode_escape_returns_invalid(tmp_path: Path) -> None:
    r"""A ``\\U`` escape whose codepoint overflows ``chr()`` must not crash.

    PyYAML's scanner raises a bare ``OverflowError`` (not a
    ``yaml.YAMLError``) on such input; the loader must catch it and report
    it as invalid rather than let it escape. Regression test for the
    ClusterFuzzLite ``fuzz_bundles_validate`` crash.
    """
    path = tmp_path / "overflow.yml"
    path.write_bytes(b'- "\\U' + b"F" * 130 + b"A1e |\n")
    result = load_yaml_mapping(path)
    assert isinstance(result, YamlFailure)
    assert result.kind is YamlError.INVALID


class TestYamlError:
    """Tests for the :class:`YamlError` enum."""

    def test_member_values(self) -> None:
        """Each member maps to its documented string value."""
        assert YamlError.NOT_FOUND.value == "not_found"
        assert YamlError.INVALID.value == "invalid"
        assert YamlError.EMPTY.value == "empty"
        assert YamlError.NOT_MAPPING.value == "not_mapping"

    def test_members_are_exhaustive(self) -> None:
        """The enum defines exactly the four documented members."""
        assert {member.name for member in YamlError} == {
            "NOT_FOUND",
            "INVALID",
            "EMPTY",
            "NOT_MAPPING",
        }


class TestYamlFailure:
    """Tests for the :class:`YamlFailure` dataclass."""

    def test_detail_defaults_to_empty(self) -> None:
        """``detail`` defaults to the empty string."""
        assert YamlFailure(YamlError.NOT_FOUND).detail == ""

    def test_kind_is_stored(self) -> None:
        """The failure mode passed in is stored on ``kind``."""
        failure = YamlFailure(YamlError.INVALID, "boom")
        assert failure.kind is YamlError.INVALID
        assert failure.detail == "boom"

    def test_is_frozen(self) -> None:
        """Assigning to an attribute raises ``FrozenInstanceError``."""
        failure = YamlFailure(YamlError.NOT_FOUND)
        with pytest.raises(dataclasses.FrozenInstanceError):
            failure.kind = YamlError.EMPTY  # type: ignore[misc]
