"""Tests for the shared ``rhiza_hooks._version`` parsing and comparison helpers.

Combines unit tests and property-based (Hypothesis) invariants for the
dotted-numeric version handling shared by the Rust and Go hooks.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rhiza_hooks._version import _padded, parse_version, same_version, version_at_least

# ---------------------------------------------------------------------------
# Unit tests: parse_version
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1", (1,)),
        ("1.75", (1, 75)),
        ("1.75.0", (1, 75, 0)),
        ("1.22.3", (1, 22, 3)),
        ("  1.22.3\n", (1, 22, 3)),
        ("1.21rc1", (1, 21)),
        ("1.21-beta.2", (1, 21)),
        ("0.0.0", (0, 0, 0)),
    ],
)
def test_parse_version_extracts_components(text: str, expected: tuple[int, ...]) -> None:
    """The leading dotted-numeric run becomes an integer tuple; suffixes are dropped."""
    assert parse_version(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "   ", "stable", "beta", "nightly", "nightly-2024-01-01", "default", "local", "go1.22", "v1.2.3"],
)
def test_parse_version_rejects_non_numeric(text: str) -> None:
    """Anything that does not start with a digit has no version to extract."""
    assert parse_version(text) is None


def test_parse_version_ignores_trailing_dot() -> None:
    """A trailing dot is not part of the numeric run (pins the regex's grouping)."""
    assert parse_version("1.22.") == (1, 22)


# ---------------------------------------------------------------------------
# Unit tests: _padded
# ---------------------------------------------------------------------------
def test_padded_extends_with_zeros() -> None:
    """Padding appends exactly the missing number of zero components."""
    assert _padded((1, 22), 4) == (1, 22, 0, 0)


def test_padded_is_identity_at_full_length() -> None:
    """Padding to the tuple's own length leaves it untouched."""
    assert _padded((1, 22, 3), 3) == (1, 22, 3)


# ---------------------------------------------------------------------------
# Unit tests: version_at_least
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("version", "minimum", "expected"),
    [
        ((1, 75, 0), (1, 75), True),
        ((1, 75), (1, 75, 0), True),
        ((1, 75), (1, 75, 1), False),
        ((1, 76), (1, 75), True),
        ((1, 74), (1, 75), False),
        ((1, 10), (1, 9), True),
        ((1, 9), (1, 10), False),
        ((2, 0), (1, 99), True),
    ],
)
def test_version_at_least(version: tuple[int, ...], minimum: tuple[int, ...], expected: bool) -> None:
    """Comparison is component-wise after zero-padding the shorter tuple."""
    assert version_at_least(version, minimum) is expected


# ---------------------------------------------------------------------------
# Unit tests: same_version
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("1.22", "1.22.0", True),
        ("1.22.0", "1.22", True),
        ("1.22.0.0", "1.22", True),
        ("1.22", "1.22.1", False),
        ("1.9", "1.10", False),
        ("stable", "stable", True),
        ("stable", "beta", False),
        ("1.75", "stable", False),
        ("stable", "1.75", False),
    ],
)
def test_same_version(left: str, right: str, expected: bool) -> None:
    """Numeric sides compare after padding; a non-numeric side falls back to string equality."""
    assert same_version(left, right) is expected


def test_same_version_non_numeric_ignores_whitespace_difference() -> None:
    """The string fallback is exact: differing whitespace makes two named channels differ."""
    assert same_version("stable", "stable ") is False


# ---------------------------------------------------------------------------
# Property-based tests (Hypothesis)
# ---------------------------------------------------------------------------
_components = st.lists(st.integers(min_value=0, max_value=99), min_size=1, max_size=4)


def _render(parts: list[int]) -> str:
    """Render integer components as a dotted version string."""
    return ".".join(str(part) for part in parts)


@given(_components)
def test_property_parse_version_roundtrip(parts: list[int]) -> None:
    """Rendering components and parsing them back returns the same tuple."""
    assert parse_version(_render(parts)) == tuple(parts)


@given(_components)
def test_property_version_at_least_is_reflexive(parts: list[int]) -> None:
    """Every version is at least itself."""
    version = tuple(parts)
    assert version_at_least(version, version) is True


@given(_components, _components)
def test_property_at_least_is_a_total_order(left: list[int], right: list[int]) -> None:
    """For any pair, at least one direction of >= holds; both hold exactly when equal."""
    a, b = tuple(left), tuple(right)
    forward = version_at_least(a, b)
    backward = version_at_least(b, a)
    assert forward or backward
    assert (forward and backward) == same_version(_render(left), _render(right))


@given(_components, st.integers(min_value=0, max_value=3))
def test_property_trailing_zeros_do_not_change_a_version(parts: list[int], extra: int) -> None:
    """Appending zero components leaves the version unchanged."""
    assert same_version(_render(parts), _render([*parts, *([0] * extra)])) is True
