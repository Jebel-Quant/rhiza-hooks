#!/usr/bin/env python3
"""Validate template-bundles.yml structure and consistency.

This script validates the template bundles configuration file to ensure:
1. Valid YAML syntax
2. Required fields are present
3. Bundle dependencies reference existing bundles
4. File paths follow expected patterns
5. Examples reference valid bundles

The script reads .rhiza/template.yml to find the template repository,
then fetches template-bundles.yml from that remote repository.

The implementation is split across focused modules — :mod:`rhiza_hooks._bundles_fetch`
(obtaining a document), :mod:`rhiza_hooks._bundles_validate` (structural checks),
and :mod:`rhiza_hooks._bundles_config` (reading ``.rhiza/template.yml``). This
module is the CLI/orchestration layer and re-exports those helpers so
``rhiza_hooks.check_template_bundles`` remains the single public import surface.

Those three modules are themselves private, so the package's public surface is
unchanged by the split. Within them a leading underscore marks a helper with no
caller outside its own file — which is why this module imports only unprefixed
names from them.

Exit codes:
  0 - Validation passed
  1 - Validation failed
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from typing import Any

from rhiza_hooks import _bundles_validate, _repo
from rhiza_hooks._bundles_config import get_config_data
from rhiza_hooks._bundles_fetch import (
    FETCH_ATTEMPTS,
    FETCH_TIMEOUT_SECONDS,
    Fetcher,
    fetch_remote_bundles,
)


def _get_config_path(args: argparse.Namespace) -> Path:
    """Get the configuration file path from arguments or default location."""
    if args.filenames:
        return Path(args.filenames[0])
    return _repo.find_repo_root() / ".rhiza" / "template.yml"


def _load_and_validate_config(config_path: Path) -> tuple[dict[str, Any], set[str]] | None:
    """Load and validate configuration file.

    Returns:
        (config, templates_set) if validation succeeds, otherwise ``None``
    """
    config = get_config_data(config_path)
    if config is None:
        print(f"Could not load configuration from {config_path}, skipping validation")
        return None

    templates_to_check = config.get("templates")
    if templates_to_check is None or not isinstance(templates_to_check, list):
        print(f"No templates field in {config_path}, skipping bundle validation")
        return None

    templates_set: set[str] = {str(t) for t in templates_to_check}
    return config, templates_set


def _report_errors(header: str, errors: list[str]) -> None:
    """Print a failure ``header`` followed by each error as a bullet, on stderr."""
    print(header, file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)


def _validate_remote_bundles(
    template_repo: str,
    template_branch: str,
    templates_set: set[str],
    *,
    fetcher: Fetcher,
    attempts: int = FETCH_ATTEMPTS,
    timeout: float = FETCH_TIMEOUT_SECONDS,
) -> tuple[dict[Any, Any] | None, list[str]]:
    """Fetch and validate remote bundles.

    ``fetcher`` is required rather than defaulted: this is the function that would
    otherwise reach the network, so making the dependency explicit is what keeps a
    test from silently doing so. The default lives once, on :func:`main`.

    Returns:
        Tuple of (bundles_data, errors) or (None, errors) if fetch fails
    """
    print(f"Fetching template bundles from {template_repo} (branch: {template_branch})")
    print(f"Checking templates: {', '.join(sorted(templates_set))}")

    fetched = fetcher(template_repo, template_branch, attempts=attempts, timeout=timeout)
    if fetched.data is None:
        _report_errors("\n✗ Failed to fetch template bundles:", fetched.errors)
        return None, fetched.errors

    # data is narrowed to dict[Any, Any] by the `is None` guard above.
    data = fetched.data

    # Validate top-level structure
    errors = _bundles_validate.validate_top_level_fields(data)
    if errors:
        _report_errors("\n✗ Template bundles validation failed:", errors)
        return None, errors

    bundles = data.get("bundles", {})
    if not isinstance(bundles, dict):
        errors = ["'bundles' must be a dictionary"]
        _report_errors("\n✗ Template bundles validation failed:", errors)
        return None, errors

    return data, []


def _validate_templates_in_bundles(templates_set: set[str], bundles: dict[Any, Any], config_path: Path) -> list[str]:
    """Validate that requested templates exist in the remote bundles and are well-formed.

    >>> bundles = {"core": {"description": "Core files", "files": [".gitignore"]}}
    >>> _validate_templates_in_bundles({"core"}, bundles, Path("template.yml"))
    []

    A template this repo asks for but the template repository does not publish is
    the error this hook exists to catch:

    >>> _validate_templates_in_bundles({"nope"}, bundles, Path("template.yml"))
    ["Template 'nope' specified in template.yml not found in remote bundles"]

    A published bundle missing its required fields is reported too:

    >>> _validate_templates_in_bundles({"core"}, {"core": {}}, Path("template.yml"))
    ["Bundle 'core' missing 'description'", "Bundle 'core' missing 'files'"]
    """
    return _bundles_validate.validate_selected_bundles(
        templates_set,
        bundles,
        lambda t: f"Template '{t}' specified in {config_path} not found in remote bundles",
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Build the argument parser, then parse and validate ``argv``."""
    parser = argparse.ArgumentParser(description="Validate template-bundles.yml from remote template repository")
    parser.add_argument(
        "filenames",
        nargs="*",
        help="Filenames to check (should be .rhiza/template.yml)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip the remote bundles fetch (e.g. for offline commits) and pass",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=FETCH_ATTEMPTS - 1,
        help="Number of retries for transient network failures, after the initial attempt (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=FETCH_TIMEOUT_SECONDS,
        help="Per-request network timeout in seconds (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    if args.retries < 0:
        parser.error("--retries must be non-negative")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    return args


def _ensure_utf8_output() -> None:
    """Reconfigure both output streams to UTF-8 so the ✓/✗ glyphs never crash a non-UTF-8 console.

    Both, not just stdout: the ``✓`` goes to stdout on the success path but the ``✗``
    headers from :func:`_report_errors` go to stderr, so guarding one stream would
    leave the failure path — the one a user is most likely to be reading — able to
    raise ``UnicodeEncodeError`` on a cp1252 console.
    """
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _run_remote_validation(
    config: dict[str, Any],
    templates_set: set[str],
    config_path: Path,
    retries: int,
    timeout: float,
    fetcher: Fetcher,
) -> int:
    """Fetch remote bundles and validate the requested templates; return an exit code."""
    template_repo = config.get("template-repository")
    template_branch = config.get("template-branch")
    if not template_repo or not template_branch:
        print(f"Missing template-repository or template-branch in {config_path}", file=sys.stderr)
        return 1

    data, _fetch_errors = _validate_remote_bundles(
        template_repo,
        template_branch,
        templates_set,
        fetcher=fetcher,
        attempts=retries + 1,
        timeout=timeout,
    )
    if data is None:
        return 1

    bundles = data.get("bundles", {})
    errors = _validate_templates_in_bundles(templates_set, bundles, config_path)
    if errors:
        _report_errors("\n✗ Template bundles validation failed:", errors)
        return 1

    print("✓ Template bundles validation passed!")
    return 0


def main(argv: list[str] | None = None, fetcher: Fetcher = fetch_remote_bundles) -> int:
    """Main entry point.

    ``fetcher`` is the one place the real network call is named. The console script
    takes the default; a test passes a fake document source as an argument rather than
    rebinding this module's ``fetch_remote_bundles`` global.
    """
    _ensure_utf8_output()

    args = _parse_args(argv)

    if args.offline:
        print("Offline mode: skipping remote template bundles validation")
        return 0

    config_path = _get_config_path(args)

    # Load and validate configuration. A None result means validation was
    # skipped (missing config or no templates field); both cases pass.
    result = _load_and_validate_config(config_path)
    if result is None:
        return 0
    config, templates_set = result

    return _run_remote_validation(config, templates_set, config_path, args.retries, args.timeout, fetcher)


if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
