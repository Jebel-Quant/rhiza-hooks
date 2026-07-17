"""Tests for the ``rhiza_hooks._config_schema`` module."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from rhiza_hooks._config_schema import (
    KEY_ALIASES,
    OPTIONAL_KEYS,
    REQUIRED_KEYS,
    VALID_KEYS,
    normalize_config,
)


# --------------------------------------------------------------------------- #
# Canonical key constants
# --------------------------------------------------------------------------- #
def test_valid_keys_is_union_of_required_and_optional() -> None:
    """VALID_KEYS is exactly the union of the required and optional key sets."""
    assert VALID_KEYS == REQUIRED_KEYS | OPTIONAL_KEYS
    assert {"template-repository", "template-branch"} == REQUIRED_KEYS
    assert {"include", "exclude", "templates"} == OPTIONAL_KEYS


def test_key_aliases_map_to_canonical_keys() -> None:
    """Every alias maps to a canonical (valid) key."""
    assert KEY_ALIASES == {
        "repository": "template-repository",
        "ref": "template-branch",
        "profiles": "templates",
    }
    assert set(KEY_ALIASES.values()) <= VALID_KEYS


# --------------------------------------------------------------------------- #
# normalize_config
# --------------------------------------------------------------------------- #
def test_normalize_config_rewrites_aliases() -> None:
    """Alias keys are rewritten to canonical keys while values are preserved."""
    raw = {"repository": "owner/repo", "ref": "main", "profiles": ["core"]}
    assert normalize_config(raw) == {
        "template-repository": "owner/repo",
        "template-branch": "main",
        "templates": ["core"],
    }


def test_normalize_config_leaves_canonical_and_unknown_keys() -> None:
    """Canonical keys and unrelated keys pass through untouched."""
    raw = {"template-repository": "owner/repo", "extra": 1}
    assert normalize_config(raw) == {"template-repository": "owner/repo", "extra": 1}


# --------------------------------------------------------------------------- #
# Property-based tests
# --------------------------------------------------------------------------- #
# Keys drawn from aliases, their canonical targets, and arbitrary unrelated keys.
_normalize_keys = st.sampled_from(sorted(set(KEY_ALIASES) | set(KEY_ALIASES.values()) | {"unrelated", "other"}))
_normalize_configs = st.dictionaries(_normalize_keys, st.integers(), max_size=6)


@given(_normalize_configs)
def test_property_no_alias_survives_normalization(config: dict[str, int]) -> None:
    """After normalization, no raw alias key remains in the output."""
    normalized = normalize_config(config)
    assert not (set(normalized) & set(KEY_ALIASES))


@given(_normalize_configs)
def test_property_idempotent(config: dict[str, int]) -> None:
    """Canonical keys map to themselves, so normalizing twice == once."""
    once = normalize_config(config)
    assert normalize_config(once) == once


@given(_normalize_configs)
def test_property_value_count_preserved_without_alias_collisions(config: dict[str, int]) -> None:
    """When no key and its alias coexist, normalization is key-count preserving."""
    # Build an input guaranteed free of alias/canonical collisions.
    canonical_to_aliases: dict[str, str] = {v: k for k, v in KEY_ALIASES.items()}
    safe = {k: v for k, v in config.items() if not (k in canonical_to_aliases and canonical_to_aliases[k] in config)}
    normalized = normalize_config(safe)
    assert len(normalized) == len(safe)
