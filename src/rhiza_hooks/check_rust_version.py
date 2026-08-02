#!/usr/bin/env python3
"""Check that the Rust version is consistent across project files.

A Rust project states its version in up to three places:

* ``rust-toolchain.toml`` — ``[toolchain] channel``, the toolchain rustup
  installs for this checkout;
* ``rust-toolchain`` — the legacy form of the same file, either TOML or a bare
  channel name on a single line;
* ``Cargo.toml`` — ``rust-version`` under ``[package]`` and/or
  ``[workspace.package]``, the crate's minimum supported Rust version (MSRV).

The hook enforces that the two toolchain files agree with each other, that the
two MSRV declarations agree with each other, and that the pinned toolchain is
not older than the declared MSRV (a pin below the MSRV cannot build the crate).
Named channels (``stable``, ``beta``, ``nightly-2024-01-01``) carry no version
number, so they are accepted without comparison.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path
from typing import Any

from rhiza_hooks._repo import find_repo_root
from rhiza_hooks._version import parse_version, same_version, version_at_least

CARGO_FILE = "Cargo.toml"
TOOLCHAIN_FILE = "rust-toolchain.toml"
LEGACY_TOOLCHAIN_FILE = "rust-toolchain"

# Cargo.toml tables that may declare an MSRV, keyed by the label used in errors.
_MSRV_TABLES = {
    "package": ("package",),
    "workspace.package": ("workspace", "package"),
}


def _table(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    """Walk nested TOML tables, returning an empty table for any missing hop.

    Args:
        data: Parsed TOML document.
        *keys: Table names to descend through, outermost first.

    Returns:
        The nested table, or an empty dict if any hop is absent or not a table.
    """
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _string_value(table: dict[str, Any], key: str) -> str | None:
    """Return ``table[key]`` as a stripped string, or None if absent/blank/non-string."""
    value = table.get(key)
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _load_toml(path: Path) -> dict[str, Any] | None:
    """Parse a TOML file.

    Args:
        path: File to read.

    Returns:
        The parsed document, or None when the file is missing, unreadable, or
        malformed. As in the Python-version hook, an unusable file is treated as
        "unspecified" rather than crashing the commit.
    """
    if not path.exists():
        return None
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (tomllib.TOMLDecodeError, OSError):
        return None


def read_legacy_toolchain(path: Path) -> str | None:
    """Read the channel from a legacy ``rust-toolchain`` file.

    rustup accepts either the modern TOML form or a bare channel name, so TOML
    is tried first and plain text is the fallback.

    Args:
        path: Path to the ``rust-toolchain`` file.

    Returns:
        The channel string, or None if the file is missing, unreadable, or
        declares no channel.
    """
    if not path.exists():
        return None
    try:
        text = path.read_text()
    except OSError:
        return None

    stripped = text.strip()
    if not stripped:
        return None

    try:
        data = tomllib.loads(stripped)
    except tomllib.TOMLDecodeError:
        # Not TOML: the whole file is the channel name (the legacy format).
        return stripped

    return _string_value(_table(data, "toolchain"), "channel")


def get_toolchain_channels(repo_root: Path) -> dict[str, str]:
    """Collect the pinned toolchain channels declared in the repository.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        Mapping of filename to channel string, containing only the files that
        exist and actually declare a channel.
    """
    channels: dict[str, str] = {}

    data = _load_toml(repo_root / TOOLCHAIN_FILE)
    if data is not None:
        channel = _string_value(_table(data, "toolchain"), "channel")
        if channel is not None:
            channels[TOOLCHAIN_FILE] = channel

    legacy = read_legacy_toolchain(repo_root / LEGACY_TOOLCHAIN_FILE)
    if legacy is not None:
        channels[LEGACY_TOOLCHAIN_FILE] = legacy

    return channels


def get_cargo_rust_versions(repo_root: Path) -> dict[str, str]:
    """Collect the MSRVs declared in ``Cargo.toml``.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        Mapping of table label (``package`` / ``workspace.package``) to the
        ``rust-version`` string declared there.
    """
    data = _load_toml(repo_root / CARGO_FILE)
    if data is None:
        return {}

    versions: dict[str, str] = {}
    for label, keys in _MSRV_TABLES.items():
        value = _string_value(_table(data, *keys), "rust-version")
        if value is not None:
            versions[label] = value
    return versions


def _check_channels_agree(channels: dict[str, str]) -> list[str]:
    """Report a disagreement between ``rust-toolchain.toml`` and ``rust-toolchain``."""
    modern = channels.get(TOOLCHAIN_FILE)
    legacy = channels.get(LEGACY_TOOLCHAIN_FILE)
    if modern is None or legacy is None or same_version(modern, legacy):
        return []
    return [
        f"Rust toolchain mismatch: {TOOLCHAIN_FILE} pins channel {modern}, but {LEGACY_TOOLCHAIN_FILE} pins {legacy}"
    ]


def _check_msrvs_agree(msrvs: dict[str, str]) -> list[str]:
    """Report a disagreement between the ``[package]`` and ``[workspace.package]`` MSRVs."""
    package = msrvs.get("package")
    workspace = msrvs.get("workspace.package")
    if package is None or workspace is None or same_version(package, workspace):
        return []
    return [
        f"Rust version mismatch: {CARGO_FILE} [package] rust-version is {package}, "
        f"but [workspace.package] rust-version is {workspace}"
    ]


def _is_below_msrv(channel_version: tuple[int, ...], msrv: str) -> bool:
    """Whether *channel_version* is below the MSRV *msrv*.

    Args:
        channel_version: Parsed components of the pinned toolchain channel.
        msrv: Raw ``rust-version`` text from ``Cargo.toml``.

    Returns:
        True only when *msrv* carries a version number that the channel fails to
        reach; False for a non-numeric MSRV, which gives nothing to compare.
    """
    msrv_version = parse_version(msrv)
    if msrv_version is None:
        return False
    return not version_at_least(channel_version, msrv_version)


def _channel_msrv_violations(source: str, channel: str, msrvs: dict[str, str]) -> list[str]:
    """Report every declared MSRV that the toolchain pinned in *source* fails to satisfy.

    Args:
        source: Filename the channel was declared in, used in the error message.
        channel: Raw channel string, e.g. ``"1.75.0"`` or ``"stable"``.
        msrvs: Declared MSRVs, keyed by the ``Cargo.toml`` table label.

    Returns:
        One error per unsatisfied MSRV, ordered by table label; empty for a named
        channel (stable/beta/nightly-<date>), which has no version to compare.
    """
    channel_version = parse_version(channel)
    if channel_version is None:
        return []
    return [
        f"Rust version mismatch: {source} pins channel {channel}, "
        f"but {CARGO_FILE} [{label}] rust-version is {msrv} "
        f"(the pinned toolchain must be at least the MSRV)"
        for label, msrv in sorted(msrvs.items())
        if _is_below_msrv(channel_version, msrv)
    ]


def _check_channel_satisfies_msrv(channels: dict[str, str], msrvs: dict[str, str]) -> list[str]:
    """Report every pinned toolchain that is older than a declared MSRV."""
    return [
        error
        for source, channel in sorted(channels.items())
        for error in _channel_msrv_violations(source, channel, msrvs)
    ]


def check_version_consistency(repo_root: Path) -> list[str]:
    """Check Rust version consistency across project files.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        List of error messages (empty if consistent, or if the repository
        declares no Rust versions at all).
    """
    channels = get_toolchain_channels(repo_root)
    msrvs = get_cargo_rust_versions(repo_root)

    return [
        *_check_channels_agree(channels),
        *_check_msrvs_agree(msrvs),
        *_check_channel_satisfies_msrv(channels, msrvs),
    ]


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the hook."""
    parser = argparse.ArgumentParser(description="Check Rust version consistency")
    parser.add_argument(
        "filenames",
        nargs="*",
        help="Filenames (ignored, checks repo root)",
    )
    parser.parse_args(argv)  # validate/consume pre-commit's filename args; result unused

    repo_root = find_repo_root()
    errors = check_version_consistency(repo_root)

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    return 0


if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
