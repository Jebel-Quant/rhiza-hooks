"""Tests for check_rhiza_config hook."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from rhiza_hooks.check_rhiza_config import main, validate_rhiza_config


@pytest.fixture
def temp_config(tmp_path: Path):
    """Create a temporary config file."""

    def _create(content: str) -> Path:
        config_file = tmp_path / "template.yml"
        config_file.write_text(dedent(content))
        return config_file

    return _create


class TestValidateRhizaConfig:
    """Tests for validate_rhiza_config function."""

    def test_valid_config(self, temp_config):
        """Test that a valid config passes validation."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
            include:
              - .github
              - Makefile
        """)
        errors = validate_rhiza_config(config)
        assert errors == []

    def test_valid_config_with_exclude(self, temp_config):
        """Test that a valid config with exclude passes validation."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
            include:
              - .github
            exclude:
              - .github/workflows/custom.yml
        """)
        errors = validate_rhiza_config(config)
        assert errors == []

    def test_valid_config_without_include(self, temp_config):
        """Test that a valid config without include but with templates passes validation."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
            templates:
              - template1
        """)
        errors = validate_rhiza_config(config)
        assert errors == []

    def test_valid_config_with_templates(self, temp_config):
        """Test that a valid config with templates key passes validation."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
            templates:
              - template1
              - template2
        """)
        errors = validate_rhiza_config(config)
        assert errors == []

    def test_missing_include_and_templates(self, temp_config):
        """Test that missing both include and templates is reported."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
        """)
        errors = validate_rhiza_config(config)
        assert any("include" in e.lower() or "templates" in e.lower() for e in errors)

    def test_missing_required_keys(self, temp_config):
        """Test that missing required keys are reported."""
        config = temp_config("""
            template-branch: main
            include:
              - Makefile
        """)
        errors = validate_rhiza_config(config)
        assert any("template-repository" in e for e in errors)
        # With include present, should not have the "include or templates" error
        assert not any("At least one" in e for e in errors)

    def test_invalid_repository_format(self, temp_config):
        """Test that invalid repository format is reported."""
        config = temp_config("""
            template-repository: invalid-format
            template-branch: main
            include:
              - Makefile
        """)
        errors = validate_rhiza_config(config)
        assert any("owner/repo" in e for e in errors)

    def test_empty_include(self, temp_config):
        """Test that empty include list is reported."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
            include: []
        """)
        errors = validate_rhiza_config(config)
        assert any("empty" in e.lower() for e in errors)

    def test_unknown_key(self, temp_config):
        """Test that unknown keys are reported."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
            include:
              - Makefile
            unknown-key: value
        """)
        errors = validate_rhiza_config(config)
        assert any("unknown-key" in e.lower() for e in errors)

    def test_empty_file(self, temp_config):
        """Test that empty file is reported."""
        config = temp_config("")
        errors = validate_rhiza_config(config)
        assert len(errors) > 0

    def test_file_not_found(self, tmp_path: Path):
        """Test that missing file is reported."""
        missing = tmp_path / "nonexistent.yml"
        errors = validate_rhiza_config(missing)
        assert any("not found" in e.lower() for e in errors)

    def test_invalid_yaml(self, temp_config):
        """Test that invalid YAML is reported."""
        config = temp_config("invalid: yaml: syntax:")
        errors = validate_rhiza_config(config)
        assert any("yaml" in e.lower() for e in errors)

    def test_non_dict_config(self, temp_config):
        """Test that non-dict config is reported."""
        config = temp_config("- item1\n- item2")
        errors = validate_rhiza_config(config)
        assert any("mapping" in e.lower() for e in errors)

    def test_template_repository_not_string(self, temp_config):
        """Test that non-string template-repository is reported."""
        config = temp_config("""
            template-repository: 123
            template-branch: main
            include:
              - Makefile
        """)
        errors = validate_rhiza_config(config)
        assert any("string" in e.lower() for e in errors)

    def test_template_branch_not_string(self, temp_config):
        """Test that non-string template-branch is reported."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: 123
            include:
              - Makefile
        """)
        errors = validate_rhiza_config(config)
        assert any("string" in e.lower() for e in errors)

    def test_empty_template_branch(self, temp_config):
        """Test that empty template-branch is reported."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: ""
            include:
              - Makefile
        """)
        errors = validate_rhiza_config(config)
        assert any("empty" in e.lower() for e in errors)

    def test_include_not_list(self, temp_config):
        """Test that non-list include is reported."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
            include: just-a-string
        """)
        errors = validate_rhiza_config(config)
        assert any("list" in e.lower() for e in errors)

    def test_exclude_not_list(self, temp_config):
        """Test that non-list exclude is reported."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
            include:
              - Makefile
            exclude: just-a-string
        """)
        errors = validate_rhiza_config(config)
        assert any("list" in e.lower() for e in errors)

    def test_templates_not_list(self, temp_config):
        """Test that non-list templates is reported."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
            templates: just-a-string
        """)
        errors = validate_rhiza_config(config)
        assert any("list" in e.lower() for e in errors)

    def test_empty_templates(self, temp_config):
        """Test that empty templates list is reported."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
            templates: []
        """)
        errors = validate_rhiza_config(config)
        assert any("empty" in e.lower() for e in errors)


class TestMain:
    """Tests for main function."""

    def test_main_valid_config(self, temp_config) -> None:
        """Main returns 0 for valid config."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
            include:
              - Makefile
        """)
        result = main([str(config)])
        assert result == 0

    def test_main_invalid_config(self, temp_config, capsys: pytest.CaptureFixture[str]) -> None:
        """Main returns 1 for invalid config."""
        config = temp_config("invalid")
        result = main([str(config)])
        assert result == 1
        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_main_no_files(self) -> None:
        """Main returns 0 when no files provided."""
        result = main([])
        assert result == 0


class TestModuleExecution:
    """Tests for module execution via if __name__ == '__main__'."""

    def test_module_executes_main(self) -> None:
        """Module execution calls main and exits with its return value."""
        import runpy
        from unittest.mock import patch

        with (
            patch("rhiza_hooks.check_rhiza_config.sys.argv", ["check_rhiza_config"]),
            patch("rhiza_hooks.check_rhiza_config.sys.exit") as mock_exit,
        ):
            runpy.run_module("rhiza_hooks.check_rhiza_config", run_name="__main__")
            mock_exit.assert_called_once_with(0)
