#!/usr/bin/env python3
"""Read the project's ``.rhiza/template.yml`` configuration.

Helpers for extracting the bits of the rhiza config that the
``check-template-bundles`` hook needs: the raw mapping and the declared set of
template names. Returning ``None`` signals "absent or unusable", which callers
treat as "skip validation".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rhiza_hooks._config_schema import normalize_config
from rhiza_hooks._yaml import YamlFailure, load_yaml_mapping


def _get_config_data(config_path: Path) -> dict[str, Any] | None:
    """Get the configuration from .rhiza/template.yml.

    Aliases (``repository``/``ref``/``profiles``) are normalized to their
    canonical keys so downstream reads of ``template-repository`` /
    ``template-branch`` / ``templates`` work for both alias and canonical forms.

    Args:
        config_path: Path to .rhiza/template.yml

    Returns:
        Configuration dictionary, or None if file not found or invalid
    """
    result = load_yaml_mapping(config_path)
    if isinstance(result, YamlFailure):
        return None
    return normalize_config(result)


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

    template_names: set[str] = {str(t) for t in templates}
    return template_names
