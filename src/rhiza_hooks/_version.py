#!/usr/bin/env python3
"""Shared dotted-numeric version parsing and comparison.

Rust and Go both express toolchain pins and minimum-supported versions as plain
dotted numbers (``1.75``, ``1.75.0``, ``1.22.3``), occasionally with a
pre-release suffix (``1.21rc1``) or a named channel (``stable``). Comparing them
is the same operation in both hooks: take the leading numeric components,
zero-pad the shorter side, and compare the resulting tuples — so ``1.22`` and
``1.22.0`` are the same version, and ``1.9`` is below ``1.10``.

Unlike Python's PEP 440 specifiers, neither ecosystem writes comparison
operators into these fields, so there is no specifier grammar to parse here.
"""

from __future__ import annotations

import re

# Anchored at the start: a leading dotted-numeric run is the version, and any
# trailing suffix (``rc1``, ``-beta``) is ignored. Strings that do not start
# with a digit (``stable``, ``nightly-2024-01-01``, ``default``) yield no match.
_LEADING_NUMERIC = re.compile(r"\d+(?:\.\d+)*")


def parse_version(text: str) -> tuple[int, ...] | None:
    """Parse the leading dotted-numeric components of a version string.

    Args:
        text: Raw version text, e.g. ``"1.75.0"``, ``"1.21rc1"`` or ``"stable"``.

    Returns:
        Tuple of integer components, or None when *text* does not begin with a
        dotted-numeric version.

    >>> parse_version("1.75.0")
    (1, 75, 0)
    >>> parse_version("1.21rc1")
    (1, 21)
    >>> parse_version("stable") is None
    True
    """
    match = _LEADING_NUMERIC.match(text.strip())
    if match is None:
        return None
    return tuple(int(part) for part in match.group(0).split("."))


def _padded(version: tuple[int, ...], length: int) -> tuple[int, ...]:
    """Zero-extend *version* to exactly *length* components."""
    return version + (0,) * (length - len(version))


def version_at_least(version: tuple[int, ...], minimum: tuple[int, ...]) -> bool:
    """Check whether *version* is greater than or equal to *minimum*.

    Args:
        version: Parsed version components.
        minimum: Parsed components of the lower bound.

    Returns:
        True if *version* is at least *minimum*, comparing component-wise after
        zero-padding the shorter tuple.

    >>> version_at_least((1, 22), (1, 22, 0))
    True
    >>> version_at_least((1, 9), (1, 10))
    False
    """
    length = max(len(version), len(minimum))
    return _padded(version, length) >= _padded(minimum, length)


def same_version(left: str, right: str) -> bool:
    """Check whether two raw version strings denote the same version.

    Falls back to an exact string comparison when either side is not
    dotted-numeric, so named channels such as ``stable`` still compare sensibly.

    Args:
        left: First raw version string.
        right: Second raw version string.

    Returns:
        True if both denote the same version.

    >>> same_version("1.22", "1.22.0")
    True
    >>> same_version("stable", "stable")
    True
    """
    left_parsed = parse_version(left)
    right_parsed = parse_version(right)
    if left_parsed is None or right_parsed is None:
        return left == right
    length = max(len(left_parsed), len(right_parsed))
    return _padded(left_parsed, length) == _padded(right_parsed, length)
