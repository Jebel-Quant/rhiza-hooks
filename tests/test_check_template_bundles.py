"""Tests for check_template_bundles hook."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from rhiza_hooks.check_template_bundles import (
    BundlesDoc,
    _get_templates_from_config,
    _load_and_validate_config,
    _load_yaml_file,
    _validate_bundle_structure,
    _validate_examples,
    _validate_metadata,
    _validate_remote_bundles,
    _validate_templates_in_bundles,
    _validate_top_level_fields,
    find_repo_root,
    main,
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


class TestBundlesDoc:
    """Tests for the BundlesDoc result type."""

    def test_is_frozen(self):
        """BundlesDoc is immutable: attribute assignment raises (pins frozen=True)."""
        import dataclasses

        doc = BundlesDoc(None, [])
        with pytest.raises(dataclasses.FrozenInstanceError):
            doc.data = {}  # type: ignore[misc]


class TestLoadYamlFile:
    """Tests for _load_yaml_file function."""

    def test_load_valid_yaml(self, temp_bundles_file):
        """Test loading valid YAML file."""
        bundles_file = temp_bundles_file("""
            version: 1.0
            bundles: {}
        """)
        result = _load_yaml_file(bundles_file)
        assert isinstance(result.data, dict)
        assert result.data["version"] == 1.0
        assert result.errors == []

    def test_load_nonexistent_file(self, tmp_path: Path):
        """Test loading non-existent file reports the exact message."""
        bundles_file = tmp_path / "nonexistent.yml"
        result = _load_yaml_file(bundles_file)
        assert result.data is None
        assert result.errors == [f"Template bundles file not found: {bundles_file}"]

    def test_load_invalid_yaml(self, temp_bundles_file):
        """Test loading invalid YAML reports the exact prefix."""
        bundles_file = temp_bundles_file("invalid: yaml: syntax:")
        result = _load_yaml_file(bundles_file)
        assert result.data is None
        assert len(result.errors) == 1
        assert result.errors[0].startswith("Invalid YAML: ")

    def test_load_empty_file(self, temp_bundles_file):
        """Test loading empty file reports the exact message."""
        bundles_file = temp_bundles_file("")
        result = _load_yaml_file(bundles_file)
        assert result.data is None
        assert result.errors == ["Template bundles file is empty"]


class TestValidateTopLevelFields:
    """Tests for _validate_top_level_fields function."""

    def test_valid_fields(self):
        """Test with all required fields present."""
        data = {"version": 1.0, "bundles": {}}
        errors = _validate_top_level_fields(data)
        assert errors == []

    def test_missing_version(self):
        """Test with missing version field reports the exact message."""
        data = {"bundles": {}}
        errors = _validate_top_level_fields(data)
        assert errors == ["Missing required field: version"]

    def test_missing_bundles(self):
        """Test with missing bundles field reports the exact message."""
        data = {"version": 1.0}
        errors = _validate_top_level_fields(data)
        assert errors == ["Missing required field: bundles"]

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
        """Test with bundle not being a dictionary reports the exact message."""
        errors = _validate_bundle_structure("test", "not-a-dict", {"test"})
        assert errors == ["Bundle 'test' must be a dictionary"]

    def test_missing_description(self):
        """Test with missing description reports the exact message."""
        bundle_config = {"files": [".gitignore"]}
        errors = _validate_bundle_structure("test", bundle_config, {"test"})
        assert errors == ["Bundle 'test' missing 'description'"]

    def test_missing_files(self):
        """Test with missing files reports the exact message."""
        bundle_config = {"description": "Test bundle"}
        errors = _validate_bundle_structure("test", bundle_config, {"test"})
        assert errors == ["Bundle 'test' missing 'files'"]

    def test_files_not_list(self):
        """Test with files not being a list reports the exact message."""
        bundle_config = {
            "description": "Test bundle",
            "files": "not-a-list",
        }
        errors = _validate_bundle_structure("test", bundle_config, {"test"})
        assert errors == ["Bundle 'test' 'files' must be a list"]

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
        assert errors == ["Bundle 'test' 'requires' must be a list"]

    def test_requires_nonexistent_bundle(self):
        """Test with requires referencing non-existent bundle reports the exact message."""
        bundle_config = {
            "description": "Test bundle",
            "files": [".gitignore"],
            "requires": ["nonexistent"],
        }
        errors = _validate_bundle_structure("test", bundle_config, {"test"})
        assert errors == ["Bundle 'test' requires non-existent bundle 'nonexistent'"]

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
        assert errors == ["Bundle 'test' 'recommends' must be a list"]

    def test_recommends_nonexistent_bundle(self):
        """Test with recommends referencing non-existent bundle reports the exact message."""
        bundle_config = {
            "description": "Test bundle",
            "files": [".gitignore"],
            "recommends": ["nonexistent"],
        }
        errors = _validate_bundle_structure("test", bundle_config, {"test"})
        assert errors == ["Bundle 'test' recommends non-existent bundle 'nonexistent'"]


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
        """Test with examples not being a dictionary reports the exact message."""
        errors = _validate_examples("not-a-dict", {"core"})
        assert errors == ["'examples' must be a dictionary"]

    def test_templates_not_list(self):
        """Test with templates not being a list reports the exact message."""
        examples = {
            "basic": {
                "templates": "not-a-list",
            },
        }
        errors = _validate_examples(examples, {"core"})
        assert errors == ["Example 'basic' 'templates' must be a list"]

    def test_template_references_nonexistent_bundle(self):
        """Test with template referencing non-existent bundle reports the exact message."""
        examples = {
            "basic": {
                "templates": ["core", "nonexistent"],
            },
        }
        errors = _validate_examples(examples, {"core"})
        assert errors == ["Example 'basic' references non-existent bundle 'nonexistent'"]

    def test_core_template_not_validated(self):
        """Test that 'core' template is not validated."""
        examples = {
            "basic": {
                "templates": ["core"],
            },
        }
        errors = _validate_examples(examples, set())
        assert errors == []

    def test_example_without_templates_key(self):
        """An example with no 'templates' key is skipped without error."""
        examples = {
            "basic": {"description": "no templates listed"},
        }
        errors = _validate_examples(examples, {"core"})
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
        """Test with mismatched total_bundles reports the exact message."""
        metadata = {"total_bundles": 5}
        bundles = {"bundle1": {}, "bundle2": {}}
        errors = _validate_metadata(metadata, bundles)
        assert errors == ["Metadata 'total_bundles' (5) doesn't match actual bundle count (2)"]

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
        assert errors == ["'bundles' must be a dictionary"]

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
        def mock_fetch_remote_bundles(repo, branch, **kwargs):
            return BundlesDoc({"bundles": {"core": {"files": [".gitignore"]}}}, [])

        monkeypatch.setattr("rhiza_hooks.check_template_bundles._fetch_remote_bundles", mock_fetch_remote_bundles)

        # Test with invalid file (missing version) - should fail validation
        result = main([str(template_file)])
        assert result == 1

    def test_main_with_cwd_default(self, tmp_path, monkeypatch, valid_bundles_content, capsys):
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
        def mock_fetch_remote_bundles(repo, branch, **kwargs):
            return BundlesDoc(
                {"version": 1.0, "bundles": {"core": {"description": "Core files", "files": [".gitignore"]}}}, []
            )

        monkeypatch.setattr("rhiza_hooks.check_template_bundles._fetch_remote_bundles", mock_fetch_remote_bundles)

        # Change to the tmp_path directory
        monkeypatch.chdir(tmp_path)

        # Test with no arguments (should use cwd)
        result = main([])
        assert result == 0
        # Exact success line (splitlines membership rejects a mutated wrapper).
        assert "✓ Template bundles validation passed!" in capsys.readouterr().out.splitlines()

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
        assert errors == ["Template 'nonexistent' specified in .rhiza/template.yml not found in bundles"]

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
        import subprocess  # nosec B404
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

            from rhiza_hooks.check_template_bundles import BundlesDoc

            def mock_fetch_remote_bundles(repo, branch, **kwargs):
                return BundlesDoc(
                    {
                        "version": 1.0,
                        "bundles": {
                            "core": {
                                "description": "Core files",
                                "files": [".gitignore"]
                            }
                        }
                    },
                    [],
                )

            with patch("rhiza_hooks.check_template_bundles._fetch_remote_bundles", mock_fetch_remote_bundles):
                from rhiza_hooks.check_template_bundles import main
                sys.exit(main())
        """)
        )

        # Change to the tmp_path directory
        monkeypatch.chdir(tmp_path)

        # Execute the mock script
        result = subprocess.run(  # nosec B603
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

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        def mock_urlopen(url, timeout):
            raise HTTPError(url, 404, "Not Found", {}, None)

        monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)

        result = _fetch_remote_bundles("test/repo", "main")
        assert result.data is None
        assert result.errors == ["Template bundles file not found in repository test/repo (branch: main)"]

    def test_fetch_remote_bundles_http_error_non_404(self, monkeypatch):
        """Test fetching remote bundles with non-404 HTTP error."""
        from urllib.error import HTTPError

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        def mock_urlopen(url, timeout):
            raise HTTPError(url, 500, "Internal Server Error", {}, None)

        monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)

        result = _fetch_remote_bundles("test/repo", "main")
        assert result.data is None
        assert result.errors == ["HTTP error fetching template bundles: 500 Internal Server Error"]

    def test_fetch_remote_bundles_url_error(self, monkeypatch):
        """A persistent URL error gives up after the default attempts, retrying once."""
        from unittest.mock import MagicMock
        from urllib.error import URLError

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        calls = MagicMock(side_effect=URLError("Connection refused"))

        def mock_urlopen(url, timeout):
            return calls(url, timeout)

        sleep = MagicMock()
        monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)
        monkeypatch.setattr("rhiza_hooks._bundles_fetch.time.sleep", sleep)

        result = _fetch_remote_bundles("test/repo", "main")
        assert result.data is None
        url = "https://raw.githubusercontent.com/test/repo/main/.rhiza/template-bundles.yml"
        assert result.errors == [f"Error fetching template bundles from {url}: Connection refused"]
        # Default = 2 attempts (1 retry): urlopen twice, one backoff sleep of 1.0s.
        assert calls.call_count == 2
        assert sleep.call_args_list == [((1.0,), {})]

    def test_fetch_remote_bundles_timeout(self, monkeypatch):
        """A persistent timeout gives up after the default attempts with the exact message."""
        from unittest.mock import MagicMock

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        calls = MagicMock(side_effect=TimeoutError("Timeout"))

        def mock_urlopen(url, timeout):
            return calls(url, timeout)

        sleep = MagicMock()
        monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)
        monkeypatch.setattr("rhiza_hooks._bundles_fetch.time.sleep", sleep)

        result = _fetch_remote_bundles("test/repo", "main")
        assert result.data is None
        url = "https://raw.githubusercontent.com/test/repo/main/.rhiza/template-bundles.yml"
        assert result.errors == [f"Timeout fetching template bundles from {url}"]
        assert calls.call_count == 2
        assert sleep.call_args_list == [((1.0,), {})]

    def test_fetch_remote_bundles_retry_then_success(self, monkeypatch):
        """A transient failure followed by success returns the parsed data after one retry."""
        from unittest.mock import MagicMock
        from urllib.error import URLError

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        def make_response():
            resp = MagicMock()
            resp.read.return_value = b"version: 1.0\nbundles: {}"
            resp.__enter__ = lambda self: self
            resp.__exit__ = lambda self, *args: None
            return resp

        calls = MagicMock(side_effect=[URLError("flaky"), make_response()])

        def mock_urlopen(url, timeout):
            return calls(url, timeout)

        sleep = MagicMock()
        monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)
        monkeypatch.setattr("rhiza_hooks._bundles_fetch.time.sleep", sleep)

        result = _fetch_remote_bundles("test/repo", "main")
        assert result.data == {"version": 1.0, "bundles": {}}
        assert result.errors == []
        assert calls.call_count == 2
        assert sleep.call_args_list == [((1.0,), {})]

    def test_fetch_remote_bundles_backoff_schedule(self, monkeypatch):
        """Backoff is linear (backoff, 2*backoff, ...) and the last attempt does not sleep."""
        from unittest.mock import MagicMock
        from urllib.error import URLError

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        calls = MagicMock(side_effect=URLError("down"))

        def mock_urlopen(url, timeout):
            return calls(url, timeout)

        sleep = MagicMock()
        monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)
        monkeypatch.setattr("rhiza_hooks._bundles_fetch.time.sleep", sleep)

        result = _fetch_remote_bundles("test/repo", "main", attempts=3, backoff=2.0)
        assert result.data is None
        # 3 attempts -> 2 sleeps between them: 2.0 then 4.0. No sleep after the final attempt.
        assert calls.call_count == 3
        assert sleep.call_args_list == [((2.0,), {}), ((4.0,), {})]

    def test_fetch_remote_bundles_invalid_yaml(self, monkeypatch):
        """Test fetching remote bundles with invalid YAML."""
        from unittest.mock import MagicMock

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        def mock_urlopen(url, timeout):
            mock_response = MagicMock()
            mock_response.read.return_value = b"invalid: yaml: syntax:"
            mock_response.__enter__ = lambda self: self
            mock_response.__exit__ = lambda self, *args: None
            return mock_response

        monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)

        result = _fetch_remote_bundles("test/repo", "main")
        assert result.data is None
        assert len(result.errors) == 1
        assert result.errors[0].startswith("Invalid YAML in remote template bundles: ")

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

        monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)

        result = _fetch_remote_bundles("test/repo", "main")
        assert result.data is None
        assert result.errors == ["Remote template bundles file is empty"]

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

        monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)

        result = _fetch_remote_bundles("test/repo", "main")
        assert result.data is None
        assert result.errors == ["Remote template bundles must be a dictionary"]

    def test_fetch_remote_bundles_invalid_scheme(self, monkeypatch):
        """Test fetching remote bundles with invalid URL scheme."""
        from urllib.parse import ParseResult

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        def mock_urlparse(url):
            # Return a parsed URL with http scheme instead of https
            return ParseResult(
                scheme="http", netloc="raw.githubusercontent.com", path="", params="", query="", fragment=""
            )

        monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlparse", mock_urlparse)

        result = _fetch_remote_bundles("test/repo", "main")
        assert result.data is None
        assert result.errors == ["Invalid URL scheme: http. Only https is allowed."]

    def test_fetch_remote_bundles_success(self, monkeypatch):
        """Test successful fetching of remote bundles."""
        from unittest.mock import MagicMock

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        seen = {}

        def mock_urlopen(url, timeout):
            seen["timeout"] = timeout
            mock_response = MagicMock()
            mock_response.read.return_value = (
                b"version: 1.0\nbundles:\n  core:\n    description: Core\n    files:\n      - .gitignore"
            )
            mock_response.__enter__ = lambda self: self
            mock_response.__exit__ = lambda self, *args: None
            return mock_response

        monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)

        result = _fetch_remote_bundles("test/repo", "main")
        assert isinstance(result.data, dict)
        assert "version" in result.data
        assert "bundles" in result.data
        assert result.errors == []
        # Pin the request timeout so a mutated value is caught.
        assert seen["timeout"] == 10

    def test_fetch_remote_bundles_custom_timeout(self, monkeypatch):
        """A custom timeout is forwarded to urlopen verbatim."""
        from unittest.mock import MagicMock

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        seen = {}

        def mock_urlopen(url, timeout):
            seen["timeout"] = timeout
            resp = MagicMock()
            resp.read.return_value = b"version: 1.0\nbundles: {}"
            resp.__enter__ = lambda self: self
            resp.__exit__ = lambda self, *args: None
            return resp

        monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)

        _fetch_remote_bundles("test/repo", "main", timeout=42.5)
        assert seen["timeout"] == 42.5

    def test_fetch_remote_bundles_no_retries(self, monkeypatch):
        """attempts=1 makes a single request and never sleeps."""
        from unittest.mock import MagicMock
        from urllib.error import URLError

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        calls = MagicMock(side_effect=URLError("down"))

        def mock_urlopen(url, timeout):
            return calls(url, timeout)

        sleep = MagicMock()
        monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)
        monkeypatch.setattr("rhiza_hooks._bundles_fetch.time.sleep", sleep)

        result = _fetch_remote_bundles("test/repo", "main", attempts=1)
        assert result.data is None
        assert calls.call_count == 1
        assert sleep.call_args_list == []

    def test_fetch_remote_bundles_logs_each_attempt(self, monkeypatch, capsys):
        """Every failed attempt is logged; retried ones mention the backoff delay."""
        from unittest.mock import MagicMock
        from urllib.error import URLError

        from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

        calls = MagicMock(side_effect=URLError("down"))

        def mock_urlopen(url, timeout):
            return calls(url, timeout)

        monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)
        monkeypatch.setattr("rhiza_hooks._bundles_fetch.time.sleep", MagicMock())

        _fetch_remote_bundles("test/repo", "main", attempts=2, backoff=1.0)
        out = capsys.readouterr().out
        assert "Attempt 1/2 failed" in out
        assert "retrying in 1.0s" in out
        # The final attempt is logged but has nothing to retry.
        assert "Attempt 2/2 failed" in out
        assert "Attempt 2/2 failed: " in out
        assert out.count("retrying in") == 1


class TestMainErrorPaths:
    """Tests for main function error paths."""

    def test_main_missing_template_repository(self, tmp_path, monkeypatch, capsys):
        """Test main function when template-repository is missing prints the exact message."""
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

        # A fetch stub guards against the mutant branch attempting a real network call.
        monkeypatch.setattr(
            "rhiza_hooks.check_template_bundles._fetch_remote_bundles",
            lambda repo, branch, **kwargs: BundlesDoc(None, ["stub"]),
        )
        # Change to the tmp_path directory
        monkeypatch.chdir(tmp_path)

        # Test with no arguments - should fail early due to missing template-repository,
        # printing the exact message *before* any fetch is attempted.
        result = main([])
        assert result == 1
        config_path = tmp_path / ".rhiza" / "template.yml"
        assert (
            f"Missing template-repository or template-branch in {config_path}" in capsys.readouterr().out.splitlines()
        )

    def test_main_missing_template_branch(self, tmp_path, monkeypatch, capsys):
        """Test main function when template-branch is missing prints the exact message."""
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

        monkeypatch.setattr(
            "rhiza_hooks.check_template_bundles._fetch_remote_bundles",
            lambda repo, branch, **kwargs: BundlesDoc(None, ["stub"]),
        )
        # Change to the tmp_path directory
        monkeypatch.chdir(tmp_path)

        # Test with no arguments - should fail due to missing template-branch
        result = main([])
        assert result == 1
        config_path = tmp_path / ".rhiza" / "template.yml"
        assert (
            f"Missing template-repository or template-branch in {config_path}" in capsys.readouterr().out.splitlines()
        )

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
        def mock_fetch_remote_bundles(repo, branch, **kwargs):
            return BundlesDoc(None, ["Failed to fetch remote bundles"])

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
        def mock_fetch_remote_bundles(repo, branch, **kwargs):
            return BundlesDoc({"version": 1.0, "bundles": []}, [])

        monkeypatch.setattr("rhiza_hooks.check_template_bundles._fetch_remote_bundles", mock_fetch_remote_bundles)

        # Change to the tmp_path directory
        monkeypatch.chdir(tmp_path)

        # Test with no arguments - should fail
        result = main([])
        assert result == 1

    def test_main_template_not_in_bundles(self, tmp_path, monkeypatch, capsys):
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
        def mock_fetch_remote_bundles(repo, branch, **kwargs):
            return BundlesDoc(
                {
                    "version": 1.0,
                    "bundles": {"core": {"description": "Core files", "files": [".gitignore"]}},
                },
                [],
            )

        monkeypatch.setattr("rhiza_hooks.check_template_bundles._fetch_remote_bundles", mock_fetch_remote_bundles)

        # Change to the tmp_path directory
        monkeypatch.chdir(tmp_path)

        # Test with no arguments - should fail
        result = main([])
        assert result == 1
        # Exact failure header + bullet lines (splitlines membership rejects mutated wrappers).
        config_path = tmp_path / ".rhiza" / "template.yml"
        lines = capsys.readouterr().out.splitlines()
        assert "✗ Template bundles validation failed:" in lines
        assert f"  - Template 'nonexistent' specified in {config_path} not found in remote bundles" in lines

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
        def mock_fetch_remote_bundles(repo, branch, **kwargs):
            return BundlesDoc({"version": 1.0, "bundles": {"core": {"files": [".gitignore"]}}}, [])

        monkeypatch.setattr("rhiza_hooks.check_template_bundles._fetch_remote_bundles", mock_fetch_remote_bundles)

        # Change to the tmp_path directory
        monkeypatch.chdir(tmp_path)

        # Test with no arguments - should fail
        result = main([])
        assert result == 1


class TestMainStdout:
    """Tests for main()'s stdout-encoding guard."""

    def test_main_with_non_textiowrapper_stdout(self, tmp_path, monkeypatch):
        """main() skips reconfigure when stdout is not a TextIOWrapper."""
        import io

        from rhiza_hooks.check_template_bundles import main

        rhiza_dir = tmp_path / ".rhiza"
        rhiza_dir.mkdir()
        (rhiza_dir / "template.yml").write_text("# No templates field")
        monkeypatch.chdir(tmp_path)

        # io.StringIO is not a TextIOWrapper, so the reconfigure branch is skipped.
        monkeypatch.setattr("sys.stdout", io.StringIO())
        assert main([]) == 0


class TestMainNameBlock:
    """Tests for the if __name__ == '__main__' block."""

    def test_main_name_block_execution(self, tmp_path):
        """Test that the module can be run as __main__."""
        import subprocess  # nosec B404
        import sys

        # Create a temporary directory with a .rhiza/template.yml that won't trigger validation
        rhiza_dir = tmp_path / ".rhiza"
        rhiza_dir.mkdir()
        template_file = rhiza_dir / "template.yml"
        template_file.write_text("# No templates field")

        # Run the module as __main__ using python -m
        result = subprocess.run(  # nosec B603
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
            # Run the module as __main__ using runpy - it should exit with code 0
            with pytest.raises(SystemExit) as exc_info:
                runpy.run_module("rhiza_hooks.check_template_bundles", run_name="__main__")
            assert exc_info.value.code == 0
        finally:
            sys.argv = original_argv


_MOD = "rhiza_hooks.check_template_bundles"


class TestValidateRemoteBundles:
    """Tests for _validate_remote_bundles (exercises its progress/failure prints)."""

    def test_success_prints_progress(self, monkeypatch, capsys):
        """Successful fetch+validate prints the exact 'Fetching'/'Checking' lines."""
        monkeypatch.setattr(
            f"{_MOD}._fetch_remote_bundles",
            lambda repo, branch, **kwargs: BundlesDoc(
                {"version": 1.0, "bundles": {"core": {"description": "d", "files": ["f"]}}}, []
            ),
        )
        data, errors = _validate_remote_bundles("test/repo", "main", {"core", "python"}, Path("cfg"))
        assert data is not None
        assert errors == []
        # Exact stdout pins both lines and the ', ' join separator (sorted templates).
        assert capsys.readouterr().out == (
            "Fetching template bundles from test/repo (branch: main)\nChecking templates: core, python\n"
        )

    def test_fetch_failure_prints_errors(self, monkeypatch, capsys):
        """A failed fetch prints the exact failure header and bullet, returning (None, errors)."""
        monkeypatch.setattr(f"{_MOD}._fetch_remote_bundles", lambda repo, branch, **kwargs: BundlesDoc(None, ["boom"]))
        data, errors = _validate_remote_bundles("test/repo", "main", {"core"}, Path("cfg"))
        assert data is None
        assert errors == ["boom"]
        assert capsys.readouterr().out == (
            "Fetching template bundles from test/repo (branch: main)\n"
            "Checking templates: core\n"
            "\n✗ Failed to fetch template bundles:\n"
            "  - boom\n"
        )

    def test_invalid_top_level_returns_none(self, monkeypatch, capsys):
        """Remote data missing 'version' fails: returns (None, errors), not (data, [])."""
        monkeypatch.setattr(
            f"{_MOD}._fetch_remote_bundles", lambda repo, branch, **kwargs: BundlesDoc({"bundles": {}}, [])
        )
        data, errors = _validate_remote_bundles("test/repo", "main", {"core"}, Path("cfg"))
        # data is None pins `errors = _validate_top_level_fields(data)` (vs the `errors = None` mutant).
        assert data is None
        assert errors == ["Missing required field: version"]
        lines = capsys.readouterr().out.splitlines()
        assert "✗ Template bundles validation failed:" in lines
        assert "  - Missing required field: version" in lines

    def test_bundles_not_dict_returns_none(self, monkeypatch, capsys):
        """Remote 'bundles' not a dict fails with the exact header and bullet."""
        monkeypatch.setattr(
            f"{_MOD}._fetch_remote_bundles",
            lambda repo, branch, **kwargs: BundlesDoc({"version": 1.0, "bundles": []}, []),
        )
        data, errors = _validate_remote_bundles("test/repo", "main", {"core"}, Path("cfg"))
        assert data is None
        assert errors == ["'bundles' must be a dictionary"]
        lines = capsys.readouterr().out.splitlines()
        assert "✗ Template bundles validation failed:" in lines
        assert "  - 'bundles' must be a dictionary" in lines


class TestValidateTemplatesInBundles:
    """Tests for _validate_templates_in_bundles."""

    def test_missing_template_exact_message(self):
        """A requested template absent from remote bundles yields the exact message."""
        errors = _validate_templates_in_bundles(
            {"nonexistent"}, {"core": {"description": "d", "files": ["f"]}}, Path("cfg")
        )
        assert errors == ["Template 'nonexistent' specified in cfg not found in remote bundles"]


class TestLoadAndValidateConfig:
    """Tests for _load_and_validate_config."""

    def test_missing_config_prints_and_returns_none(self, tmp_path, capsys):
        """A missing config file prints the exact skip message and returns (None, None)."""
        missing = tmp_path / "template.yml"
        config, templates = _load_and_validate_config(missing)
        assert config is None
        assert templates is None
        assert capsys.readouterr().out == f"Could not load configuration from {missing}, skipping validation\n"

    def test_templates_not_list_returns_none(self, tmp_path, capsys):
        """A non-list 'templates' field skips validation (pins the `or` in the guard)."""
        cfg = tmp_path / "template.yml"
        cfg.write_text('template-repository: test/repo\ntemplate-branch: main\ntemplates: "not a list"\n')
        config, templates = _load_and_validate_config(cfg)
        # With `and` instead of `or`, this would fall through and return (config, set(...)).
        assert config is None
        assert templates is None
        assert capsys.readouterr().out == f"No templates field in {cfg}, skipping bundle validation\n"


class TestMainExtraCoverage:
    """Tests pinning main()'s stdout-encoding reconfigure and --help output."""

    def test_reconfigures_stdout_encoding(self, tmp_path, monkeypatch):
        """When stdout is a TextIOWrapper, main reconfigures it with the exact encoding/errors."""
        import io
        from unittest.mock import MagicMock

        rhiza_dir = tmp_path / ".rhiza"
        rhiza_dir.mkdir()
        (rhiza_dir / "template.yml").write_text("# no templates field")
        monkeypatch.chdir(tmp_path)

        wrapper = io.TextIOWrapper(io.BytesIO())
        reconfigure = MagicMock()
        monkeypatch.setattr(wrapper, "reconfigure", reconfigure)
        monkeypatch.setattr("sys.stdout", wrapper)

        assert main([]) == 0
        reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")

    def test_help_text(self, capsys):
        """--help renders the exact argparse description and option help strings."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "XX" not in out  # no mutated literal survived into the rendered help
        assert "Validate template-bundles.yml from remote template repository" in out
        assert "Filenames to check (should be .rhiza/template.yml)" in out

    def test_offline_skips_fetch(self, monkeypatch, capsys):
        """--offline returns 0 with the exact notice and never touches the network."""
        from unittest.mock import MagicMock

        # Any attempt to fetch would fail the test, proving the network is skipped.
        urlopen = MagicMock(side_effect=AssertionError("network must not be used in offline mode"))
        monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", urlopen)

        assert main(["--offline"]) == 0
        assert capsys.readouterr().out == "Offline mode: skipping remote template bundles validation\n"
        urlopen.assert_not_called()


class TestRetryTimeoutFlags:
    """Tests for the --retries / --timeout CLI flags (issue #179)."""

    def _make_config(self, tmp_path, monkeypatch):
        """Create a minimal template.yml with a templates field and chdir into it."""
        rhiza_dir = tmp_path / ".rhiza"
        rhiza_dir.mkdir()
        (rhiza_dir / "template.yml").write_text(
            dedent("""
            template-repository: test/repo
            template-branch: main
            templates:
              - core
            """)
        )
        monkeypatch.chdir(tmp_path)

    def test_flags_forwarded_to_fetch(self, tmp_path, monkeypatch):
        """--retries/--timeout are translated to attempts (retries + 1) and timeout."""
        self._make_config(tmp_path, monkeypatch)

        seen = {}

        def mock_fetch_remote_bundles(repo, branch, *, attempts, timeout):
            seen["attempts"] = attempts
            seen["timeout"] = timeout
            return BundlesDoc(
                {"version": 1.0, "bundles": {"core": {"description": "Core", "files": [".gitignore"]}}}, []
            )

        monkeypatch.setattr("rhiza_hooks.check_template_bundles._fetch_remote_bundles", mock_fetch_remote_bundles)

        assert main(["--retries", "4", "--timeout", "7.5"]) == 0
        # --retries counts retries after the first attempt, so attempts = retries + 1.
        assert seen == {"attempts": 5, "timeout": 7.5}

    def test_defaults_when_flags_absent(self, tmp_path, monkeypatch):
        """Without flags, the documented defaults (2 attempts, 10s) are used."""
        from rhiza_hooks.check_template_bundles import _FETCH_ATTEMPTS, _FETCH_TIMEOUT_SECONDS

        self._make_config(tmp_path, monkeypatch)

        seen = {}

        def mock_fetch_remote_bundles(repo, branch, *, attempts, timeout):
            seen["attempts"] = attempts
            seen["timeout"] = timeout
            return BundlesDoc(
                {"version": 1.0, "bundles": {"core": {"description": "Core", "files": [".gitignore"]}}}, []
            )

        monkeypatch.setattr("rhiza_hooks.check_template_bundles._fetch_remote_bundles", mock_fetch_remote_bundles)

        assert main([]) == 0
        assert seen == {"attempts": _FETCH_ATTEMPTS, "timeout": _FETCH_TIMEOUT_SECONDS}

    def test_negative_retries_rejected(self):
        """--retries below zero is rejected by argument validation."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--retries", "-1"])
        assert exc_info.value.code == 2

    def test_non_positive_timeout_rejected(self):
        """--timeout of zero (or less) is rejected by argument validation."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--timeout", "0"])
        assert exc_info.value.code == 2

    def test_flags_in_help(self, capsys):
        """--help advertises the new flags."""
        with pytest.raises(SystemExit):
            main(["--help"])
        out = capsys.readouterr().out
        assert "--retries" in out
        assert "--timeout" in out
