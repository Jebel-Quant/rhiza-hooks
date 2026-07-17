#!/usr/bin/env python3
"""Canonical schema for ``.rhiza/template.yml`` — keys, aliases, normalization.

This is the single source of truth for the shape of a rhiza template config. It
owns the canonical key sets (:data:`REQUIRED_KEYS`, :data:`OPTIONAL_KEYS`,
:data:`VALID_KEYS`), the :data:`KEY_ALIASES` map from accepted alias spellings to
their canonical names, and :func:`normalize_config`, which rewrites a raw mapping
so every alias becomes its canonical key.

Both the config validator (:mod:`rhiza_hooks.check_rhiza_config`) and the
template-bundles reader (:mod:`rhiza_hooks._bundles_config`) import from here so
the alias handling never drifts between them. The module is a leaf: it imports
nothing from the rest of :mod:`rhiza_hooks`.
"""

from __future__ import annotations

from typing import Any

REQUIRED_KEYS = {"template-repository", "template-branch"}
OPTIONAL_KEYS = {"include", "exclude", "templates"}
VALID_KEYS = REQUIRED_KEYS | OPTIONAL_KEYS
# Alternative (alias) key names mapped to their canonical spellings.
KEY_ALIASES = {
    "repository": "template-repository",
    "ref": "template-branch",
    "profiles": "templates",
}


def normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    """Normalize configuration by replacing aliases with canonical keys.

    Args:
        config: Raw configuration dictionary

    Returns:
        Normalized configuration with aliases replaced
    """
    normalized: dict[str, Any] = {}
    for key, value in config.items():
        # Replace alias with canonical name if it exists
        canonical_key = KEY_ALIASES.get(key, key)
        normalized[canonical_key] = value
    return normalized
