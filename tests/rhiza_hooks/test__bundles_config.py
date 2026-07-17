"""Tests for the ``rhiza_hooks._bundles_config`` module."""

from __future__ import annotations

from textwrap import dedent

from rhiza_hooks._bundles_config import _get_config_data, _get_templates_from_config


def test_get_templates_from_valid_config(tmp_path):
    """Test getting templates from valid config."""
    config_file = tmp_path / "template.yml"
    config_file.write_text(
        dedent("""
        template-repository: test/repo
        template-branch: main
        templates:
          - core
          - python
    """)
    )

    templates = _get_templates_from_config(config_file)
    assert templates == {"core", "python"}


def test_get_config_data_normalizes_alias_form(tmp_path):
    """Alias-form keys (repository/ref/profiles) are normalized to canonical keys."""
    config_file = tmp_path / "template.yml"
    config_file.write_text(
        dedent("""
        repository: test/repo
        ref: main
        profiles:
          - core
    """)
    )

    config = _get_config_data(config_file)
    assert config == {
        "template-repository": "test/repo",
        "template-branch": "main",
        "templates": ["core"],
    }


def test_get_templates_from_alias_form_config(tmp_path):
    """Templates resolve from the ``profiles`` alias just like the canonical ``templates`` key."""
    config_file = tmp_path / "template.yml"
    config_file.write_text(
        dedent("""
        repository: test/repo
        ref: main
        profiles:
          - core
          - python
    """)
    )

    templates = _get_templates_from_config(config_file)
    assert templates == {"core", "python"}


def test_get_templates_from_nonexistent_file(tmp_path):
    """Test with non-existent config file."""
    config_file = tmp_path / "nonexistent.yml"
    templates = _get_templates_from_config(config_file)
    assert templates is None


def test_get_templates_from_non_utf8_file(tmp_path):
    """A non-UTF-8 config file is treated as unusable, not crashed on (fuzzing regression)."""
    config_file = tmp_path / "bad-encoding.yml"
    config_file.write_bytes(b"\xb5\n")
    templates = _get_templates_from_config(config_file)
    assert templates is None


def test_get_templates_from_config_without_templates_field(tmp_path):
    """Test config file without templates field."""
    config_file = tmp_path / "template.yml"
    config_file.write_text(
        dedent("""
        template-repository: test/repo
        template-branch: main
        include:
          - file1
          - file2
    """)
    )

    templates = _get_templates_from_config(config_file)
    assert templates is None


def test_get_templates_from_invalid_yaml(tmp_path):
    """Test with invalid YAML."""
    config_file = tmp_path / "template.yml"
    config_file.write_text("invalid: yaml: syntax:")

    templates = _get_templates_from_config(config_file)
    assert templates is None


def test_get_templates_from_config_not_dict(tmp_path):
    """Test config file that parses to a list instead of dict."""
    config_file = tmp_path / "template.yml"
    config_file.write_text("- item1\n- item2")

    templates = _get_templates_from_config(config_file)
    assert templates is None


def test_get_templates_from_config_templates_not_list(tmp_path):
    """Test config file where templates field is not a list."""
    config_file = tmp_path / "template.yml"
    config_file.write_text(
        dedent("""
        template-repository: test/repo
        templates: "not a list"
    """)
    )

    templates = _get_templates_from_config(config_file)
    assert templates is None
