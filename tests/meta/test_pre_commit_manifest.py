"""Tests for the published pre-commit contract (issues #294, #295).

``.pre-commit-hooks.yaml`` is this repository's public API: every downstream
project resolves a hook ``id`` from it to an ``entry``, which pre-commit expects
to find as a console script installed from ``[project.scripts]``. Nothing in the
package imports either file, so no unit test covers the link between them.

Two layers guard it here:

* static checks that the manifest and ``pyproject.toml`` agree, which run in
  milliseconds and cover every published hook;
* one end-to-end run through ``pre-commit try-repo``, which proves a manifest
  entry really resolves to an executable console script.

This file lives in ``tests/meta/`` — exempt from the test-layout orphan check via
``[tool.check_test_layout] exempt_dirs`` — because it tests repository metadata
rather than a ``src/`` module.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess  # nosec B404
import sys
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import yaml

if TYPE_CHECKING:
    from typing import NoReturn

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HOOKS_YAML = _REPO_ROOT / ".pre-commit-hooks.yaml"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"


def _manifest() -> list[dict[str, Any]]:
    """Return the parsed ``.pre-commit-hooks.yaml`` hook definitions."""
    hooks = yaml.safe_load(_HOOKS_YAML.read_text(encoding="utf-8"))
    assert isinstance(hooks, list), "manifest must be a list of hook definitions"
    return hooks


def _console_scripts() -> dict[str, str]:
    """Return the ``[project.scripts]`` table from ``pyproject.toml``."""
    return dict(tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]["scripts"])


# ---------------------------------------------------------------------------
# Static contract: manifest <-> [project.scripts]
# ---------------------------------------------------------------------------
def test_hook_entries_match_console_scripts() -> None:
    """Every published hook entry is an installed console script, and vice versa.

    Both directions matter and fail differently. An ``entry`` with no console
    script breaks every consumer at hook-install time; a console script with no
    ``entry`` is a hook that was built and tested here but never published.
    """
    entries = {hook["entry"] for hook in _manifest()}
    scripts = set(_console_scripts())

    assert entries - scripts == set(), "hook entries with no matching [project.scripts] console script"
    assert scripts - entries == set(), "console scripts not published in .pre-commit-hooks.yaml"


def test_hook_ids_are_unique() -> None:
    """No hook id is defined twice.

    pre-commit resolves an id to the *first* matching definition, so a duplicate
    silently shadows the later one rather than erroring.
    """
    ids = [hook["id"] for hook in _manifest()]
    assert sorted(ids) == sorted(set(ids)), f"duplicate hook ids: {sorted({i for i in ids if ids.count(i) > 1})}"


def test_hook_entries_are_bare_script_names() -> None:
    """Entries name a console script rather than a path or interpreter invocation.

    ``language: python`` installs the package into an isolated environment and
    runs ``entry`` from its ``bin/``. A path (``src/...``) or a compound command
    (``python -m ...``) may work in this checkout and fail once installed.
    """
    for hook in _manifest():
        entry = hook["entry"]
        assert " " not in entry, f"{hook['id']}: entry must be a bare script name, got {entry!r}"
        assert "/" not in entry, f"{hook['id']}: entry must not be a path, got {entry!r}"
        assert "\\" not in entry, f"{hook['id']}: entry must not be a path, got {entry!r}"


def test_every_hook_declares_the_documented_fields() -> None:
    """Each hook carries the fields consumers and `pre-commit` rely on."""
    for hook in _manifest():
        for field in ("id", "name", "description", "entry", "language"):
            assert field in hook, f"{hook.get('id', '<unknown>')}: missing required field {field!r}"


# ---------------------------------------------------------------------------
# End-to-end through pre-commit (issues #184, #295)
# ---------------------------------------------------------------------------
# Phrases that indicate pre-commit itself could not run the hook environment
# (network, build backend, resolver, or an internal pre-commit crash) rather
# than a genuine wiring failure. When any appears we skip instead of failing,
# so a hostile environment does not break CI.
_ENV_FAILURE_MARKERS = (
    "InstallError",
    "Failed to install",
    "Could not install",
    "ResolutionImpossible",
    "Connection",
    "Temporary failure in name resolution",
    "Network is unreachable",
    "ReadTimeoutError",
    "SSLError",
    # pre-commit's generic banner for an internal crash (exit code 3). It is
    # printed for environment problems, never for hook-wiring errors (those get
    # clean messages like "No hook with id ..."). The most common offender is
    # GitHub's Windows runner, where the workspace (D:) and the pre-commit cache
    # (C:) sit on different drives: `ValueError: path is on mount 'D:', start on
    # mount 'C:'`.
    "An unexpected error has occurred",
    "path is on mount",
)

# Every skip below is individually defensible — a network-less build genuinely
# cannot be told apart from a broken one — but collectively they let this test
# pass without running anything, which is what issue #295 is about. Two tiers
# keep it honest without making CI flaky:
#
# * Missing tooling (git, pre-commit) is never transient. `UV_SYNC_ARGS` is
#   `--all-extras --all-groups`, so the lint group's pre-commit is installed in
#   every CI job; if it is absent under CI something is wrong with the
#   environment and a skip would hide it. These fail whenever CI is set.
# * A failed environment build or a timeout genuinely can be transient (a PyPI
#   blip, an offline runner). These stay skips unless RHIZA_REQUIRE_E2E=1, so a
#   designated job can demand a full run without every job going red on a blip.
#
# RHIZA_REQUIRE_E2E overrides both tiers: "1" demands a full run and turns every
# skip into a failure; "0" forces the lenient behaviour for an environment that
# genuinely cannot run pre-commit. Unset leaves the two tiers above in charge.
_REQUIRE_ENV = os.environ.get("RHIZA_REQUIRE_E2E")
_UNDER_CI = os.environ.get("CI", "").lower() in {"1", "true"}

# A repository that declares consistent versions for six of the published hooks.
# Deliberately no `[project] version`: check-bumpversion-config only demands a
# discoverable bumpversion config once a static version exists, so omitting it
# keeps the fixture passing without a [tool.bumpversion] table.
_FIXTURE_FILES = {
    ".python-version": "3.11\n",
    "pyproject.toml": '[project]\nname = "e2e"\nrequires-python = ">=3.11"\n',
    "rust-toolchain.toml": '[toolchain]\nchannel = "1.75.0"\n',
    "Cargo.toml": '[package]\nname = "e2e"\nrust-version = "1.75"\n',
    ".go-version": "1.22.0\n",
    "go.mod": "module e2e\n\ngo 1.22\n",
}

# The hooks whose `files:` patterns the fixture matches, and which must therefore
# run and pass. The rest match nothing and are reported as Skipped — including
# check-template-bundles, which is what keeps this test off the network.
#
# check-managed-files declares no `files:` at all, so it runs on every fixture file
# and passes because the fixture has no .rhiza/template.lock: nothing is owned
# upstream in a repo that was never synced.
_EXPECTED_TO_RUN = frozenset(
    {
        "check-python-version-consistency",
        "check-rust-version-consistency",
        "check-go-version-consistency",
        "check-bumpversion-config",
        "check-managed-files",
        "check-license-metadata",
    }
)

# pre-commit renders one line per hook: the name, dot padding, an optional
# parenthesised note, then the status. Matched loosely so padding width and the
# note's wording stay free to change.
_STATUS_RE = re.compile(r"^(?P<name>.*?)\.{3,}(?:\([^)]*\))?(?P<status>Passed|Failed|Skipped)\s*$")


def _skip_or_fail(reason: str, *, transient: bool) -> NoReturn:
    """Skip, or fail when this run is one that must not silently no-op.

    Args:
        reason: Why the end-to-end run cannot proceed.
        transient: True for conditions an unlucky environment can hit (build
            failure, timeout); False for missing tooling, which under CI means a
            broken environment rather than bad luck.
    """
    if _REQUIRE_ENV == "0":
        pytest.skip(reason)
    if _REQUIRE_ENV == "1" or (_UNDER_CI and not transient):
        pytest.fail(f"{reason}\n(Set RHIZA_REQUIRE_E2E=0 if this environment genuinely cannot run pre-commit.)")
    pytest.skip(reason)


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command, capturing text output, with a generous timeout."""
    return subprocess.run(  # nosec B603
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


def _pre_commit_command() -> list[str] | None:
    """Return the command that invokes pre-commit, or None if it is unavailable.

    The ``uvx`` fallback is what keeps this test alive: pre-commit is deliberately
    not a declared dependency of this project (every other gate reaches it through
    ``uvx`` too — see ``fmt`` in the root Makefile and .rhiza/make.d/quality.mk), so
    neither PATH nor the project venv has it. Without the fallback this test does not
    quietly skip — ``_skip_or_fail(transient=False)`` turns a missing pre-commit into
    a hard failure under CI.
    """
    if shutil.which("pre-commit") is not None:
        return ["pre-commit"]
    if importlib.util.find_spec("pre_commit") is not None:
        return [sys.executable, "-m", "pre_commit"]
    uvx = shutil.which("uvx")
    if uvx is not None:
        return [uvx, "pre-commit"]
    return None


# ``try-repo`` builds its shadow repo from **git**, so a source module that exists on
# disk but is not yet tracked is absent from the package pre-commit installs. Every
# hook importing it then dies at import time, while the rest of the suite — which
# imports from the working tree — passes. The result is a single red test whose output
# blames the hook rather than the staging area, so match it and say so. Only reachable
# locally: CI checks out a commit, where nothing is untracked by definition.
#
# Two exception types, because the package uses both import styles and they fail
# differently: ``from rhiza_hooks._x import y`` raises ModuleNotFoundError, while
# ``from rhiza_hooks import _x`` (as check_template_bundles does) raises ImportError.
_MISSING_PACKAGE_MODULE_RE = re.compile(
    r"ModuleNotFoundError: No module named '(?P<dotted>rhiza_hooks[\w.]*)'"
    r"|ImportError: cannot import name '(?P<name>\w+)' from 'rhiza_hooks'"
)


def _untracked_sources() -> list[str]:
    """Return the untracked files under ``src/``, as git reports them."""
    listed = _run(["git", "ls-files", "--others", "--exclude-standard", "src"], cwd=_REPO_ROOT)
    if listed.returncode != 0:
        return []
    return sorted(line.strip() for line in listed.stdout.splitlines() if line.strip())


def _fail_on_untracked_source(combined: str) -> None:
    """Fail with the real cause when an untracked module explains an import error.

    Silent when the two do not coincide, leaving the generic assertion to report
    whatever actually went wrong.
    """
    missing = _MISSING_PACKAGE_MODULE_RE.search(combined)
    untracked = _untracked_sources()
    if not (missing and untracked):
        return
    module = missing.group("dotted") or f"rhiza_hooks.{missing.group('name')}"
    listing = "\n".join(f"  {path}" for path in untracked)
    pytest.fail(
        f"try-repo could not import {module}, and these files under src/ are untracked:\n"
        f"{listing}\n\n"
        "`pre-commit try-repo` builds its shadow repo from git, so a module that is only on "
        "disk is missing from the package it installs. Run `git add` on the files above and "
        f"re-run.\n\nFull output:\n{combined}"
    )


def _hook_statuses(output: str) -> dict[str, str]:
    """Parse pre-commit's per-hook result lines into ``{hook name: status}``."""
    statuses = {}
    for line in output.splitlines():
        match = _STATUS_RE.match(line.rstrip())
        if match:
            statuses[match["name"].strip()] = match["status"]
    return statuses


@pytest.mark.timeout(600)
def test_manifest_hooks_run_through_pre_commit_try_repo(tmp_path: Path) -> None:
    """`pre-commit try-repo` builds this repo's hooks and runs every applicable one.

    Invoked without a hook id, ``try-repo`` loads the whole manifest, so every id
    is resolved in a single environment build. The hooks the fixture declares files
    for must pass; the rest report "no files to check" and are skipped by
    pre-commit, which is what keeps this test network-free.
    """
    if shutil.which("git") is None:
        _skip_or_fail("git is required for the end-to-end test", transient=False)

    base = _pre_commit_command()
    if base is None:
        _skip_or_fail("pre-commit is required for the end-to-end test", transient=False)

    for name, content in _FIXTURE_FILES.items():
        (tmp_path / name).write_text(content)

    init = _run(["git", "init"], cwd=tmp_path)
    assert init.returncode == 0, init.stderr
    # try-repo / --all-files operate on tracked files.
    _run(["git", "add", "-A"], cwd=tmp_path)

    try:
        result = _run([*base, "try-repo", str(_REPO_ROOT), "--all-files", "--verbose"], cwd=tmp_path)
    except FileNotFoundError:
        _skip_or_fail("pre-commit is not installed", transient=False)
    except subprocess.TimeoutExpired:
        _skip_or_fail("pre-commit try-repo timed out (slow/no network for the isolated build)", transient=True)

    combined = f"{result.stdout}\n{result.stderr}"

    if result.returncode != 0 and any(marker in combined for marker in _ENV_FAILURE_MARKERS):
        _skip_or_fail(f"pre-commit could not build the hook environment:\n{combined}", transient=True)

    if result.returncode != 0:
        _fail_on_untracked_source(combined)

    assert result.returncode == 0, f"try-repo failed:\n{combined}"

    # A clean exit alone would also be satisfied by every hook being skipped, so
    # assert on the per-hook statuses: the wiring is only proven by a hook that
    # pre-commit actually installed and ran.
    statuses = _hook_statuses(combined)
    assert statuses, f"could not parse any hook result lines from:\n{combined}"

    names = {hook["id"]: hook["name"] for hook in _manifest()}
    for hook_id in sorted(_EXPECTED_TO_RUN):
        name = names[hook_id]
        assert statuses.get(name) == "Passed", f"expected {hook_id} ({name!r}) to run and pass, got {statuses}"
