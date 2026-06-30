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
        """Write the dedented content to a template.yml and return its path."""
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
        assert errors == ["At least one of 'include' or 'templates' must be present"]

    def test_missing_required_keys(self, temp_config):
        """Test that missing required keys are reported."""
        config = temp_config("""
            template-branch: main
            include:
              - Makefile
        """)
        errors = validate_rhiza_config(config)
        assert "Missing required key: template-repository" in errors
        # With include present, should not have the "include or templates" error
        assert "At least one of 'include' or 'templates' must be present" not in errors

    def test_missing_template_branch(self, temp_config):
        """A config without template-branch is reported and skips branch validation."""
        config = temp_config("""
            template-repository: owner/repo
            include:
              - Makefile
        """)
        errors = validate_rhiza_config(config)
        assert any("Missing required key: template-branch" in e for e in errors)
        # The branch-format checks are skipped, so no "must be a string"/"cannot be empty".
        assert not any("template-branch must be" in e or "template-branch cannot" in e for e in errors)

    def test_invalid_repository_format(self, temp_config):
        """Test that invalid repository format is reported."""
        config = temp_config("""
            template-repository: invalid-format
            template-branch: main
            include:
              - Makefile
        """)
        errors = validate_rhiza_config(config)
        assert errors == ["template-repository should be in 'owner/repo' format, got: invalid-format"]

    def test_empty_include(self, temp_config):
        """Test that empty include list is reported with the exact message."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
            include: []
        """)
        errors = validate_rhiza_config(config)
        assert errors == ["include list cannot be empty"]

    def test_unknown_key(self, temp_config):
        """Test that unknown keys are reported with the exact message."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
            include:
              - Makefile
            unknown-key: value
        """)
        errors = validate_rhiza_config(config)
        assert errors == ["Unknown key: unknown-key"]

    def test_empty_file(self, temp_config):
        """Test that empty file is reported with the exact message."""
        config = temp_config("")
        errors = validate_rhiza_config(config)
        assert errors == ["Configuration file is empty"]

    def test_file_not_found(self, tmp_path: Path):
        """Test that missing file is reported with the exact message."""
        missing = tmp_path / "nonexistent.yml"
        errors = validate_rhiza_config(missing)
        assert errors == [f"File not found: {missing}"]

    def test_invalid_yaml(self, temp_config):
        """Test that invalid YAML is reported with the exact prefix."""
        config = temp_config("invalid: yaml: syntax:")
        errors = validate_rhiza_config(config)
        assert len(errors) == 1
        # startswith pins the leading literal; the {e} tail is parser-defined.
        assert errors[0].startswith("Invalid YAML: ")

    def test_non_dict_config(self, temp_config):
        """Test that non-dict config is reported with the exact message."""
        config = temp_config("- item1\n- item2")
        errors = validate_rhiza_config(config)
        assert errors == ["Configuration must be a YAML mapping"]

    def test_template_repository_not_string(self, temp_config):
        """Test that non-string template-repository is reported with the exact message."""
        config = temp_config("""
            template-repository: 123
            template-branch: main
            include:
              - Makefile
        """)
        errors = validate_rhiza_config(config)
        assert errors == ["template-repository must be a string"]

    def test_template_branch_not_string(self, temp_config):
        """Test that non-string template-branch is reported with the exact message."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: 123
            include:
              - Makefile
        """)
        errors = validate_rhiza_config(config)
        assert errors == ["template-branch must be a string"]

    def test_empty_template_branch(self, temp_config):
        """Test that empty template-branch is reported with the exact message."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: ""
            include:
              - Makefile
        """)
        errors = validate_rhiza_config(config)
        assert errors == ["template-branch cannot be empty"]

    def test_include_not_list(self, temp_config):
        """Test that non-list include is reported with the exact message."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
            include: just-a-string
        """)
        errors = validate_rhiza_config(config)
        assert errors == ["include must be a list"]

    def test_exclude_not_list(self, temp_config):
        """Test that non-list exclude is reported with the exact message."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
            include:
              - Makefile
            exclude: just-a-string
        """)
        errors = validate_rhiza_config(config)
        assert errors == ["exclude must be a list or null"]

    def test_templates_not_list(self, temp_config):
        """Test that non-list templates is reported with the exact message."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
            templates: just-a-string
        """)
        errors = validate_rhiza_config(config)
        assert errors == ["templates must be a list"]

    def test_empty_templates(self, temp_config):
        """Test that empty templates list is reported with the exact message."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
            templates: []
        """)
        errors = validate_rhiza_config(config)
        assert errors == ["templates list cannot be empty"]

    def test_alias_repository_accepted(self, temp_config):
        """Test that 'repository' alias is accepted for 'template-repository'."""
        config = temp_config("""
            repository: owner/repo
            template-branch: main
            include:
              - Makefile
        """)
        errors = validate_rhiza_config(config)
        assert errors == []

    def test_alias_ref_accepted(self, temp_config):
        """Test that 'ref' alias is accepted for 'template-branch'."""
        config = temp_config("""
            template-repository: owner/repo
            ref: main
            include:
              - Makefile
        """)
        errors = validate_rhiza_config(config)
        assert errors == []

    def test_both_aliases_accepted(self, temp_config):
        """Test that both aliases work together."""
        config = temp_config("""
            repository: owner/repo
            ref: main
            templates:
              - core
        """)
        errors = validate_rhiza_config(config)
        assert errors == []

    def test_profiles_alias_accepted(self, temp_config):
        """Test that 'profiles' alias is accepted for 'templates'."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
            profiles:
              - core
              - github
        """)
        errors = validate_rhiza_config(config)
        assert errors == []

    def test_alias_with_invalid_format(self, temp_config):
        """Test that validation still works with aliases."""
        config = temp_config("""
            repository: invalid-format
            ref: main
            include:
              - Makefile
        """)
        errors = validate_rhiza_config(config)
        assert any("owner/repo" in e for e in errors)

    def test_mixed_canonical_and_alias(self, temp_config):
        """Test that mixing canonical and alias names works."""
        config = temp_config("""
            repository: owner/repo
            template-branch: main
            include:
              - Makefile
        """)
        errors = validate_rhiza_config(config)
        assert errors == []

    def test_profiles_alias_not_list(self, temp_config):
        """Test that 'profiles' alias still validates list type."""
        config = temp_config("""
            template-repository: owner/repo
            template-branch: main
            profiles: core
        """)
        errors = validate_rhiza_config(config)
        assert errors == ["templates must be a list"]


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
        """Main returns 1 for invalid config and prints the exact header + error lines."""
        config = temp_config("invalid")
        result = main([str(config)])
        assert result == 1
        captured = capsys.readouterr()
        # Exact stdout pins the "{filename}:" header and the "  - {error}" line.
        assert captured.out == f"{config}:\n  - Configuration must be a YAML mapping\n"

    def test_main_no_files(self) -> None:
        """Main returns 0 when no files provided."""
        result = main([])
        assert result == 0

    def test_help_text(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--help renders the exact argparse description and option help strings."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "XX" not in out  # no mutated literal survived into the rendered help
        assert "Validate .rhiza/template.yml configuration" in out
        assert "Filenames to check" in out


class TestModuleExecution:
    """Tests for module execution via if __name__ == '__main__'."""

    def test_module_executes_main(self) -> None:
        """Module execution calls main and exits with its return value."""
        import runpy
        import sys
        from unittest.mock import patch

        with (
            patch("rhiza_hooks.check_rhiza_config.sys.argv", ["check_rhiza_config"]),
            patch("rhiza_hooks.check_rhiza_config.sys.exit") as mock_exit,
        ):
            # Drop the pre-imported module so runpy executes a fresh copy without
            # the "found in sys.modules ... prior to execution" RuntimeWarning.
            sys.modules.pop("rhiza_hooks.check_rhiza_config", None)
            runpy.run_module("rhiza_hooks.check_rhiza_config", run_name="__main__")
            mock_exit.assert_called_once_with(0)
