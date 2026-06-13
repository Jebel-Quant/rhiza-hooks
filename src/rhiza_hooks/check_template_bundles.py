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

Exit codes:
  0 - Validation passed
  1 - Validation failed
"""

from __future__ import annotations

import argparse
import io
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen

import yaml

from rhiza_hooks._repo import find_repo_root

# Remote fetch is retried on transient network errors before giving up. Two
# attempts = one initial try plus one retry, with a short linear backoff.
_FETCH_ATTEMPTS = 2
_FETCH_BACKOFF_SECONDS = 1.0


@dataclass(frozen=True)
class BundlesDoc:
    """Outcome of loading/parsing a template-bundles document.

    ``data`` holds the parsed mapping on success and is ``None`` on failure;
    ``errors`` carries the failure messages (empty on success). The two are
    mutually exclusive, so callers branch on ``data is None`` — which also lets
    the type checker narrow ``data`` to ``dict`` on the success path without a
    cast.
    """

    data: dict[Any, Any] | None
    errors: list[str]


def _load_yaml_file(bundles_path: Path) -> BundlesDoc:
    """Load and parse a local YAML file into a :class:`BundlesDoc`."""
    if not bundles_path.exists():
        return BundlesDoc(None, [f"Template bundles file not found: {bundles_path}"])

    try:
        with open(bundles_path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return BundlesDoc(None, [f"Invalid YAML: {e}"])

    if data is None:
        return BundlesDoc(None, ["Template bundles file is empty"])

    return BundlesDoc(data, [])


def _validate_top_level_fields(data: dict[Any, Any]) -> list[str]:
    """Validate required top-level fields."""
    errors = []
    required_fields = {"version", "bundles"}
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    return errors


def _validate_bundle_structure(
    bundle_name: str,
    bundle_config: Any,
    bundle_names: set[str],
) -> list[str]:
    """Validate a single bundle's structure and dependencies."""
    errors = []

    if not isinstance(bundle_config, dict):
        errors.append(f"Bundle '{bundle_name}' must be a dictionary")
        return errors

    # Check required fields
    if "description" not in bundle_config:
        errors.append(f"Bundle '{bundle_name}' missing 'description'")

    if "files" not in bundle_config:
        errors.append(f"Bundle '{bundle_name}' missing 'files'")
    elif not isinstance(bundle_config["files"], list):
        errors.append(f"Bundle '{bundle_name}' 'files' must be a list")

    # Validate dependencies
    if "requires" in bundle_config:
        if not isinstance(bundle_config["requires"], list):
            errors.append(f"Bundle '{bundle_name}' 'requires' must be a list")
        else:
            for dep in bundle_config["requires"]:
                if dep not in bundle_names:
                    errors.append(f"Bundle '{bundle_name}' requires non-existent bundle '{dep}'")

    if "recommends" in bundle_config:
        if not isinstance(bundle_config["recommends"], list):
            errors.append(f"Bundle '{bundle_name}' 'recommends' must be a list")
        else:
            for dep in bundle_config["recommends"]:
                if dep not in bundle_names:
                    errors.append(f"Bundle '{bundle_name}' recommends non-existent bundle '{dep}'")

    return errors


def _validate_examples(examples: Any, bundle_names: set[str]) -> list[str]:
    """Validate examples section."""
    errors = []

    if not isinstance(examples, dict):
        errors.append("'examples' must be a dictionary")
        return errors

    for example_name, example_config in examples.items():
        if "templates" in example_config:
            if not isinstance(example_config["templates"], list):
                errors.append(f"Example '{example_name}' 'templates' must be a list")
            else:
                for template in example_config["templates"]:
                    # core is auto-included, we don't validate it
                    if template != "core" and template not in bundle_names:
                        errors.append(f"Example '{example_name}' references non-existent bundle '{template}'")

    return errors


def _validate_metadata(metadata: dict[Any, Any], bundles: dict[Any, Any]) -> list[str]:
    """Validate metadata section."""
    errors = []

    if "total_bundles" in metadata:
        expected_count = len(bundles)
        actual_count = metadata["total_bundles"]
        if actual_count != expected_count:
            errors.append(
                f"Metadata 'total_bundles' ({actual_count}) doesn't match actual bundle count ({expected_count})"
            )

    return errors


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

    template_names: set[str] = set(templates)
    return template_names


def _parse_remote_bundles(content: bytes) -> BundlesDoc:
    """Parse fetched template-bundles.yml content into a :class:`BundlesDoc`."""
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        return BundlesDoc(None, [f"Invalid YAML in remote template bundles: {e}"])

    if data is None:
        return BundlesDoc(None, ["Remote template bundles file is empty"])

    if not isinstance(data, dict):
        return BundlesDoc(None, ["Remote template bundles must be a dictionary"])

    return BundlesDoc(data, [])


def _fetch_remote_bundles(
    repo: str,
    branch: str,
    attempts: int = _FETCH_ATTEMPTS,
    backoff: float = _FETCH_BACKOFF_SECONDS,
) -> BundlesDoc:
    """Fetch template-bundles.yml from a remote GitHub repository.

    Transient network failures (`URLError`/`TimeoutError`) are retried up to
    ``attempts`` times with a linear backoff. HTTP errors (e.g. 404) are
    permanent and returned immediately without retrying.

    Args:
        repo: GitHub repository in 'owner/repo' format
        branch: Branch name
        attempts: Total number of fetch attempts (initial try + retries)
        backoff: Base seconds to sleep between attempts (multiplied by attempt number)

    Returns:
        A :class:`BundlesDoc` with the parsed mapping on success, or errors.
    """
    # Construct GitHub raw content URL
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/.rhiza/template-bundles.yml"

    # Validate URL scheme for security (bandit B310)
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return BundlesDoc(None, [f"Invalid URL scheme: {parsed.scheme}. Only https is allowed."])

    # pragma below: equivalent mutant — the final `return BundlesDoc(None, errors)` is only
    # reached after a transient-error iteration has reassigned `errors` (success and HTTP
    # errors return early), so for attempts >= 1 this initial value is never the one returned.
    errors: list[str] = []  # pragma: no mutate
    for attempt in range(attempts):
        try:
            with urlopen(url, timeout=10) as response:  # noqa: S310  # nosec B310
                content = response.read()
        except HTTPError as e:
            if e.code == 404:
                return BundlesDoc(None, [f"Template bundles file not found in repository {repo} (branch: {branch})"])
            return BundlesDoc(None, [f"HTTP error fetching template bundles: {e.code} {e.reason}"])
        except URLError as e:
            errors = [f"Error fetching template bundles from {url}: {e.reason}"]
        except TimeoutError:
            errors = [f"Timeout fetching template bundles from {url}"]
        else:
            return _parse_remote_bundles(content)
        # Transient failure: back off before the next attempt (linear: backoff, 2*backoff, ...).
        if attempt + 1 < attempts:
            time.sleep(backoff * (attempt + 1))

    return BundlesDoc(None, errors)


def _validate_selected_bundles(
    templates: set[str],
    bundles: dict[Any, Any],
    missing_message: Callable[[str], str],
) -> list[str]:
    """Validate that each requested template exists in ``bundles`` and is well-formed.

    Shared by the local-file and remote-fetch paths; they differ only in the
    "not found" wording, supplied via ``missing_message``.

    Args:
        templates: Template names requested in the rhiza config.
        bundles: The ``bundles`` mapping from a template-bundles document.
        missing_message: Builds the error string for a template absent from ``bundles``.

    Returns:
        List of error messages (empty if every requested template is valid).
    """
    errors: list[str] = []
    bundle_names: set[str] = set(bundles.keys())

    for template in templates:
        if template not in bundle_names:
            errors.append(missing_message(template))

    for template in templates:
        if template in bundles:
            errors.extend(_validate_bundle_structure(template, bundles[template], bundle_names))

    return errors


def validate_template_bundles(bundles_path: Path, templates_to_check: set[str] | None = None) -> tuple[bool, list[str]]:
    """Validate template bundles configuration.

    Args:
        bundles_path: Path to template-bundles.yml
        templates_to_check: Optional set of template names to validate. If None, validate all.

    Returns:
        Tuple of (success, error_messages)
    """
    # Load YAML file
    loaded = _load_yaml_file(bundles_path)
    if loaded.data is None:
        return False, loaded.errors
    # data is narrowed to dict[Any, Any] by the `is None` guard above.
    data = loaded.data

    # Validate top-level fields
    errors = _validate_top_level_fields(data)
    if errors:
        return False, errors

    # Validate bundles section
    bundles = data.get("bundles", {})
    if not isinstance(bundles, dict):
        return False, ["'bundles' must be a dictionary"]

    bundle_names: set[str] = set(bundles.keys())

    if templates_to_check is not None:
        # Validate only the requested subset (existence + structure).
        errors.extend(
            _validate_selected_bundles(
                templates_to_check,
                bundles,
                lambda t: f"Template '{t}' specified in .rhiza/template.yml not found in bundles",
            )
        )
    else:
        # Validate every declared bundle, plus the examples and metadata sections.
        for bundle_name in bundle_names:
            errors.extend(_validate_bundle_structure(bundle_name, bundles[bundle_name], bundle_names))
        if "examples" in data:
            errors.extend(_validate_examples(data["examples"], bundle_names))
        if "metadata" in data:
            errors.extend(_validate_metadata(data["metadata"], bundles))

    return len(errors) == 0, errors


def _get_config_path(args: argparse.Namespace) -> Path:
    """Get the configuration file path from arguments or default location."""
    if args.filenames:
        return Path(args.filenames[0])
    return find_repo_root() / ".rhiza" / "template.yml"


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

    templates_set: set[str] = set(templates_to_check)
    return config, templates_set


def _validate_remote_bundles(
    template_repo: str, template_branch: str, templates_set: set[str], config_path: Path
) -> tuple[dict[Any, Any] | None, list[str]]:
    """Fetch and validate remote bundles.

    Returns:
        Tuple of (bundles_data, errors) or (None, errors) if fetch fails
    """
    print(f"Fetching template bundles from {template_repo} (branch: {template_branch})")
    print(f"Checking templates: {', '.join(sorted(templates_set))}")

    fetched = _fetch_remote_bundles(template_repo, template_branch)
    if fetched.data is None:
        print("\n✗ Failed to fetch template bundles:")
        for error in fetched.errors:
            print(f"  - {error}")
        return None, fetched.errors

    # data is narrowed to dict[Any, Any] by the `is None` guard above.
    data = fetched.data

    # Validate top-level structure
    errors = _validate_top_level_fields(data)
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
    return _validate_selected_bundles(
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
    args = parser.parse_args(argv)

    if args.offline:
        print("Offline mode: skipping remote template bundles validation")
        return 0

    # Get configuration path
    config_path = _get_config_path(args)

    # Load and validate configuration
    config, templates_set = _load_and_validate_config(config_path)
    # pragma below: equivalent mutant — _load_and_validate_config returns (None, None)
    # or (config, set) as a pair, so `config is None` and `templates_set is None` are
    # always equal and `or`->`and` cannot change the outcome.
    if config is None or templates_set is None:  # pragma: no mutate
        return 0

    # Get template repository and branch
    template_repo = config.get("template-repository")
    template_branch = config.get("template-branch")

    if not template_repo or not template_branch:
        print(f"Missing template-repository or template-branch in {config_path}")
        return 1

    # Fetch and validate remote bundles
    data, _fetch_errors = _validate_remote_bundles(template_repo, template_branch, templates_set, config_path)
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
