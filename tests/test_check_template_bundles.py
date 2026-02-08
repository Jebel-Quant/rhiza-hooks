"""Tests for check_template_bundles hook."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from rhiza_hooks.check_template_bundles import (
    _get_templates_from_config,
    _load_yaml_file,
    _validate_bundle_structure,
    _validate_examples,
    _validate_metadata,
    _validate_top_level_fields,
    find_repo_root,
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


@pytest.fixture
def valid_bundles_content() -> str:
    """Return valid bundles content for testing."""
    return """
version: 1.0
bundles:
  core:
    description: Core files
    files:
      - .gitignore
"""


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

    def test_nonexistent_file_triggers_assertion(self, tmp_path):
        """Test that nonexistent file triggers the assertion on line 263-264."""
        nonexistent_file = tmp_path / "nonexistent.yml"
        success, errors = validate_template_bundles(nonexistent_file)
        assert success is False
        assert isinstance(errors, list)
        assert len(errors) > 0

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

    def test_main_with_filename_argument(self, temp_bundles_file, valid_bundles_content):
        """Test main function with filename passed as argument."""
        from rhiza_hooks.check_template_bundles import main

        bundles_file = temp_bundles_file(valid_bundles_content)

        # Test with valid file
        result = main([str(bundles_file)])
        assert result == 0

    def test_main_with_invalid_file(self, temp_bundles_file):
        """Test main function with invalid file - skips validation without templates field."""
        from rhiza_hooks.check_template_bundles import main

        bundles_file = temp_bundles_file("""
            bundles:
              core:
                files:
                  - .gitignore
        """)

        # Test with invalid file (missing version) - but no templates field, so skips validation
        result = main([str(bundles_file)])
        assert result == 0

    def test_main_with_invalid_file_and_templates(self, temp_bundles_file, tmp_path, monkeypatch):
        """Test main function with invalid file when templates field exists."""
        from rhiza_hooks.check_template_bundles import main

        # Create template.yml with templates field
        template_file = tmp_path / "template.yml"
        template_file.write_text("""
template-repository: test/repo
template-branch: main
templates:
  - core
""")

        # Mock _fetch_remote_bundles to return invalid bundles (missing version)
        def mock_fetch_remote_bundles(repo, branch):
            return True, {"bundles": {"core": {"files": [".gitignore"]}}}

        monkeypatch.setattr("rhiza_hooks.check_template_bundles._fetch_remote_bundles", mock_fetch_remote_bundles)

        # Test with invalid file (missing version) - should fail validation
        result = main([str(template_file)])
        assert result == 1

    def test_main_with_cwd_default(self, tmp_path, monkeypatch, valid_bundles_content):
        """Test main function uses current working directory when no filename provided."""
        from rhiza_hooks.check_template_bundles import main

        # Create the .rhiza directory structure in tmp_path
        rhiza_dir = tmp_path / ".rhiza"
        rhiza_dir.mkdir()

        # Create template.yml with templates field
        template_file = rhiza_dir / "template.yml"
        template_file.write_text(
            dedent("""
            template-repository: test/repo
            template-branch: main
            templates:
              - core
        """)
        )

        # Mock _fetch_remote_bundles to return valid bundles
        def mock_fetch_remote_bundles(repo, branch):
            return True, {"version": 1.0, "bundles": {"core": {"description": "Core files", "files": [".gitignore"]}}}

        monkeypatch.setattr("rhiza_hooks.check_template_bundles._fetch_remote_bundles", mock_fetch_remote_bundles)

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

        # Test with no arguments (no templates field, should skip validation)
        result = main([])
        assert result == 0

    def test_main_skips_validation_without_templates_field(self, tmp_path, monkeypatch, valid_bundles_content):
        """Test main function skips validation when no templates field in template.yml."""
        from rhiza_hooks.check_template_bundles import main

        # Create the .rhiza directory structure in tmp_path
        rhiza_dir = tmp_path / ".rhiza"
        rhiza_dir.mkdir()
        bundles_file = rhiza_dir / "template-bundles.yml"
        bundles_file.write_text(dedent(valid_bundles_content))

        # Create template.yml WITHOUT templates field (uses include instead)
        template_file = rhiza_dir / "template.yml"
        template_file.write_text(
            dedent("""
            template-repository: test/repo
            template-branch: main
            include:
              - file1
              - file2
        """)
        )

        # Change to the tmp_path directory
        monkeypatch.chdir(tmp_path)

        # Test with no arguments (should skip validation since no templates field)
        result = main([])
        assert result == 0


class TestGetTemplatesFromConfig:
    """Tests for _get_templates_from_config function."""

    def test_get_templates_from_valid_config(self, tmp_path):
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

    def test_get_templates_from_nonexistent_file(self, tmp_path):
        """Test with non-existent config file."""
        config_file = tmp_path / "nonexistent.yml"
        templates = _get_templates_from_config(config_file)
        assert templates is None

    def test_get_templates_from_config_without_templates_field(self, tmp_path):
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

    def test_get_templates_from_invalid_yaml(self, tmp_path):
        """Test with invalid YAML."""
        config_file = tmp_path / "template.yml"
        config_file.write_text("invalid: yaml: syntax:")

        templates = _get_templates_from_config(config_file)
        assert templates is None


class TestValidateTemplateBundlesWithTemplates:
    """Tests for validate_template_bundles with templates filtering."""

    def test_validate_specific_templates(self, temp_bundles_file):
        """Test validating only specific templates."""
        bundles_file = temp_bundles_file("""
            version: 1.0
            bundles:
              core:
                description: Core files
                files:
                  - .gitignore
              python:
                description: Python files
                requires:
                  - core
                files:
                  - pyproject.toml
              makefile:
                description: Makefile
                files:
                  - Makefile
        """)

        # Validate only core and python
        success, errors = validate_template_bundles(bundles_file, {"core", "python"})
        assert success is True
        assert errors == []

    def test_validate_nonexistent_template(self, temp_bundles_file):
        """Test with non-existent template in templates list."""
        bundles_file = temp_bundles_file("""
            version: 1.0
            bundles:
              core:
                description: Core files
                files:
                  - .gitignore
        """)

        # Try to validate a template that doesn't exist
        success, errors = validate_template_bundles(bundles_file, {"core", "nonexistent"})
        assert success is False
        assert any("nonexistent" in e.lower() for e in errors)

    def test_validate_with_invalid_dependency(self, temp_bundles_file):
        """Test validating template with invalid dependency."""
        bundles_file = temp_bundles_file("""
            version: 1.0
            bundles:
              core:
                description: Core files
                files:
                  - .gitignore
              python:
                description: Python files
                requires:
                  - nonexistent
                files:
                  - pyproject.toml
        """)

        # Validate only python, which has invalid dependency
        success, errors = validate_template_bundles(bundles_file, {"python"})
        assert success is False
        assert any("non-existent" in e.lower() for e in errors)

    def test_metadata_not_validated_with_specific_templates(self, temp_bundles_file):
        """Test that metadata is not validated when checking specific templates."""
        bundles_file = temp_bundles_file("""
            version: 1.0
            bundles:
              core:
                description: Core files
                files:
                  - .gitignore
              python:
                description: Python files
                files:
                  - pyproject.toml
            metadata:
              total_bundles: 999
        """)

        # Validate only core - metadata should not be checked
        success, errors = validate_template_bundles(bundles_file, {"core"})
        assert success is True
        assert errors == []


class TestGetTemplatesFromConfigEdgeCases:
    """Tests for edge cases in _get_templates_from_config function."""

    def test_get_templates_from_config_not_dict(self, tmp_path):
        """Test config file that parses to a list instead of dict."""
        config_file = tmp_path / "template.yml"
        config_file.write_text("- item1\n- item2")

        templates = _get_templates_from_config(config_file)
        assert templates is None

    def test_get_templates_from_config_templates_not_list(self, tmp_path):
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


class TestFindRepoRoot:
    """Tests for find_repo_root function."""

    def test_finds_git_directory(self, tmp_path, monkeypatch):
        """Test that find_repo_root finds the .git directory."""
        # Create a .git directory
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        # Create a subdirectory
        sub_dir = tmp_path / "subdir"
        sub_dir.mkdir()

        # Change to the subdirectory
        monkeypatch.chdir(sub_dir)

        # Should find the parent directory with .git
        root = find_repo_root()
        assert root == tmp_path

    def test_returns_cwd_when_no_git_found(self, tmp_path, monkeypatch):
        """Test that find_repo_root returns cwd when no .git directory is found."""
        # Change to a directory without .git
        monkeypatch.chdir(tmp_path)

        # Should return current working directory
        root = find_repo_root()
        assert root == tmp_path


class TestModuleExecution:
    """Tests for module execution."""

    def test_module_executes_main(self, tmp_path, monkeypatch):
        """Test that the module can be executed directly."""
        import subprocess
        import sys

        # Create a valid template.yml with templates field
        rhiza_dir = tmp_path / ".rhiza"
        rhiza_dir.mkdir()
        template_file = rhiza_dir / "template.yml"
        template_file.write_text(
            dedent("""
            template-repository: test/repo
            template-branch: main
            templates:
              - core
        """)
        )

        # Create a mock script that patches _fetch_remote_bundles
        mock_script = tmp_path / "mock_fetch.py"
        mock_script.write_text(
            dedent("""
            import sys
            from unittest.mock import patch

            def mock_fetch_remote_bundles(repo, branch):
                return True, {
                    "version": 1.0,
                    "bundles": {
                        "core": {
                            "description": "Core files",
                            "files": [".gitignore"]
                        }
                    }
                }

            with patch("rhiza_hooks.check_template_bundles._fetch_remote_bundles", mock_fetch_remote_bundles):
                from rhiza_hooks.check_template_bundles import main
                sys.exit(main())
        """)
        )

        # Change to the tmp_path directory
        monkeypatch.chdir(tmp_path)

        # Execute the mock script
        result = subprocess.run(
            [sys.executable, str(mock_script)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0


class TestFetchRemoteBundles:
    """Tests for _fetch_remote_bundles function."""

    def test_fetch_remote_bundles_http_404(self, monkeypatch):
        """Test fetching remote bundles returns 404 error."""
        from urllib.error import HTTPError
        from urllib.request import Request

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        def mock_urlopen(url, timeout):
            raise HTTPError(url, 404, "Not Found", {}, None)

        monkeypatch.setattr("rhiza_hooks.check_template_bundles.urlopen", mock_urlopen)

        success, errors = _fetch_remote_bundles("test/repo", "main")
        assert success is False
        assert any("not found" in e.lower() for e in errors)

    def test_fetch_remote_bundles_http_error_non_404(self, monkeypatch):
        """Test fetching remote bundles with non-404 HTTP error."""
        from urllib.error import HTTPError

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        def mock_urlopen(url, timeout):
            raise HTTPError(url, 500, "Internal Server Error", {}, None)

        monkeypatch.setattr("rhiza_hooks.check_template_bundles.urlopen", mock_urlopen)

        success, errors = _fetch_remote_bundles("test/repo", "main")
        assert success is False
        assert any("500" in e for e in errors)

    def test_fetch_remote_bundles_url_error(self, monkeypatch):
        """Test fetching remote bundles with URL error."""
        from urllib.error import URLError

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        def mock_urlopen(url, timeout):
            raise URLError("Connection refused")

        monkeypatch.setattr("rhiza_hooks.check_template_bundles.urlopen", mock_urlopen)

        success, errors = _fetch_remote_bundles("test/repo", "main")
        assert success is False
        assert any("error fetching" in e.lower() for e in errors)

    def test_fetch_remote_bundles_timeout(self, monkeypatch):
        """Test fetching remote bundles with timeout."""
        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        def mock_urlopen(url, timeout):
            raise TimeoutError("Timeout")

        monkeypatch.setattr("rhiza_hooks.check_template_bundles.urlopen", mock_urlopen)

        success, errors = _fetch_remote_bundles("test/repo", "main")
        assert success is False
        assert any("timeout" in e.lower() for e in errors)

    def test_fetch_remote_bundles_invalid_yaml(self, monkeypatch):
        """Test fetching remote bundles with invalid YAML."""
        from io import BytesIO
        from unittest.mock import MagicMock

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        def mock_urlopen(url, timeout):
            mock_response = MagicMock()
            mock_response.read.return_value = b"invalid: yaml: syntax:"
            mock_response.__enter__ = lambda self: self
            mock_response.__exit__ = lambda self, *args: None
            return mock_response

        monkeypatch.setattr("rhiza_hooks.check_template_bundles.urlopen", mock_urlopen)

        success, errors = _fetch_remote_bundles("test/repo", "main")
        assert success is False
        assert any("invalid yaml" in e.lower() for e in errors)

    def test_fetch_remote_bundles_empty_file(self, monkeypatch):
        """Test fetching remote bundles with empty file."""
        from unittest.mock import MagicMock

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        def mock_urlopen(url, timeout):
            mock_response = MagicMock()
            mock_response.read.return_value = b""
            mock_response.__enter__ = lambda self: self
            mock_response.__exit__ = lambda self, *args: None
            return mock_response

        monkeypatch.setattr("rhiza_hooks.check_template_bundles.urlopen", mock_urlopen)

        success, errors = _fetch_remote_bundles("test/repo", "main")
        assert success is False
        assert any("empty" in e.lower() for e in errors)

    def test_fetch_remote_bundles_not_dict(self, monkeypatch):
        """Test fetching remote bundles that's not a dictionary."""
        from unittest.mock import MagicMock

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        def mock_urlopen(url, timeout):
            mock_response = MagicMock()
            mock_response.read.return_value = b"- item1\n- item2"
            mock_response.__enter__ = lambda self: self
            mock_response.__exit__ = lambda self, *args: None
            return mock_response

        monkeypatch.setattr("rhiza_hooks.check_template_bundles.urlopen", mock_urlopen)

        success, errors = _fetch_remote_bundles("test/repo", "main")
        assert success is False
        assert any("dictionary" in e.lower() for e in errors)

    def test_fetch_remote_bundles_invalid_scheme(self, monkeypatch):
        """Test fetching remote bundles with invalid URL scheme."""
        from urllib.parse import ParseResult

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        def mock_urlparse(url):
            # Return a parsed URL with http scheme instead of https
            return ParseResult(scheme="http", netloc="raw.githubusercontent.com", path="", params="", query="", fragment="")

        monkeypatch.setattr("rhiza_hooks.check_template_bundles.urlparse", mock_urlparse)

        success, errors = _fetch_remote_bundles("test/repo", "main")
        assert success is False
        assert any("invalid url scheme" in e.lower() for e in errors)

    def test_fetch_remote_bundles_success(self, monkeypatch):
        """Test successful fetching of remote bundles."""
        from unittest.mock import MagicMock

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        def mock_urlopen(url, timeout):
            mock_response = MagicMock()
            mock_response.read.return_value = b"version: 1.0\nbundles:\n  core:\n    description: Core\n    files:\n      - .gitignore"
            mock_response.__enter__ = lambda self: self
            mock_response.__exit__ = lambda self, *args: None
            return mock_response

        monkeypatch.setattr("rhiza_hooks.check_template_bundles.urlopen", mock_urlopen)

        success, data = _fetch_remote_bundles("test/repo", "main")
        assert success is True
        assert isinstance(data, dict)
        assert "version" in data
        assert "bundles" in data


class TestMainErrorPaths:
    """Tests for main function error paths."""

    def test_main_missing_template_repository(self, tmp_path, monkeypatch):
        """Test main function when template-repository is missing."""
        from rhiza_hooks.check_template_bundles import main

        # Create the .rhiza directory structure
        rhiza_dir = tmp_path / ".rhiza"
        rhiza_dir.mkdir()

        # Create template.yml with templates but missing template-repository
        template_file = rhiza_dir / "template.yml"
        template_file.write_text(
            dedent("""
            template-branch: main
            templates:
              - core
        """)
        )

        # Change to the tmp_path directory
        monkeypatch.chdir(tmp_path)

        # Test with no arguments - should fail due to missing template-repository
        result = main([])
        assert result == 1

    def test_main_missing_template_branch(self, tmp_path, monkeypatch):
        """Test main function when template-branch is missing."""
        from rhiza_hooks.check_template_bundles import main

        # Create the .rhiza directory structure
        rhiza_dir = tmp_path / ".rhiza"
        rhiza_dir.mkdir()

        # Create template.yml with templates but missing template-branch
        template_file = rhiza_dir / "template.yml"
        template_file.write_text(
            dedent("""
            template-repository: test/repo
            templates:
              - core
        """)
        )

        # Change to the tmp_path directory
        monkeypatch.chdir(tmp_path)

        # Test with no arguments - should fail due to missing template-branch
        result = main([])
        assert result == 1

    def test_main_fetch_remote_fails(self, tmp_path, monkeypatch):
        """Test main function when fetching remote bundles fails."""
        from rhiza_hooks.check_template_bundles import main

        # Create the .rhiza directory structure
        rhiza_dir = tmp_path / ".rhiza"
        rhiza_dir.mkdir()

        # Create template.yml with templates field
        template_file = rhiza_dir / "template.yml"
        template_file.write_text(
            dedent("""
            template-repository: test/repo
            template-branch: main
            templates:
              - core
        """)
        )

        # Mock _fetch_remote_bundles to return failure
        def mock_fetch_remote_bundles(repo, branch):
            return False, ["Failed to fetch remote bundles"]

        monkeypatch.setattr("rhiza_hooks.check_template_bundles._fetch_remote_bundles", mock_fetch_remote_bundles)

        # Change to the tmp_path directory
        monkeypatch.chdir(tmp_path)

        # Test with no arguments - should fail
        result = main([])
        assert result == 1

    def test_main_bundles_not_dict(self, tmp_path, monkeypatch):
        """Test main function when bundles is not a dict in remote data."""
        from rhiza_hooks.check_template_bundles import main

        # Create the .rhiza directory structure
        rhiza_dir = tmp_path / ".rhiza"
        rhiza_dir.mkdir()

        # Create template.yml with templates field
        template_file = rhiza_dir / "template.yml"
        template_file.write_text(
            dedent("""
            template-repository: test/repo
            template-branch: main
            templates:
              - core
        """)
        )

        # Mock _fetch_remote_bundles to return bundles as a list instead of dict
        def mock_fetch_remote_bundles(repo, branch):
            return True, {"version": 1.0, "bundles": []}

        monkeypatch.setattr("rhiza_hooks.check_template_bundles._fetch_remote_bundles", mock_fetch_remote_bundles)

        # Change to the tmp_path directory
        monkeypatch.chdir(tmp_path)

        # Test with no arguments - should fail
        result = main([])
        assert result == 1

    def test_main_template_not_in_bundles(self, tmp_path, monkeypatch):
        """Test main function when requested template is not in remote bundles."""
        from rhiza_hooks.check_template_bundles import main

        # Create the .rhiza directory structure
        rhiza_dir = tmp_path / ".rhiza"
        rhiza_dir.mkdir()

        # Create template.yml with templates field
        template_file = rhiza_dir / "template.yml"
        template_file.write_text(
            dedent("""
            template-repository: test/repo
            template-branch: main
            templates:
              - core
              - nonexistent
        """)
        )

        # Mock _fetch_remote_bundles to return bundles without the requested template
        def mock_fetch_remote_bundles(repo, branch):
            return True, {
                "version": 1.0,
                "bundles": {"core": {"description": "Core files", "files": [".gitignore"]}},
            }

        monkeypatch.setattr("rhiza_hooks.check_template_bundles._fetch_remote_bundles", mock_fetch_remote_bundles)

        # Change to the tmp_path directory
        monkeypatch.chdir(tmp_path)

        # Test with no arguments - should fail
        result = main([])
        assert result == 1

    def test_main_invalid_bundle_structure_in_remote(self, tmp_path, monkeypatch):
        """Test main function when remote bundle has invalid structure."""
        from rhiza_hooks.check_template_bundles import main

        # Create the .rhiza directory structure
        rhiza_dir = tmp_path / ".rhiza"
        rhiza_dir.mkdir()

        # Create template.yml with templates field
        template_file = rhiza_dir / "template.yml"
        template_file.write_text(
            dedent("""
            template-repository: test/repo
            template-branch: main
            templates:
              - core
        """)
        )

        # Mock _fetch_remote_bundles to return invalid bundle structure (missing description)
        def mock_fetch_remote_bundles(repo, branch):
            return True, {"version": 1.0, "bundles": {"core": {"files": [".gitignore"]}}}

        monkeypatch.setattr("rhiza_hooks.check_template_bundles._fetch_remote_bundles", mock_fetch_remote_bundles)

        # Change to the tmp_path directory
        monkeypatch.chdir(tmp_path)

        # Test with no arguments - should fail
        result = main([])
        assert result == 1


class TestMainNameBlock:
    """Tests for the if __name__ == '__main__' block."""

    def test_main_name_block_execution(self, tmp_path):
        """Test that the module can be run as __main__."""
        import subprocess
        import sys

        # Create a temporary directory with a .rhiza/template.yml that won't trigger validation
        rhiza_dir = tmp_path / ".rhiza"
        rhiza_dir.mkdir()
        template_file = rhiza_dir / "template.yml"
        template_file.write_text("# No templates field")

        # Run the module as __main__ using python -m
        result = subprocess.run(
            [sys.executable, "-m", "rhiza_hooks.check_template_bundles"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

    def test_main_name_block_with_runpy(self, tmp_path, monkeypatch):
        """Test the __main__ block using runpy to maintain coverage."""
        import runpy
        import sys

        # Create a temporary directory with a .rhiza/template.yml that won't trigger validation
        rhiza_dir = tmp_path / ".rhiza"
        rhiza_dir.mkdir()
        template_file = rhiza_dir / "template.yml"
        template_file.write_text("# No templates field")

        # Change to the tmp_path directory
        monkeypatch.chdir(tmp_path)

        # Mock sys.argv to simulate command-line execution
        original_argv = sys.argv
        sys.argv = ["rhiza_hooks.check_template_bundles"]

        try:
            # Run the module as __main__ using runpy
            runpy.run_module("rhiza_hooks.check_template_bundles", run_name="__main__")
        except SystemExit as e:
            # The module calls sys.exit(), which we expect
            assert e.code == 0
        finally:
            sys.argv = original_argv
