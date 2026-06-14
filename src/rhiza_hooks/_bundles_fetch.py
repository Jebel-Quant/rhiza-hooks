#!/usr/bin/env python3
"""Load and fetch template-bundles documents into a typed result.

This module is responsible solely for *obtaining* a template-bundles document —
from a local file, from already-fetched bytes, or from a remote GitHub
repository — and returning it as a :class:`BundlesDoc`. Structural validation of
the returned mapping lives in :mod:`rhiza_hooks._bundles_validate`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen

import yaml

# Remote fetch is retried on transient network errors before giving up. Two
# attempts = one initial try plus one retry, with a short linear backoff.
# These are defaults; the CLI exposes `--retries` and `--timeout` to override.
_FETCH_ATTEMPTS = 2
_FETCH_BACKOFF_SECONDS = 1.0
_FETCH_TIMEOUT_SECONDS = 10.0


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
    timeout: float = _FETCH_TIMEOUT_SECONDS,
) -> BundlesDoc:
    """Fetch template-bundles.yml from a remote GitHub repository.

    Transient network failures (`URLError`/`TimeoutError`) are retried up to
    ``attempts`` times with a linear backoff, and each failed attempt is logged
    so CI failures are diagnosable. HTTP errors (e.g. 404) are permanent and
    returned immediately without retrying.

    Args:
        repo: GitHub repository in 'owner/repo' format
        branch: Branch name
        attempts: Total number of fetch attempts (initial try + retries)
        backoff: Base seconds to sleep between attempts (multiplied by attempt number)
        timeout: Per-request socket timeout in seconds

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
            with urlopen(url, timeout=timeout) as response:  # noqa: S310  # nosec B310
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
        # Transient failure: log it, then back off before the next attempt
        # (linear: backoff, 2*backoff, ...). The last attempt has nowhere to
        # retry, so it is logged without a backoff.
        if attempt + 1 < attempts:
            delay = backoff * (attempt + 1)
            print(f"  Attempt {attempt + 1}/{attempts} failed: {errors[0]}; retrying in {delay:.1f}s")
            time.sleep(delay)
        else:
            print(f"  Attempt {attempt + 1}/{attempts} failed: {errors[0]}")

    return BundlesDoc(None, errors)
