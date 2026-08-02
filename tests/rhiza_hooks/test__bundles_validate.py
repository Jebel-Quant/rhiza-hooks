"""Tests for the ``rhiza_hooks._bundles_validate`` module."""

from __future__ import annotations

import pytest

from rhiza_hooks._bundles_validate import (
    _validate_bundle_structure,
    _validate_examples,
    _validate_metadata,
    validate_template_bundles,
    validate_top_level_fields,
)


def test_valid_fields():
    """Test with all required fields present."""
    data = {"version": 1.0, "bundles": {}}
    errors = validate_top_level_fields(data)
    assert errors == []


def test_missing_version():
    """Test with missing version field reports the exact message."""
    data = {"bundles": {}}
    errors = validate_top_level_fields(data)
    assert errors == ["Missing required field: version"]


def test_missing_bundles():
    """Test with missing bundles field reports the exact message."""
    data = {"version": 1.0}
    errors = validate_top_level_fields(data)
    assert errors == ["Missing required field: bundles"]


def test_missing_all_fields():
    """Test with all required fields missing."""
    data = {}
    errors = validate_top_level_fields(data)
    assert len(errors) == 2


def test_valid_bundle():
    """Test with valid bundle structure."""
    bundle_config = {
        "description": "Test bundle",
        "files": [".gitignore", "README.md"],
    }
    errors = _validate_bundle_structure("test", bundle_config, {"test"})
    assert errors == []


@pytest.mark.parametrize("key", ["requires", "recommends"])
def test_unhashable_dependency_entry(key):
    """An unhashable dependency entry is reported, not crashed on (fuzzing regression)."""
    bundle_config = {"description": "x", "files": [], key: [["nested"]]}
    errors = _validate_bundle_structure("test", bundle_config, {"test"})
    assert errors == [f"Bundle 'test' {key} non-existent bundle '['nested']'"]


def test_bundle_not_dict():
    """Test with bundle not being a dictionary reports the exact message."""
    errors = _validate_bundle_structure("test", "not-a-dict", {"test"})
    assert errors == ["Bundle 'test' must be a dictionary"]


def test_missing_description():
    """Test with missing description reports the exact message."""
    bundle_config = {"files": [".gitignore"]}
    errors = _validate_bundle_structure("test", bundle_config, {"test"})
    assert errors == ["Bundle 'test' missing 'description'"]


def test_missing_files():
    """Test with missing files reports the exact message."""
    bundle_config = {"description": "Test bundle"}
    errors = _validate_bundle_structure("test", bundle_config, {"test"})
    assert errors == ["Bundle 'test' missing 'files'"]


def test_files_not_list():
    """Test with files not being a list reports the exact message."""
    bundle_config = {
        "description": "Test bundle",
        "files": "not-a-list",
    }
    errors = _validate_bundle_structure("test", bundle_config, {"test"})
    assert errors == ["Bundle 'test' 'files' must be a list"]


def test_valid_requires():
    """Test with valid requires."""
    bundle_config = {
        "description": "Test bundle",
        "files": [".gitignore"],
        "requires": ["core"],
    }
    errors = _validate_bundle_structure("test", bundle_config, {"test", "core"})
    assert errors == []


def test_requires_not_list():
    """Test with requires not being a list."""
    bundle_config = {
        "description": "Test bundle",
        "files": [".gitignore"],
        "requires": "not-a-list",
    }
    errors = _validate_bundle_structure("test", bundle_config, {"test"})
    assert errors == ["Bundle 'test' 'requires' must be a list"]


def test_requires_nonexistent_bundle():
    """Test with requires referencing non-existent bundle reports the exact message."""
    bundle_config = {
        "description": "Test bundle",
        "files": [".gitignore"],
        "requires": ["nonexistent"],
    }
    errors = _validate_bundle_structure("test", bundle_config, {"test"})
    assert errors == ["Bundle 'test' requires non-existent bundle 'nonexistent'"]


def test_valid_recommends():
    """Test with valid recommends."""
    bundle_config = {
        "description": "Test bundle",
        "files": [".gitignore"],
        "recommends": ["makefile"],
    }
    errors = _validate_bundle_structure("test", bundle_config, {"test", "makefile"})
    assert errors == []


def test_recommends_not_list():
    """Test with recommends not being a list."""
    bundle_config = {
        "description": "Test bundle",
        "files": [".gitignore"],
        "recommends": "not-a-list",
    }
    errors = _validate_bundle_structure("test", bundle_config, {"test"})
    assert errors == ["Bundle 'test' 'recommends' must be a list"]


def test_recommends_nonexistent_bundle():
    """Test with recommends referencing non-existent bundle reports the exact message."""
    bundle_config = {
        "description": "Test bundle",
        "files": [".gitignore"],
        "recommends": ["nonexistent"],
    }
    errors = _validate_bundle_structure("test", bundle_config, {"test"})
    assert errors == ["Bundle 'test' recommends non-existent bundle 'nonexistent'"]


def test_valid_examples():
    """Test with valid examples."""
    examples = {
        "basic": {
            "templates": ["core", "python"],
        },
    }
    errors = _validate_examples(examples, {"core", "python"})
    assert errors == []


def test_examples_not_dict():
    """Test with examples not being a dictionary reports the exact message."""
    errors = _validate_examples("not-a-dict", {"core"})
    assert errors == ["'examples' must be a dictionary"]


def test_templates_not_list():
    """Test with templates not being a list reports the exact message."""
    examples = {
        "basic": {
            "templates": "not-a-list",
        },
    }
    errors = _validate_examples(examples, {"core"})
    assert errors == ["Example 'basic' 'templates' must be a list"]


def test_template_references_nonexistent_bundle():
    """Test with template referencing non-existent bundle reports the exact message."""
    examples = {
        "basic": {
            "templates": ["core", "nonexistent"],
        },
    }
    errors = _validate_examples(examples, {"core"})
    assert errors == ["Example 'basic' references non-existent bundle 'nonexistent'"]


def test_core_template_not_validated():
    """Test that 'core' template is not validated."""
    examples = {
        "basic": {
            "templates": ["core"],
        },
    }
    errors = _validate_examples(examples, set())
    assert errors == []


def test_example_without_templates_key():
    """An example with no 'templates' key is skipped without error."""
    examples = {
        "basic": {"description": "no templates listed"},
    }
    errors = _validate_examples(examples, {"core"})
    assert errors == []


@pytest.mark.parametrize("bad_value", [None, 5, "string", ["list"]])
def test_example_value_not_dict(bad_value):
    """A non-dict example value is reported, not crashed on (fuzzing regression)."""
    errors = _validate_examples({"basic": bad_value}, {"core"})
    assert errors == ["Example 'basic' must be a dictionary"]


def test_unhashable_template_entry():
    """An unhashable template entry is reported, not crashed on (fuzzing regression)."""
    examples = {"basic": {"templates": [["nested"]]}}
    errors = _validate_examples(examples, {"core"})
    assert errors == ["Example 'basic' references non-existent bundle '['nested']'"]


def test_valid_metadata():
    """Test with valid metadata."""
    metadata = {"total_bundles": 2}
    bundles = {"bundle1": {}, "bundle2": {}}
    errors = _validate_metadata(metadata, bundles)
    assert errors == []


def test_mismatched_total_bundles():
    """Test with mismatched total_bundles reports the exact message."""
    metadata = {"total_bundles": 5}
    bundles = {"bundle1": {}, "bundle2": {}}
    errors = _validate_metadata(metadata, bundles)
    assert errors == ["Metadata 'total_bundles' (5) doesn't match actual bundle count (2)"]


def test_no_total_bundles_field():
    """Test with no total_bundles field."""
    metadata = {}
    bundles = {"bundle1": {}, "bundle2": {}}
    errors = _validate_metadata(metadata, bundles)
    assert errors == []


@pytest.mark.parametrize("bad_value", [None, 5, "string", ["list"]])
def test_metadata_not_dict(bad_value):
    """A non-dict metadata section is reported, not crashed on (fuzzing regression)."""
    errors = _validate_metadata(bad_value, {"bundle1": {}})
    assert errors == ["'metadata' must be a dictionary"]


def test_valid_config(temp_bundles_file):
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


def test_nonexistent_file_triggers_assertion(tmp_path):
    """Test that nonexistent file triggers the assertion on line 263-264."""
    nonexistent_file = tmp_path / "nonexistent.yml"
    success, errors = validate_template_bundles(nonexistent_file)
    assert success is False
    assert isinstance(errors, list)
    assert len(errors) > 0


def test_missing_required_fields(temp_bundles_file):
    """Test with missing required fields."""
    bundles_file = temp_bundles_file("""
        bundles: {}
    """)
    success, errors = validate_template_bundles(bundles_file)
    assert success is False
    assert any("version" in e.lower() for e in errors)


def test_bundles_not_dict(temp_bundles_file):
    """Test with bundles not being a dictionary."""
    bundles_file = temp_bundles_file("""
        version: 1.0
        bundles: []
    """)
    success, errors = validate_template_bundles(bundles_file)
    assert success is False
    assert errors == ["'bundles' must be a dictionary"]


def test_invalid_bundle_structure(temp_bundles_file):
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


def test_invalid_dependency(temp_bundles_file):
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


def test_invalid_example(temp_bundles_file):
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


def test_invalid_metadata(temp_bundles_file):
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


def test_validate_specific_templates(temp_bundles_file):
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


def test_validate_nonexistent_template(temp_bundles_file):
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


def test_validate_with_invalid_dependency(temp_bundles_file):
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


def test_metadata_not_validated_with_specific_templates(temp_bundles_file):
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
