#!/usr/bin/env python3
"""Check that .rhiza/template.yml is valid and well-formed."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REQUIRED_KEYS = {"template-repository", "template-branch", "include"}
OPTIONAL_KEYS = {"exclude"}
VALID_KEYS = REQUIRED_KEYS | OPTIONAL_KEYS


def validate_rhiza_config(filepath: Path) -> list[str]:
    """Validate a rhiza configuration file.

    Args:
        filepath: Path to the .rhiza/template.yml file

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []

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

    # Check for required keys
    for key in REQUIRED_KEYS:
        if key not in config:
            errors.append(f"Missing required key: {key}")

    # Check for unknown keys
    for key in config:
        if key not in VALID_KEYS:
            errors.append(f"Unknown key: {key}")

    # Validate template-repository format
    if "template-repository" in config:
        repo = config["template-repository"]
        if not isinstance(repo, str):
            errors.append("template-repository must be a string")
        elif "/" not in repo:
            errors.append(f"template-repository should be in 'owner/repo' format, got: {repo}")

    # Validate template-branch
    if "template-branch" in config:
        branch = config["template-branch"]
        if not isinstance(branch, str):
            errors.append("template-branch must be a string")
        elif not branch:
            errors.append("template-branch cannot be empty")

    # Validate include
    if "include" in config:
        include = config["include"]
        if not isinstance(include, list):
            errors.append("include must be a list")
        elif not include:
            errors.append("include list cannot be empty")

    # Validate exclude (if present)
    if "exclude" in config:
        exclude = config["exclude"]
        if exclude is not None and not isinstance(exclude, list):
            errors.append("exclude must be a list or null")

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
