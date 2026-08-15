#!/usr/bin/env python3
"""Load and fetch template-bundles documents into a typed result.

This module is responsible solely for *obtaining* a template-bundles document —
from a local file, from already-fetched bytes, or from a remote GitHub
repository — and returning it as a :class:`BundlesDoc`. Structural validation of
the returned mapping lives in :mod:`rhiza_hooks._bundles_validate`.
"""

from __future__ import annotations

import sys
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import yaml

from rhiza_hooks._yaml import YamlError, YamlFailure, load_yaml_mapping

# Remote fetch is retried on transient network errors before giving up. Two
# attempts = one initial try plus one retry, with a short linear backoff.
# These are defaults; the CLI exposes `--retries` and `--timeout` to override.
FETCH_ATTEMPTS = 2
FETCH_BACKOFF_SECONDS = 1.0
FETCH_TIMEOUT_SECONDS = 10.0


class _Opener(Protocol):
    """The ``urlopen``-shaped callable that performs a single HTTP GET.

    Injected rather than reached for so tests can supply a fake without patching
    this module's ``urlopen`` binding by name — a fetch is then exercised through
    the same argument every caller uses.
    """

    def __call__(self, url: str, *, timeout: float) -> AbstractContextManager[Any]:
        """Open ``url`` and return a response context manager exposing ``read()``."""
        ...


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


class Fetcher(Protocol):
    """The :func:`fetch_remote_bundles`-shaped callable a validation run obtains its document from.

    The same reasoning as :class:`_Opener`, one layer up. ``check_template_bundles``
    injects this rather than reaching for the module global, so a test supplies a fake
    document through the argument every caller uses instead of rebinding
    ``check_template_bundles.fetch_remote_bundles`` by dotted name — a rebinding that
    pins the wiring rather than the behaviour, and breaks on any rename.

    Unprefixed, unlike :class:`_Opener`: this module's convention is that a leading
    underscore marks a helper with no caller outside its own file, and this one is
    named in another module's signatures.
    """

    def __call__(self, repo: str, branch: str, *, attempts: int, timeout: float) -> BundlesDoc:
        """Fetch the template-bundles document for ``repo``/``branch``."""
        ...


def load_local_bundles(bundles_path: Path) -> BundlesDoc:
    """Load and parse a local template-bundles file into a :class:`BundlesDoc`.

    This is the local-file counterpart to :func:`fetch_remote_bundles` and part
    of this module's cross-module surface — :mod:`rhiza_hooks._bundles_validate`
    calls it to load a document before validating it.
    """
    result = load_yaml_mapping(bundles_path)
    if not isinstance(result, YamlFailure):
        return BundlesDoc(result, [])

    messages = {
        YamlError.NOT_FOUND: f"Template bundles file not found: {bundles_path}",
        YamlError.INVALID: f"Invalid YAML: {result.detail}",
        YamlError.EMPTY: "Template bundles file is empty",
        YamlError.NOT_MAPPING: "Template bundles file must be a dictionary",
    }
    return BundlesDoc(None, [messages[result.kind]])


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


def _fetch_once(url: str, timeout: float, repo: str, branch: str, opener: _Opener) -> bytes | BundlesDoc | str:
    """Perform a single fetch attempt with ``opener``.

    Returns the raw response ``bytes`` on success; a :class:`BundlesDoc` carrying
    a permanent HTTP error (e.g. 404) that must not be retried; or an error
    ``str`` describing a transient network/timeout failure that may be retried.
    """
    try:
        with opener(url, timeout=timeout) as response:
            content: bytes = response.read()
    except HTTPError as e:
        if e.code == 404:
            return BundlesDoc(None, [f"Template bundles file not found in repository {repo} (branch: {branch})"])
        return BundlesDoc(None, [f"HTTP error fetching template bundles: {e.code} {e.reason}"])
    except URLError as e:
        return f"Error fetching template bundles from {url}: {e.reason}"
    except TimeoutError:
        return f"Timeout fetching template bundles from {url}"
    return content


def _log_failed_attempt(attempt: int, attempts: int, error: str, backoff: float) -> None:
    """Log a failed fetch attempt, sleeping with linear backoff if retries remain.

    Backoff grows linearly (backoff, 2*backoff, ...). The last attempt has
    nowhere to retry, so it is logged without a backoff.
    """
    if attempt + 1 < attempts:
        delay = backoff * (attempt + 1)
        print(f"  Attempt {attempt + 1}/{attempts} failed: {error}; retrying in {delay:.1f}s", file=sys.stderr)
        time.sleep(delay)
    else:
        print(f"  Attempt {attempt + 1}/{attempts} failed: {error}", file=sys.stderr)


def fetch_remote_bundles(
    repo: str,
    branch: str,
    attempts: int = FETCH_ATTEMPTS,
    backoff: float = FETCH_BACKOFF_SECONDS,
    timeout: float = FETCH_TIMEOUT_SECONDS,
    opener: _Opener = urlopen,
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
        opener: Performs one HTTP GET; defaults to :func:`urllib.request.urlopen`.
            Only the https URL built below is ever passed to it — tests substitute a
            fake instead of rebinding this module's ``urlopen``.

    Returns:
        A :class:`BundlesDoc` with the parsed mapping on success, or errors.
    """
    # The scheme and host are literal, and `repo`/`branch` interpolate only into the
    # path that follows them, so this URL is https by construction. There used to be a
    # `urlparse(url).scheme != "https"` guard here "for bandit B310" (#340): it could
    # not fire for any argument, the only way to cover the line was a test that
    # monkeypatched this module's `urlparse`, and a control that needs a patched parser
    # to trigger asserts a safety property nobody is checking. If a caller-supplied URL
    # is ever wanted, validate it *there*, where it can actually be untrusted.
    #
    # The `nosec B310` marker on the `opener` default above went with it, and for a
    # related reason: B310 flags *calls* to urlopen, which this module never makes —
    # every request goes through the injected `opener`, and `urlopen` appears only as
    # that parameter's default value. So the marker was silencing a finding bandit does
    # not raise. Confirmed by running the configured hook without it (`.bandit` skips
    # B101 only, so B310 was live): bandit passes.
    #
    # Written without the leading `#` on purpose: bandit greps comments for that token
    # and parses whatever follows as test ids, so spelling it in prose logs a dozen
    # "Test in comment: ... is not a test name" warnings and quietly registers a
    # suppression on this line.
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/.rhiza/template-bundles.yml"

    # pragma below: equivalent mutant — the final `return BundlesDoc(None, errors)` is only
    # reached after a transient-error iteration has reassigned `errors` (success and HTTP
    # errors return early), so for attempts >= 1 this initial value is never the one returned.
    errors: list[str] = []  # pragma: no mutate
    for attempt in range(attempts):
        outcome = _fetch_once(url, timeout, repo, branch, opener)
        if isinstance(outcome, BundlesDoc):
            return outcome  # permanent HTTP error — do not retry
        if isinstance(outcome, bytes):
            return _parse_remote_bundles(outcome)
        # Transient failure (network/timeout): record it, then back off and retry.
        errors = [outcome]
        _log_failed_attempt(attempt, attempts, outcome, backoff)

    return BundlesDoc(None, errors)
