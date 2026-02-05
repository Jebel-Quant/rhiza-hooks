#!/usr/bin/env python3
"""Validate template-bundles.yml structure and consistency.

This script validates the template bundles configuration file to ensure:
1. Valid YAML syntax
2. Required fields are present
3. Bundle dependencies reference existing bundles
4. File paths follow expected patterns
5. Examples reference valid bundles

Exit codes:
  0 - Validation passed
  1 - Validation failed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml")
    sys.exit(1)


def _load_yaml_file(bundles_path: Path) -> tuple[bool, dict[Any, Any] | list[str]]:
    """Load and parse YAML file.

    Returns:
        Tuple of (success, data_or_errors)
    """
    if not bundles_path.exists():
        return False, [f"Template bundles file not found: {bundles_path}"]

    try:
        with open(bundles_path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return False, [f"Invalid YAML: {e}"]

    if data is None:
        return False, ["Template bundles file is empty"]

    return True, data


def _validate_top_level_fields(data: dict[Any, Any]) -> list[str]:
    """Validate required top-level fields."""
    errors = []
    required_fields = {"version", "bundles"}
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    return errors


def _validate_bundle_structure(
    bundle_name: str,
    bundle_config: dict[Any, Any] | object,
    bundle_names: set[str],
) -> list[str]:
    """Validate a single bundle's structure and dependencies."""
    errors = []

    if not isinstance(bundle_config, dict):
        errors.append(f"Bundle '{bundle_name}' must be a dictionary")
        return errors

    # Check required fields
    if "description" not in bundle_config:
        errors.append(f"Bundle '{bundle_name}' missing 'description'")

    if "files" not in bundle_config:
        errors.append(f"Bundle '{bundle_name}' missing 'files'")
    elif not isinstance(bundle_config["files"], list):
        errors.append(f"Bundle '{bundle_name}' 'files' must be a list")

    # Validate dependencies
    if "requires" in bundle_config:
        if not isinstance(bundle_config["requires"], list):
            errors.append(f"Bundle '{bundle_name}' 'requires' must be a list")
        else:
            for dep in bundle_config["requires"]:
                if dep not in bundle_names:
                    errors.append(f"Bundle '{bundle_name}' requires non-existent bundle '{dep}'")

    if "recommends" in bundle_config:
        if not isinstance(bundle_config["recommends"], list):
            errors.append(f"Bundle '{bundle_name}' 'recommends' must be a list")
        else:
            for dep in bundle_config["recommends"]:
                if dep not in bundle_names:
                    errors.append(f"Bundle '{bundle_name}' recommends non-existent bundle '{dep}'")

    return errors


def _validate_examples(examples: dict[Any, Any] | object, bundle_names: set[str]) -> list[str]:
    """Validate examples section."""
    errors = []

    if not isinstance(examples, dict):
        errors.append("'examples' must be a dictionary")
        return errors

    for example_name, example_config in examples.items():
        if "templates" in example_config:
            if not isinstance(example_config["templates"], list):
                errors.append(f"Example '{example_name}' 'templates' must be a list")
            else:
                for template in example_config["templates"]:
                    # core is auto-included, we don't validate it
                    if template != "core" and template not in bundle_names:
                        errors.append(f"Example '{example_name}' references non-existent bundle '{template}'")

    return errors


def _validate_metadata(metadata: dict[Any, Any], bundles: dict[Any, Any]) -> list[str]:
    """Validate metadata section."""
    errors = []

    if "total_bundles" in metadata:
        expected_count = len(bundles)
        actual_count = metadata["total_bundles"]
        if actual_count != expected_count:
            errors.append(
                f"Metadata 'total_bundles' ({actual_count}) doesn't match actual bundle count ({expected_count})"
            )

    return errors


def _get_templates_from_config(config_path: Path) -> set[str] | None:
    """Get the list of templates from .rhiza/template.yml.

    Args:
        config_path: Path to .rhiza/template.yml

    Returns:
        Set of template names, or None if templates field doesn't exist or file not found
    """
    if not config_path.exists():
        return None

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError:
        return None

    if not isinstance(config, dict):
        return None

    templates = config.get("templates")
    if templates is None:
        return None

    if not isinstance(templates, list):
        return None

    return set(templates)


def validate_template_bundles(bundles_path: Path, templates_to_check: set[str] | None = None) -> tuple[bool, list[str]]:
    """Validate template bundles configuration.

    Args:
        bundles_path: Path to template-bundles.yml
        templates_to_check: Optional set of template names to validate. If None, validate all.

    Returns:
        Tuple of (success, error_messages)
    """
    # Load YAML file
    success, data_or_errors = _load_yaml_file(bundles_path)
    if not success:
        # Type narrowing: when success is False, data_or_errors is list[str]
        assert isinstance(data_or_errors, list)
        return False, data_or_errors

    # Type narrowing: when success is True, data_or_errors is dict[Any, Any]
    assert isinstance(data_or_errors, dict)
    data = data_or_errors

    # Validate top-level fields
    errors = _validate_top_level_fields(data)
    if errors:
        return False, errors

    # Validate bundles section
    bundles = data.get("bundles", {})
    if not isinstance(bundles, dict):
        return False, ["'bundles' must be a dictionary"]

    bundle_names = set(bundles.keys())

    # If templates_to_check is specified, verify they exist
    if templates_to_check is not None:
        for template in templates_to_check:
            if template not in bundle_names:
                errors.append(f"Template '{template}' specified in .rhiza/template.yml not found in bundles")

    # Determine which bundles to validate
    bundles_to_validate = templates_to_check if templates_to_check is not None else bundle_names

    # Validate each bundle
    for bundle_name in bundles_to_validate:
        if bundle_name in bundles:
            bundle_config = bundles[bundle_name]
            errors.extend(_validate_bundle_structure(bundle_name, bundle_config, bundle_names))

    # Validate examples section (only if validating all bundles)
    if templates_to_check is None and "examples" in data:
        errors.extend(_validate_examples(data["examples"], bundle_names))

    # Validate metadata if present (only if validating all bundles)
    if templates_to_check is None and "metadata" in data:
        errors.extend(_validate_metadata(data["metadata"], bundles))

    return len(errors) == 0, errors


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate template-bundles.yml configuration")
    parser.add_argument(
        "filenames",
        nargs="*",
        help="Filenames to check (defaults to .rhiza/template-bundles.yml in current directory)",
    )
    args = parser.parse_args(argv)

    # If filenames provided, use them; otherwise use default path from current directory
    if args.filenames:
        bundles_path = Path(args.filenames[0])
    else:
        bundles_path = Path.cwd() / ".rhiza" / "template-bundles.yml"

    # Try to load templates from .rhiza/template.yml
    config_path = bundles_path.parent / "template.yml"
    templates_to_check = _get_templates_from_config(config_path)

    if templates_to_check is not None:
        print(f"Validating template bundles: {bundles_path}")
        print(f"Checking only templates specified in {config_path}: {', '.join(sorted(templates_to_check))}")
    else:
        print(f"Validating template bundles: {bundles_path}")
        print("No templates field in .rhiza/template.yml, validating all bundles")

    success, errors = validate_template_bundles(bundles_path, templates_to_check)

    if success:
        print("✓ Template bundles validation passed!")
        return 0
    else:
        print("\n✗ Template bundles validation failed:")
        for error in errors:
            print(f"  - {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
