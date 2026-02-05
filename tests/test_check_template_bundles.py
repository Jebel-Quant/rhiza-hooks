"""Tests for check_template_bundles hook."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from rhiza_hooks.check_template_bundles import (
    _load_yaml_file,
    _validate_bundle_structure,
    _validate_examples,
    _validate_metadata,
    _validate_top_level_fields,
    validate_template_bundles,
)


@pytest.fixture
def temp_bundles_file(tmp_path: Path):
    """Create a temporary bundles file."""

    def _create(content: str) -> Path:
        bundles_file = tmp_path / "template-bundles.yml"
        bundles_file.write_text(dedent(content))
        return bundles_file

    return _create


class TestLoadYamlFile:
    """Tests for _load_yaml_file function."""

    def test_load_valid_yaml(self, temp_bundles_file):
        """Test loading valid YAML file."""
        bundles_file = temp_bundles_file("""
            version: 1.0
            bundles: {}
        """)
        success, data = _load_yaml_file(bundles_file)
        assert success is True
        assert isinstance(data, dict)
        assert data["version"] == 1.0

    def test_load_nonexistent_file(self, tmp_path: Path):
        """Test loading non-existent file."""
        bundles_file = tmp_path / "nonexistent.yml"
        success, errors = _load_yaml_file(bundles_file)
        assert success is False
        assert any("not found" in e.lower() for e in errors)

    def test_load_invalid_yaml(self, temp_bundles_file):
        """Test loading invalid YAML."""
        bundles_file = temp_bundles_file("invalid: yaml: syntax:")
        success, errors = _load_yaml_file(bundles_file)
        assert success is False
        assert any("yaml" in e.lower() for e in errors)

    def test_load_empty_file(self, temp_bundles_file):
        """Test loading empty file."""
        bundles_file = temp_bundles_file("")
        success, errors = _load_yaml_file(bundles_file)
        assert success is False
        assert any("empty" in e.lower() for e in errors)


class TestValidateTopLevelFields:
    """Tests for _validate_top_level_fields function."""

    def test_valid_fields(self):
        """Test with all required fields present."""
        data = {"version": 1.0, "bundles": {}}
        errors = _validate_top_level_fields(data)
        assert errors == []

    def test_missing_version(self):
        """Test with missing version field."""
        data = {"bundles": {}}
        errors = _validate_top_level_fields(data)
        assert any("version" in e.lower() for e in errors)

    def test_missing_bundles(self):
        """Test with missing bundles field."""
        data = {"version": 1.0}
        errors = _validate_top_level_fields(data)
        assert any("bundles" in e.lower() for e in errors)

    def test_missing_all_fields(self):
        """Test with all required fields missing."""
        data = {}
        errors = _validate_top_level_fields(data)
        assert len(errors) == 2


class TestValidateBundleStructure:
    """Tests for _validate_bundle_structure function."""

    def test_valid_bundle(self):
        """Test with valid bundle structure."""
        bundle_config = {
            "description": "Test bundle",
            "files": [".gitignore", "README.md"],
        }
        errors = _validate_bundle_structure("test", bundle_config, {"test"})
        assert errors == []

    def test_bundle_not_dict(self):
        """Test with bundle not being a dictionary."""
        errors = _validate_bundle_structure("test", "not-a-dict", {"test"})
        assert any("dictionary" in e.lower() for e in errors)

    def test_missing_description(self):
        """Test with missing description."""
        bundle_config = {"files": [".gitignore"]}
        errors = _validate_bundle_structure("test", bundle_config, {"test"})
        assert any("description" in e.lower() for e in errors)

    def test_missing_files(self):
        """Test with missing files."""
        bundle_config = {"description": "Test bundle"}
        errors = _validate_bundle_structure("test", bundle_config, {"test"})
        assert any("files" in e.lower() for e in errors)

    def test_files_not_list(self):
        """Test with files not being a list."""
        bundle_config = {
            "description": "Test bundle",
            "files": "not-a-list",
        }
        errors = _validate_bundle_structure("test", bundle_config, {"test"})
        assert any("list" in e.lower() for e in errors)

    def test_valid_requires(self):
        """Test with valid requires."""
        bundle_config = {
            "description": "Test bundle",
            "files": [".gitignore"],
            "requires": ["core"],
        }
        errors = _validate_bundle_structure("test", bundle_config, {"test", "core"})
        assert errors == []

    def test_requires_not_list(self):
        """Test with requires not being a list."""
        bundle_config = {
            "description": "Test bundle",
            "files": [".gitignore"],
            "requires": "not-a-list",
        }
        errors = _validate_bundle_structure("test", bundle_config, {"test"})
        assert any("list" in e.lower() for e in errors)

    def test_requires_nonexistent_bundle(self):
        """Test with requires referencing non-existent bundle."""
        bundle_config = {
            "description": "Test bundle",
            "files": [".gitignore"],
            "requires": ["nonexistent"],
        }
        errors = _validate_bundle_structure("test", bundle_config, {"test"})
        assert any("non-existent" in e.lower() for e in errors)

    def test_valid_recommends(self):
        """Test with valid recommends."""
        bundle_config = {
            "description": "Test bundle",
            "files": [".gitignore"],
            "recommends": ["makefile"],
        }
        errors = _validate_bundle_structure("test", bundle_config, {"test", "makefile"})
        assert errors == []

    def test_recommends_not_list(self):
        """Test with recommends not being a list."""
        bundle_config = {
            "description": "Test bundle",
            "files": [".gitignore"],
            "recommends": "not-a-list",
        }
        errors = _validate_bundle_structure("test", bundle_config, {"test"})
        assert any("list" in e.lower() for e in errors)

    def test_recommends_nonexistent_bundle(self):
        """Test with recommends referencing non-existent bundle."""
        bundle_config = {
            "description": "Test bundle",
            "files": [".gitignore"],
            "recommends": ["nonexistent"],
        }
        errors = _validate_bundle_structure("test", bundle_config, {"test"})
        assert any("non-existent" in e.lower() for e in errors)


class TestValidateExamples:
    """Tests for _validate_examples function."""

    def test_valid_examples(self):
        """Test with valid examples."""
        examples = {
            "basic": {
                "templates": ["core", "python"],
            },
        }
        errors = _validate_examples(examples, {"core", "python"})
        assert errors == []

    def test_examples_not_dict(self):
        """Test with examples not being a dictionary."""
        errors = _validate_examples("not-a-dict", {"core"})
        assert any("dictionary" in e.lower() for e in errors)

    def test_templates_not_list(self):
        """Test with templates not being a list."""
        examples = {
            "basic": {
                "templates": "not-a-list",
            },
        }
        errors = _validate_examples(examples, {"core"})
        assert any("list" in e.lower() for e in errors)

    def test_template_references_nonexistent_bundle(self):
        """Test with template referencing non-existent bundle."""
        examples = {
            "basic": {
                "templates": ["core", "nonexistent"],
            },
        }
        errors = _validate_examples(examples, {"core"})
        assert any("non-existent" in e.lower() for e in errors)

    def test_core_template_not_validated(self):
        """Test that 'core' template is not validated."""
        examples = {
            "basic": {
                "templates": ["core"],
            },
        }
        errors = _validate_examples(examples, set())
        assert errors == []


class TestValidateMetadata:
    """Tests for _validate_metadata function."""

    def test_valid_metadata(self):
        """Test with valid metadata."""
        metadata = {"total_bundles": 2}
        bundles = {"bundle1": {}, "bundle2": {}}
        errors = _validate_metadata(metadata, bundles)
        assert errors == []

    def test_mismatched_total_bundles(self):
        """Test with mismatched total_bundles."""
        metadata = {"total_bundles": 5}
        bundles = {"bundle1": {}, "bundle2": {}}
        errors = _validate_metadata(metadata, bundles)
        assert any("doesn't match" in e.lower() for e in errors)

    def test_no_total_bundles_field(self):
        """Test with no total_bundles field."""
        metadata = {}
        bundles = {"bundle1": {}, "bundle2": {}}
        errors = _validate_metadata(metadata, bundles)
        assert errors == []


class TestValidateTemplateBundles:
    """Tests for validate_template_bundles function."""

    def test_valid_config(self, temp_bundles_file):
        """Test with valid configuration."""
        bundles_file = temp_bundles_file("""
            version: 1.0
            bundles:
              core:
                description: Core files
                files:
                  - .gitignore
                  - README.md
              python:
                description: Python files
                requires:
                  - core
                files:
                  - pyproject.toml
            examples:
              basic:
                templates:
                  - core
                  - python
            metadata:
              total_bundles: 2
        """)
        success, errors = validate_template_bundles(bundles_file)
        assert success is True
        assert errors == []

    def test_missing_required_fields(self, temp_bundles_file):
        """Test with missing required fields."""
        bundles_file = temp_bundles_file("""
            bundles: {}
        """)
        success, errors = validate_template_bundles(bundles_file)
        assert success is False
        assert any("version" in e.lower() for e in errors)

    def test_bundles_not_dict(self, temp_bundles_file):
        """Test with bundles not being a dictionary."""
        bundles_file = temp_bundles_file("""
            version: 1.0
            bundles: []
        """)
        success, errors = validate_template_bundles(bundles_file)
        assert success is False
        assert any("dictionary" in e.lower() for e in errors)

    def test_invalid_bundle_structure(self, temp_bundles_file):
        """Test with invalid bundle structure."""
        bundles_file = temp_bundles_file("""
            version: 1.0
            bundles:
              core:
                files:
                  - .gitignore
        """)
        success, errors = validate_template_bundles(bundles_file)
        assert success is False
        assert any("description" in e.lower() for e in errors)

    def test_invalid_dependency(self, temp_bundles_file):
        """Test with invalid dependency."""
        bundles_file = temp_bundles_file("""
            version: 1.0
            bundles:
              python:
                description: Python files
                requires:
                  - nonexistent
                files:
                  - pyproject.toml
        """)
        success, errors = validate_template_bundles(bundles_file)
        assert success is False
        assert any("non-existent" in e.lower() for e in errors)

    def test_invalid_example(self, temp_bundles_file):
        """Test with invalid example."""
        bundles_file = temp_bundles_file("""
            version: 1.0
            bundles:
              core:
                description: Core files
                files:
                  - .gitignore
            examples:
              basic:
                templates:
                  - nonexistent
        """)
        success, errors = validate_template_bundles(bundles_file)
        assert success is False
        assert any("non-existent" in e.lower() for e in errors)

    def test_invalid_metadata(self, temp_bundles_file):
        """Test with invalid metadata."""
        bundles_file = temp_bundles_file("""
            version: 1.0
            bundles:
              core:
                description: Core files
                files:
                  - .gitignore
            metadata:
              total_bundles: 5
        """)
        success, errors = validate_template_bundles(bundles_file)
        assert success is False
        assert any("doesn't match" in e.lower() for e in errors)


class TestMain:
    """Tests for main function."""

    def test_main_with_filename_argument(self, temp_bundles_file):
        """Test main function with filename passed as argument."""
        from rhiza_hooks.check_template_bundles import main

        bundles_file = temp_bundles_file("""
            version: 1.0
            bundles:
              core:
                description: Core files
                files:
                  - .gitignore
        """)

        # Test with valid file
        result = main([str(bundles_file)])
        assert result == 0

    def test_main_with_invalid_file(self, temp_bundles_file):
        """Test main function with invalid file."""
        from rhiza_hooks.check_template_bundles import main

        bundles_file = temp_bundles_file("""
            bundles:
              core:
                files:
                  - .gitignore
        """)

        # Test with invalid file (missing version)
        result = main([str(bundles_file)])
        assert result == 1

    def test_main_with_cwd_default(self, tmp_path, monkeypatch):
        """Test main function uses current working directory when no filename provided."""
        from rhiza_hooks.check_template_bundles import main

        # Create the .rhiza directory structure in tmp_path
        rhiza_dir = tmp_path / ".rhiza"
        rhiza_dir.mkdir()
        bundles_file = rhiza_dir / "template-bundles.yml"
        bundles_file.write_text("""
version: 1.0
bundles:
  core:
    description: Core files
    files:
      - .gitignore
""")

        # Change to the tmp_path directory
        monkeypatch.chdir(tmp_path)

        # Test with no arguments (should use cwd)
        result = main([])
        assert result == 0

    def test_main_with_nonexistent_default_path(self, tmp_path, monkeypatch):
        """Test main function when default path doesn't exist."""
        from rhiza_hooks.check_template_bundles import main

        # Change to a directory without .rhiza/template-bundles.yml
        monkeypatch.chdir(tmp_path)

        # Test with no arguments (file doesn't exist)
        result = main([])
        assert result == 1
