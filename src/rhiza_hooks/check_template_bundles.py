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
from rhiza_hooks._bundles_config import _get_config_data
from rhiza_hooks._bundles_fetch import (
    _FETCH_ATTEMPTS,
    _FETCH_TIMEOUT_SECONDS,
    _fetch_remote_bundles,
)


def _get_config_path(args: argparse.Namespace) -> Path:
    """Get the configuration file path from arguments or default location."""
    if args.filenames:
        return Path(args.filenames[0])
    return _repo.find_repo_root() / ".rhiza" / "template.yml"


def _load_and_validate_config(config_path: Path) -> tuple[dict[str, Any] | None, set[str] | None]:
    """Load and validate configuration file.

    Returns:
        Tuple of (config, templates_set) or (None, None) if validation fails
    """
    config = _get_config_data(config_path)
    if config is None:
        print(f"Could not load configuration from {config_path}, skipping validation")
        return None, None

    templates_to_check = config.get("templates")
    if templates_to_check is None or not isinstance(templates_to_check, list):
        print(f"No templates field in {config_path}, skipping bundle validation")
        return None, None

    templates_set: set[str] = {str(t) for t in templates_to_check}
    return config, templates_set


def _validate_remote_bundles(
    template_repo: str,
    template_branch: str,
    templates_set: set[str],
    attempts: int = _FETCH_ATTEMPTS,
    timeout: float = _FETCH_TIMEOUT_SECONDS,
) -> tuple[dict[Any, Any] | None, list[str]]:
    """Fetch and validate remote bundles.

    Returns:
        Tuple of (bundles_data, errors) or (None, errors) if fetch fails
    """
    print(f"Fetching template bundles from {template_repo} (branch: {template_branch})")
    print(f"Checking templates: {', '.join(sorted(templates_set))}")

    fetched = _fetch_remote_bundles(template_repo, template_branch, attempts=attempts, timeout=timeout)
    if fetched.data is None:
        print("\n✗ Failed to fetch template bundles:")
        for error in fetched.errors:
            print(f"  - {error}")
        return None, fetched.errors

    # data is narrowed to dict[Any, Any] by the `is None` guard above.
    data = fetched.data

    # Validate top-level structure
    errors = _bundles_validate._validate_top_level_fields(data)
    if errors:
        print("\n✗ Template bundles validation failed:")
        for error in errors:
            print(f"  - {error}")
        return None, errors

    bundles = data.get("bundles", {})
    if not isinstance(bundles, dict):
        print("\n✗ Template bundles validation failed:")
        print("  - 'bundles' must be a dictionary")
        return None, ["'bundles' must be a dictionary"]

    return data, []


def _validate_templates_in_bundles(templates_set: set[str], bundles: dict[Any, Any], config_path: Path) -> list[str]:
    """Validate that requested templates exist in the remote bundles and are well-formed."""
    return _bundles_validate._validate_selected_bundles(
        templates_set,
        bundles,
        lambda t: f"Template '{t}' specified in {config_path} not found in remote bundles",
    )


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
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
        default=_FETCH_ATTEMPTS - 1,
        help="Number of retries for transient network failures, after the initial attempt (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=_FETCH_TIMEOUT_SECONDS,
        help="Per-request network timeout in seconds (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    if args.retries < 0:
        parser.error("--retries must be non-negative")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    if args.offline:
        print("Offline mode: skipping remote template bundles validation")
        return 0

    # Get configuration path
    config_path = _get_config_path(args)

    # Load and validate configuration
    config, templates_set = _load_and_validate_config(config_path)
    # _load_and_validate_config returns these values in lockstep:
    #   - success path: (config_dict, templates_set)  -> both are not None
    #   - early-exit path: (None, None)               -> both are None
    # Therefore `config is None` and `templates_set is None` are equivalent here.
    # Under this invariant, mutating `or` to `and` does not change behavior.
    if config is None or templates_set is None:  # pragma: no mutate
        return 0

    # Get template repository and branch
    template_repo = config.get("template-repository")
    template_branch = config.get("template-branch")

    if not template_repo or not template_branch:
        print(f"Missing template-repository or template-branch in {config_path}")
        return 1

    # Fetch and validate remote bundles
    data, _fetch_errors = _validate_remote_bundles(
        template_repo,
        template_branch,
        templates_set,
        attempts=args.retries + 1,
        timeout=args.timeout,
    )
    if data is None:
        return 1

    # Validate templates
    bundles = data.get("bundles", {})
    errors = _validate_templates_in_bundles(templates_set, bundles, config_path)

    if errors:
        print("\n✗ Template bundles validation failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("✓ Template bundles validation passed!")
    return 0


if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
