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

import yaml


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

    template_names: set[str] = {str(t) for t in templates}
    return template_names
