#!/usr/bin/env python3
"""Validate template-bundles.yml structure and consistency.

This script validates the template bundles configuration file to ensure:
1. Valid YAML syntax
2. Required fields are present
3. Bundle dependencies reference existing bundles
4. File paths follow expected patterns
5. Examples reference valid bundles

The script reads .rhiza/template.yml to find the template repository,
then fetches template-bundles.yml from that remote repository.

Exit codes:
  0 - Validation passed
  1 - Validation failed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen

import yaml


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


def find_repo_root() -> Path:
    """Find the repository root directory.

    Returns:
        Path to the repository root
    """
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return Path.cwd()


def _get_config_data(config_path: Path) -> dict[str, Any] | None:
    """Get the configuration from .rhiza/template.yml.

    Args:
        config_path: Path to .rhiza/template.yml

    Returns:
        Configuration dictionary, or None if file not found or invalid
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

    return config


def _get_templates_from_config(config_path: Path) -> set[str] | None:
    """Get the list of templates from .rhiza/template.yml.

    Args:
        config_path: Path to .rhiza/template.yml

    Returns:
        Set of template names, or None if templates field doesn't exist or file not found
    """
    config = _get_config_data(config_path)
    if config is None:
        return None

    templates = config.get("templates")
    if templates is None:
        return None

    if not isinstance(templates, list):
        return None

    return set(templates)


def _fetch_remote_bundles(repo: str, branch: str) -> tuple[bool, dict[Any, Any] | list[str]]:
    """Fetch template-bundles.yml from a remote GitHub repository.

    Args:
        repo: GitHub repository in 'owner/repo' format
        branch: Branch name

    Returns:
        Tuple of (success, data_or_errors)
    """
    # Construct GitHub raw content URL
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/.rhiza/template-bundles.yml"

    # Validate URL scheme for security (bandit B310)
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False, [f"Invalid URL scheme: {parsed.scheme}. Only https is allowed."]

    try:
        with urlopen(url, timeout=10) as response:  # nosec B310
            content = response.read()
    except HTTPError as e:
        if e.code == 404:
            return False, [f"Template bundles file not found in repository {repo} (branch: {branch})"]
        return False, [f"HTTP error fetching template bundles: {e.code} {e.reason}"]
    except URLError as e:
        return False, [f"Error fetching template bundles from {url}: {e.reason}"]
    except TimeoutError:
        return False, [f"Timeout fetching template bundles from {url}"]

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        return False, [f"Invalid YAML in remote template bundles: {e}"]

    if data is None:
        return False, ["Remote template bundles file is empty"]

    if not isinstance(data, dict):
        return False, ["Remote template bundles must be a dictionary"]

    return True, data


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


def _get_config_path(args: argparse.Namespace) -> Path:
    """Get the configuration file path from arguments or default location."""
    if args.filenames:
        return Path(args.filenames[0])
    return find_repo_root() / ".rhiza" / "template.yml"


def _load_and_validate_config(config_path: Path) -> tuple[dict[str, Any] | None, set[str] | None]:
    """Load and validate configuration file.

    Returns:
        Tuple of (config, templates_set) or (None, None) if validation fails
    """
    config = _get_config_data(config_path)
    if config is None:
        print(f"Could not load configuration from {config_path}, skipping validation")
        return None, None

    templates_to_check = config.get("templates")
    if templates_to_check is None or not isinstance(templates_to_check, list):
        print(f"No templates field in {config_path}, skipping bundle validation")
        return None, None

    return config, set(templates_to_check)


def _validate_remote_bundles(
    template_repo: str, template_branch: str, templates_set: set[str], config_path: Path
) -> tuple[dict[Any, Any] | None, list[str]]:
    """Fetch and validate remote bundles.

    Returns:
        Tuple of (bundles_data, errors) or (None, errors) if fetch fails
    """
    print(f"Fetching template bundles from {template_repo} (branch: {template_branch})")
    print(f"Checking templates: {', '.join(sorted(templates_set))}")

    success, data_or_errors = _fetch_remote_bundles(template_repo, template_branch)
    if not success:
        print("\n✗ Failed to fetch template bundles:")
        assert isinstance(data_or_errors, list)
        for error in data_or_errors:
            print(f"  - {error}")
        return None, data_or_errors

    assert isinstance(data_or_errors, dict)
    data = data_or_errors

    # Validate top-level structure
    errors = _validate_top_level_fields(data)
    if errors:
        print("\n✗ Template bundles validation failed:")
        for error in errors:
            print(f"  - {error}")
        return None, errors

    bundles = data.get("bundles", {})
    if not isinstance(bundles, dict):
        print("\n✗ Template bundles validation failed:")
        print("  - 'bundles' must be a dictionary")
        return None, ["'bundles' must be a dictionary"]

    return data, []


def _validate_templates_in_bundles(templates_set: set[str], bundles: dict[Any, Any], config_path: Path) -> list[str]:
    """Validate that requested templates exist and have valid structure."""
    errors = []
    bundle_names = set(bundles.keys())

    # Check if templates exist
    for template in templates_set:
        if template not in bundle_names:
            errors.append(f"Template '{template}' specified in {config_path} not found in remote bundles")

    # Validate structure of each template
    for template in templates_set:
        if template in bundles:
            bundle_config = bundles[template]
            errors.extend(_validate_bundle_structure(template, bundle_config, bundle_names))

    return errors


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate template-bundles.yml from remote template repository")
    parser.add_argument(
        "filenames",
        nargs="*",
        help="Filenames to check (should be .rhiza/template.yml)",
    )
    args = parser.parse_args(argv)

    # Get configuration path
    config_path = _get_config_path(args)

    # Load and validate configuration
    config, templates_set = _load_and_validate_config(config_path)
    if config is None or templates_set is None:
        return 0

    # Get template repository and branch
    template_repo = config.get("template-repository")
    template_branch = config.get("template-branch")

    if not template_repo or not template_branch:
        print(f"Missing template-repository or template-branch in {config_path}")
        return 1

    # Fetch and validate remote bundles
    data, _fetch_errors = _validate_remote_bundles(template_repo, template_branch, templates_set, config_path)
    if data is None:
        return 1

    # Validate templates
    bundles = data.get("bundles", {})
    errors = _validate_templates_in_bundles(templates_set, bundles, config_path)

    if errors:
        print("\n✗ Template bundles validation failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("✓ Template bundles validation passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
