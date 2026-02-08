#!/usr/bin/env python3
"""Check that .rhiza/template.yml is valid and well-formed."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REQUIRED_KEYS = {"template-repository", "template-branch"}
OPTIONAL_KEYS = {"include", "exclude", "templates"}
VALID_KEYS = REQUIRED_KEYS | OPTIONAL_KEYS


def _load_config(filepath: Path) -> dict | list[str]:
    """Load configuration from YAML file.

    Returns:
        Config dict on success, or list of error messages on failure
    """
    try:
        with filepath.open() as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return [f"Invalid YAML: {e}"]
    except FileNotFoundError:
        return [f"File not found: {filepath}"]

    if config is None:
        return ["Configuration file is empty"]

    if not isinstance(config, dict):
        return ["Configuration must be a YAML mapping"]

    return config


def _validate_required_keys(config: dict) -> list[str]:
    """Validate required keys are present."""
    errors = []
    for key in REQUIRED_KEYS:
        if key not in config:
            errors.append(f"Missing required key: {key}")
    return errors


def _validate_unknown_keys(config: dict) -> list[str]:
    """Check for unknown keys."""
    errors = []
    for key in config:
        if key not in VALID_KEYS:
            errors.append(f"Unknown key: {key}")
    return errors


def _validate_include_or_templates(config: dict) -> list[str]:
    """Ensure at least one of 'include' or 'templates' is present."""
    if "include" not in config and "templates" not in config:
        return ["At least one of 'include' or 'templates' must be present"]
    return []


def _validate_template_repository(config: dict) -> list[str]:
    """Validate template-repository field."""
    errors = []
    if "template-repository" in config:
        repo = config["template-repository"]
        if not isinstance(repo, str):
            errors.append("template-repository must be a string")
        elif "/" not in repo:
            errors.append(f"template-repository should be in 'owner/repo' format, got: {repo}")
    return errors


def _validate_template_branch(config: dict) -> list[str]:
    """Validate template-branch field."""
    errors = []
    if "template-branch" in config:
        branch = config["template-branch"]
        if not isinstance(branch, str):
            errors.append("template-branch must be a string")
        elif not branch:
            errors.append("template-branch cannot be empty")
    return errors


def _validate_include_field(config: dict) -> list[str]:
    """Validate include field."""
    errors = []
    if "include" in config:
        include = config["include"]
        if not isinstance(include, list):
            errors.append("include must be a list")
        elif not include:
            errors.append("include list cannot be empty")
    return errors


def _validate_templates_field(config: dict) -> list[str]:
    """Validate templates field."""
    errors = []
    if "templates" in config:
        templates = config["templates"]
        if not isinstance(templates, list):
            errors.append("templates must be a list")
        elif not templates:
            errors.append("templates list cannot be empty")
    return errors


def _validate_exclude_field(config: dict) -> list[str]:
    """Validate exclude field."""
    errors = []
    if "exclude" in config:
        exclude = config["exclude"]
        if exclude is not None and not isinstance(exclude, list):
            errors.append("exclude must be a list or null")
    return errors


def validate_rhiza_config(filepath: Path) -> list[str]:
    """Validate a rhiza configuration file.

    Args:
        filepath: Path to the .rhiza/template.yml file

    Returns:
        List of error messages (empty if valid)
    """
    # Load configuration
    config = _load_config(filepath)
    if isinstance(config, list):
        return config

    # Validate all aspects
    errors = []
    errors.extend(_validate_required_keys(config))
    errors.extend(_validate_unknown_keys(config))
    errors.extend(_validate_include_or_templates(config))
    errors.extend(_validate_template_repository(config))
    errors.extend(_validate_template_branch(config))
    errors.extend(_validate_include_field(config))
    errors.extend(_validate_templates_field(config))
    errors.extend(_validate_exclude_field(config))

    return errors


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the hook."""
    parser = argparse.ArgumentParser(description="Validate .rhiza/template.yml configuration")
    parser.add_argument(
        "filenames",
        nargs="*",
        help="Filenames to check",
    )
    args = parser.parse_args(argv)

    retval = 0
    for filename in args.filenames:
        filepath = Path(filename)
        errors = validate_rhiza_config(filepath)
        if errors:
            print(f"{filename}:")
            for error in errors:
                print(f"  - {error}")
            retval = 1

    return retval


if __name__ == "__main__":
    sys.exit(main())
