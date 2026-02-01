"""Tests for check_rhiza_config hook."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from rhiza_hooks.check_rhiza_config import validate_rhiza_config


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

    def test_missing_required_keys(self, temp_config):
        """Test that missing required keys are reported."""
        config = temp_config("""
            template-branch: main
        """)
        errors = validate_rhiza_config(config)
        assert any("template-repository" in e for e in errors)
        assert any("include" in e for e in errors)

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
