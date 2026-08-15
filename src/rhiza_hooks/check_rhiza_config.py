#!/usr/bin/env python3
"""Check that .rhiza/template.yml is valid and well-formed."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rhiza_hooks._config_schema import KEY_ALIASES, REQUIRED_KEYS, VALID_KEYS, normalize_config
from rhiza_hooks._yaml import YamlError, YamlFailure, load_yaml_mapping


def _load_config(filepath: Path) -> dict[str, Any] | list[str]:
    """Load configuration from YAML file.

    Returns:
        Config dict on success, or list of error messages on failure
    """
    result = load_yaml_mapping(filepath)
    if not isinstance(result, YamlFailure):
        return result

    messages = {
        YamlError.NOT_FOUND: f"File not found: {filepath}",
        YamlError.INVALID: f"Invalid YAML: {result.detail}",
        YamlError.EMPTY: "Configuration file is empty",
        YamlError.NOT_MAPPING: "Configuration must be a YAML mapping",
    }
    return [messages[result.kind]]


def _validate_required_keys(config: dict[str, Any]) -> list[str]:
    """Validate required keys are present.

    >>> _validate_required_keys({"template-repository": "jebel-quant/rhiza", "template-branch": "v1.3.3"})
    []
    >>> _validate_required_keys({"template-repository": "jebel-quant/rhiza"})
    ['Missing required key: template-branch']

    Aliases are resolved before this runs (see :func:`_config_schema.normalize_config`),
    so a config spelling the key ``ref:`` reaches here already canonical.
    """
    errors = []
    for key in REQUIRED_KEYS:
        if key not in config:
            errors.append(f"Missing required key: {key}")
    return errors


def _validate_unknown_keys(config: dict[str, Any]) -> list[str]:
    """Check for unknown keys.

    >>> _validate_unknown_keys({"template-repository": "o/r", "template-branch": "v1"})
    []
    >>> _validate_unknown_keys({"template-repository": "o/r", "tempalte-branch": "v1"})
    ['Unknown key: tempalte-branch']

    Alias spellings are accepted here as well as canonical ones, so validation
    does not depend on having normalized first:

    >>> _validate_unknown_keys({"repository": "o/r", "ref": "v1", "profiles": ["core"]})
    []
    """
    errors = []
    # Accept both canonical keys and their aliases
    all_valid_keys = VALID_KEYS | set(KEY_ALIASES.keys())
    for key in config:
        if key not in all_valid_keys:
            errors.append(f"Unknown key: {key}")
    return errors


def _validate_include_or_templates(config: dict[str, Any]) -> list[str]:
    """Ensure at least one of 'include' or 'templates' is present."""
    if "include" not in config and "templates" not in config:
        return ["At least one of 'include' or 'templates' must be present"]
    return []


def _validate_template_repository(config: dict[str, Any]) -> list[str]:
    """Validate template-repository field."""
    errors = []
    if "template-repository" in config:
        repo = config["template-repository"]
        if not isinstance(repo, str):
            errors.append("template-repository must be a string")
        elif "/" not in repo:
            errors.append(f"template-repository should be in 'owner/repo' format, got: {repo}")
    return errors


@dataclass(frozen=True)
class _FieldRule:
    """Declarative rule for a presence-conditional field.

    When the field is present its value must be an instance of one of ``types``,
    otherwise ``type_error`` is reported. If ``empty_error`` is set, a falsy value
    (empty list, empty string) is rejected with that message. ``exclude`` permits
    ``None`` by including ``type(None)`` in its ``types``.
    """

    key: str
    types: tuple[type, ...]
    type_error: str
    empty_error: str | None = None


# Per-field rules sharing the "optional, type-checked, optionally non-empty" shape.
# template-repository is validated separately because it needs an owner/repo format check.
_FIELD_RULES: tuple[_FieldRule, ...] = (
    _FieldRule("template-branch", (str,), "template-branch must be a string", "template-branch cannot be empty"),
    _FieldRule("include", (list,), "include must be a list", "include list cannot be empty"),
    _FieldRule("templates", (list,), "templates must be a list", "templates list cannot be empty"),
    _FieldRule("exclude", (list, type(None)), "exclude must be a list or null"),
    # Type-checked but not enumerated: see the note on OPTIONAL_KEYS in _config_schema.
    # This catches `language: [go]` and an empty value; it does not police the spelling,
    # because this package is pinned and upstream may add a layer at any time.
    _FieldRule("language", (str,), "language must be a string", "language cannot be empty"),
)


def _validate_field(config: dict[str, Any], rule: _FieldRule) -> list[str]:
    """Validate a single field against its rule (a no-op when the field is absent)."""
    if rule.key not in config:
        return []
    value = config[rule.key]
    if not isinstance(value, rule.types):
        return [rule.type_error]
    if rule.empty_error is not None and not value:
        return [rule.empty_error]
    return []


def validate_rhiza_config(filepath: Path) -> list[str]:
    """Validate a rhiza configuration file.

    Args:
        filepath: Path to the .rhiza/template.yml file

    Returns:
        List of error messages (empty if valid)
    """
    # Load configuration
    raw_config = _load_config(filepath)
    if isinstance(raw_config, list):
        return raw_config

    # Validate unknown keys on raw config (before normalization)
    errors = []
    errors.extend(_validate_unknown_keys(raw_config))

    # Normalize aliases for subsequent validation
    config = normalize_config(raw_config)

    # Validate all aspects
    errors.extend(_validate_required_keys(config))
    errors.extend(_validate_include_or_templates(config))
    errors.extend(_validate_template_repository(config))
    for rule in _FIELD_RULES:
        errors.extend(_validate_field(config, rule))

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
            print(f"{filename}:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            retval = 1

    return retval


if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
