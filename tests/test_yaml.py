"""Tests for the shared YAML mapping loader (:mod:`rhiza_hooks._yaml`)."""

from __future__ import annotations

from pathlib import Path

from rhiza_hooks._yaml import YamlError, YamlFailure, load_yaml_mapping


class TestLoadYamlMapping:
    """Tests for :func:`load_yaml_mapping`."""

    def test_missing_file_returns_not_found(self, tmp_path: Path) -> None:
        """A missing file yields a ``NOT_FOUND`` failure."""
        result = load_yaml_mapping(tmp_path / "absent.yml")
        assert result == YamlFailure(YamlError.NOT_FOUND)

    def test_valid_mapping_is_returned(self, tmp_path: Path) -> None:
        """A well-formed mapping is parsed and returned as a dict."""
        path = tmp_path / "ok.yml"
        path.write_text("a: 1\nb: two\n", encoding="utf-8")
        assert load_yaml_mapping(path) == {"a": 1, "b": "two"}

    def test_empty_file_returns_empty(self, tmp_path: Path) -> None:
        """An empty file yields an ``EMPTY`` failure."""
        path = tmp_path / "empty.yml"
        path.write_text("", encoding="utf-8")
        assert load_yaml_mapping(path) == YamlFailure(YamlError.EMPTY)

    def test_non_mapping_returns_not_mapping(self, tmp_path: Path) -> None:
        """A top-level sequence yields a ``NOT_MAPPING`` failure."""
        path = tmp_path / "list.yml"
        path.write_text("- 1\n- 2\n", encoding="utf-8")
        assert load_yaml_mapping(path) == YamlFailure(YamlError.NOT_MAPPING)

    def test_syntax_error_returns_invalid(self, tmp_path: Path) -> None:
        """Malformed YAML syntax yields an ``INVALID`` failure."""
        path = tmp_path / "bad.yml"
        path.write_text("a: [1, 2\n", encoding="utf-8")
        result = load_yaml_mapping(path)
        assert isinstance(result, YamlFailure)
        assert result.kind is YamlError.INVALID

    def test_oversized_unicode_escape_returns_invalid(self, tmp_path: Path) -> None:
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
