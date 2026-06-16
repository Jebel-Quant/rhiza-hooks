"""Property-based tests (Hypothesis) for the pure parsing/validation helpers.

These exercise algebraic invariants rather than fixed examples, and are collected
by the ``make hypothesis-test`` target (``-m "hypothesis or property"``); the
``@given`` decorator applies Hypothesis' own ``hypothesis`` marker automatically.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from rhiza_hooks.check_python_version import parse_version, version_satisfies_constraint
from rhiza_hooks.check_rhiza_config import KEY_ALIASES, _normalize_config

# Version components kept small but representative; the helpers only ever compare
# (major, minor) tuples, so the exact magnitude is irrelevant to the invariants.
_components = st.integers(min_value=0, max_value=99)


def _version_str(major: int, minor: int) -> str:
    """Format a (major, minor) pair as a dotted version string."""
    return f"{major}.{minor}"


class TestParseVersion:
    """Invariants for parse_version."""

    @given(_components, _components)
    def test_roundtrip(self, major: int, minor: int) -> None:
        """Formatting a (major, minor) pair and parsing it returns the pair."""
        assert parse_version(_version_str(major, minor)) == (major, minor)


class TestVersionSatisfiesConstraint:
    """Algebraic invariants for version_satisfies_constraint.

    The function compares (major, minor) tuples under a total order, so each
    operator has a dual / negation that must hold for *every* pair of versions.
    """

    @given(_components, _components, _components, _components)
    def test_ge_is_mirror_of_le(self, a_maj: int, a_min: int, b_maj: int, b_min: int) -> None:
        """Mirror identity: a >= b holds exactly when b <= a."""
        a, b = _version_str(a_maj, a_min), _version_str(b_maj, b_min)
        assert version_satisfies_constraint(a, ">=", b) == version_satisfies_constraint(b, "<=", a)

    @given(_components, _components, _components, _components)
    def test_gt_is_mirror_of_lt(self, a_maj: int, a_min: int, b_maj: int, b_min: int) -> None:
        """Mirror identity: a > b holds exactly when b < a."""
        a, b = _version_str(a_maj, a_min), _version_str(b_maj, b_min)
        assert version_satisfies_constraint(a, ">", b) == version_satisfies_constraint(b, "<", a)

    @given(_components, _components, _components, _components)
    def test_ge_negates_lt(self, a_maj: int, a_min: int, b_maj: int, b_min: int) -> None:
        """Total order: a >= b is exactly the negation of a < b."""
        a, b = _version_str(a_maj, a_min), _version_str(b_maj, b_min)
        assert version_satisfies_constraint(a, ">=", b) != version_satisfies_constraint(a, "<", b)

    @given(_components, _components, _components, _components)
    def test_eq_negates_ne(self, a_maj: int, a_min: int, b_maj: int, b_min: int) -> None:
        """Equality is exactly the negation of inequality (== versus !=)."""
        a, b = _version_str(a_maj, a_min), _version_str(b_maj, b_min)
        assert version_satisfies_constraint(a, "==", b) != version_satisfies_constraint(a, "!=", b)

    @given(_components, _components)
    def test_empty_operator_means_equality(self, major: int, minor: int) -> None:
        """An empty operator behaves like '==' (documented default)."""
        v = _version_str(major, minor)
        assert version_satisfies_constraint(v, "", v) is True

    @given(_components, _components, _components, _components)
    def test_compatible_release_implies_lower_bound(self, a_maj: int, a_min: int, b_maj: int, b_min: int) -> None:
        """Compatible-release ~= refines >=: it never accepts what >= rejects."""
        a, b = _version_str(a_maj, a_min), _version_str(b_maj, b_min)
        if version_satisfies_constraint(a, "~=", b):
            assert version_satisfies_constraint(a, ">=", b)
            assert a_maj == b_maj

    @given(_components, _components, _components, _components)
    def test_unknown_operator_is_permissive(self, a_maj: int, a_min: int, b_maj: int, b_min: int) -> None:
        """Unrecognised operators are accepted permissively (documented behaviour)."""
        a, b = _version_str(a_maj, a_min), _version_str(b_maj, b_min)
        assert version_satisfies_constraint(a, "?!", b) is True


class TestNormalizeConfig:
    """Invariants for _normalize_config."""

    # Keys drawn from aliases, their canonical targets, and arbitrary unrelated keys.
    _keys = st.sampled_from(sorted(set(KEY_ALIASES) | set(KEY_ALIASES.values()) | {"unrelated", "other"}))
    _configs = st.dictionaries(_keys, st.integers(), max_size=6)

    @given(_configs)
    def test_no_alias_survives_normalization(self, config: dict[str, int]) -> None:
        """After normalization, no raw alias key remains in the output."""
        normalized = _normalize_config(config)
        assert not (set(normalized) & set(KEY_ALIASES))

    @given(_configs)
    def test_idempotent(self, config: dict[str, int]) -> None:
        """Canonical keys map to themselves, so normalizing twice == once."""
        once = _normalize_config(config)
        assert _normalize_config(once) == once

    @given(_configs)
    def test_value_count_preserved_without_alias_collisions(self, config: dict[str, int]) -> None:
        """When no key and its alias coexist, normalization is key-count preserving."""
        # Build an input guaranteed free of alias/canonical collisions.
        canonical_to_aliases: dict[str, str] = {v: k for k, v in KEY_ALIASES.items()}
        safe = {
            k: v for k, v in config.items() if not (k in canonical_to_aliases and canonical_to_aliases[k] in config)
        }
        normalized = _normalize_config(safe)
        assert len(normalized) == len(safe)
