#!/usr/bin/env python3
"""Structural validation of a template-bundles document.

These functions operate on an already-loaded mapping (see
:mod:`rhiza_hooks._bundles_fetch` for how the document is obtained) and report
problems as lists of human-readable error strings. They never perform I/O,
except :func:`validate_template_bundles`, which is a thin convenience wrapper
that loads a local file and then validates it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from rhiza_hooks._bundles_fetch import load_local_bundles


def _not_a_known_bundle(value: Any, bundle_names: set[Any]) -> bool:
    """Return True if ``value`` is not a declared bundle name.

    A plain ``value not in bundle_names`` raises ``TypeError`` when ``value`` is
    unhashable (e.g. a list or dict produced by malformed YAML). Such a value
    can never be a bundle name, so it is reported as unknown rather than crashing.
    """
    try:
        return value not in bundle_names
    except TypeError:
        return True


def validate_top_level_fields(data: dict[Any, Any]) -> list[str]:
    """Validate required top-level fields."""
    errors = []
    required_fields = {"version", "bundles"}
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    return errors


def _validate_dep_list(bundle_name: str, field: str, deps: Any, bundle_names: set[str]) -> list[str]:
    """Validate one dependency list (``requires`` / ``recommends``) of a bundle.

    The ``field`` name doubles as the verb in the "non-existent bundle" message
    (e.g. ``requires``/``recommends``), so the two call sites share this logic.
    """
    if not isinstance(deps, list):
        return [f"Bundle '{bundle_name}' '{field}' must be a list"]
    return [
        f"Bundle '{bundle_name}' {field} non-existent bundle '{dep}'"
        for dep in deps
        if _not_a_known_bundle(dep, bundle_names)
    ]


def _validate_required_bundle_fields(bundle_name: str, bundle_config: dict[Any, Any]) -> list[str]:
    """Validate a bundle's required fields: a ``description`` and a list ``files``."""
    errors = []
    if "description" not in bundle_config:
        errors.append(f"Bundle '{bundle_name}' missing 'description'")
    if "files" not in bundle_config:
        errors.append(f"Bundle '{bundle_name}' missing 'files'")
    elif not isinstance(bundle_config["files"], list):
        errors.append(f"Bundle '{bundle_name}' 'files' must be a list")
    return errors


def _validate_bundle_structure(
    bundle_name: str,
    bundle_config: Any,
    bundle_names: set[str],
) -> list[str]:
    """Validate a single bundle's structure and dependencies."""
    if not isinstance(bundle_config, dict):
        return [f"Bundle '{bundle_name}' must be a dictionary"]

    errors = _validate_required_bundle_fields(bundle_name, bundle_config)

    # Validate dependencies
    for field in ("requires", "recommends"):
        if field in bundle_config:
            errors.extend(_validate_dep_list(bundle_name, field, bundle_config[field], bundle_names))

    return errors


def _is_unknown_example_template(template: Any, bundle_names: set[str]) -> bool:
    """True if an example template is neither ``core`` (auto-included) nor a known bundle."""
    return template != "core" and _not_a_known_bundle(template, bundle_names)


def _validate_example_templates(example_name: str, templates: Any, bundle_names: set[str]) -> list[str]:
    """Validate one example's ``templates`` value: a list of known bundle names."""
    if not isinstance(templates, list):
        return [f"Example '{example_name}' 'templates' must be a list"]
    return [
        f"Example '{example_name}' references non-existent bundle '{template}'"
        for template in templates
        if _is_unknown_example_template(template, bundle_names)
    ]


def _validate_example(example_name: str, example_config: Any, bundle_names: set[str]) -> list[str]:
    """Validate a single example entry."""
    if not isinstance(example_config, dict):
        return [f"Example '{example_name}' must be a dictionary"]
    if "templates" not in example_config:
        return []
    return _validate_example_templates(example_name, example_config["templates"], bundle_names)


def _validate_examples(examples: Any, bundle_names: set[str]) -> list[str]:
    """Validate examples section."""
    if not isinstance(examples, dict):
        return ["'examples' must be a dictionary"]

    errors = []
    for example_name, example_config in examples.items():
        errors.extend(_validate_example(example_name, example_config, bundle_names))
    return errors


def _validate_metadata(metadata: Any, bundles: dict[Any, Any]) -> list[str]:
    """Validate metadata section."""
    errors = []

    if not isinstance(metadata, dict):
        errors.append("'metadata' must be a dictionary")
        return errors

    if "total_bundles" in metadata:
        expected_count = len(bundles)
        actual_count = metadata["total_bundles"]
        if actual_count != expected_count:
            errors.append(
                f"Metadata 'total_bundles' ({actual_count}) doesn't match actual bundle count ({expected_count})"
            )

    return errors


def validate_selected_bundles(
    templates: set[str],
    bundles: dict[Any, Any],
    missing_message: Callable[[str], str],
) -> list[str]:
    """Validate that each requested template exists in ``bundles`` and is well-formed.

    Shared by the local-file and remote-fetch paths; they differ only in the
    "not found" wording, supplied via ``missing_message``.

    Args:
        templates: Template names requested in the rhiza config.
        bundles: The ``bundles`` mapping from a template-bundles document.
        missing_message: Builds the error string for a template absent from ``bundles``.

    Returns:
        List of error messages (empty if every requested template is valid).
    """
    errors: list[str] = []
    bundle_names: set[str] = set(bundles.keys())

    for template in templates:
        if template not in bundle_names:
            errors.append(missing_message(template))

    for template in templates:
        if template in bundles:
            errors.extend(_validate_bundle_structure(template, bundles[template], bundle_names))

    return errors


def validate_template_bundles(bundles_path: Path, templates_to_check: set[str] | None = None) -> tuple[bool, list[str]]:
    """Validate template bundles configuration.

    Args:
        bundles_path: Path to template-bundles.yml
        templates_to_check: Optional set of template names to validate. If None, validate all.

    Returns:
        Tuple of (success, error_messages)
    """
    # Load YAML file
    loaded = load_local_bundles(bundles_path)
    if loaded.data is None:
        return False, loaded.errors
    # data is narrowed to dict[Any, Any] by the `is None` guard above.
    data = loaded.data

    # Validate top-level fields
    errors = validate_top_level_fields(data)
    if errors:
        return False, errors

    # Validate bundles section
    bundles = data.get("bundles", {})
    if not isinstance(bundles, dict):
        return False, ["'bundles' must be a dictionary"]

    if templates_to_check is not None:
        # Validate only the requested subset (existence + structure).
        errors.extend(
            validate_selected_bundles(
                templates_to_check,
                bundles,
                lambda t: f"Template '{t}' specified in .rhiza/template.yml not found in bundles",
            )
        )
    else:
        errors.extend(_validate_all_bundles(data, bundles))

    return len(errors) == 0, errors


def _validate_all_bundles(data: dict[Any, Any], bundles: dict[Any, Any]) -> list[str]:
    """Validate every declared bundle, plus the examples and metadata sections."""
    bundle_names: set[str] = {str(k) for k in bundles}

    errors: list[str] = []
    for bundle_name in bundle_names:
        errors.extend(_validate_bundle_structure(bundle_name, bundles[bundle_name], bundle_names))
    if "examples" in data:
        errors.extend(_validate_examples(data["examples"], bundle_names))
    if "metadata" in data:
        errors.extend(_validate_metadata(data["metadata"], bundles))
    return errors
