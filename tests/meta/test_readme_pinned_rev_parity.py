"""Tests that the README's install snippet works at the rev it tells people to pin (#366).

The Quick Start in ``README.md`` is this repo's install path: a consumer copies the
``repo:``/``rev:``/``hooks:`` block verbatim. pre-commit and prek resolve each hook ``id``
against ``.pre-commit-hooks.yaml`` **as it exists at the pinned rev** — not as it exists on
``main`` — so an id added after the last release makes the documented snippet fail with
``No hook with id ...`` for every new consumer, while the repo's own gates stay green.

That is exactly what happened: #360 published ``check-test-layout``, and the README listed
it under ``rev: v1.2.0``, a tag whose manifest holds twelve hooks and not that one.

Three existing checks all miss it, which is why this file exists:

* ``check_doc_examples.py`` (``/rhiza:quality`` gate 9) validates README fences by
  language — ``bash -n`` for shell, ``compile()`` for Python. ``yaml`` fences are reported
  "not checkable", and fifteen of the README's twenty fences are yaml, this one included.
* ``test_pre_commit_manifest.py`` enforces manifest <-> ``[project.scripts]``, which is why
  README and ``HEAD`` agree. Neither side is the *released* artifact.
* the template's README checks validate structure and links, not whether an id resolves.

This file lives in ``tests/meta/`` — exempt from the test-layout orphan check via
``[tool.check_test_layout] exempt_dirs`` — because it tests repository metadata rather
than a ``src/`` module.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_README = _REPO_ROOT / "README.md"

# The Quick Start block, up to the heading that begins the per-hook reference. Scoping the
# search matters: the per-hook sections further down carry `- id:` lines of their own, in
# `args:` examples that are deliberately not a full install snippet.
_QUICK_START_END = "## 📋 Available Hooks"

# `rev: v1.2.0  # Use the latest release`
_REV_RE = re.compile(r"^\s*rev:\s*(?P<rev>v[0-9][^\s#]*)", re.MULTILINE)
_ID_RE = re.compile(r"^\s*-\s+id:\s*(?P<id>[a-z][a-z0-9-]*)", re.MULTILINE)


def _quick_start() -> str:
    """Return the README text up to the per-hook reference section."""
    text = _README.read_text(encoding="utf-8")
    head, _, _ = text.partition(_QUICK_START_END)
    return head


def _pinned_rev() -> str:
    """Return the single rev the Quick Start tells consumers to pin."""
    revs = _REV_RE.findall(_quick_start())
    assert revs, "no `rev:` found in the README Quick Start"
    assert len(set(revs)) == 1, f"Quick Start pins more than one rev: {sorted(set(revs))}"
    return revs[0]


def _documented_ids() -> set[str]:
    """Return the hook ids the Quick Start tells consumers to enable."""
    ids = set(_ID_RE.findall(_quick_start()))
    assert ids, "no `- id:` entries found in the README Quick Start"
    return ids


def _newest_tag() -> str | None:
    """Return the newest reachable release tag, or None in a tagless checkout.

    This replaced a read of ``[project].version``, which no longer exists: the version is
    derived from the git tag by hatch-vcs, so the tag is what the README's ``rev:`` has to
    agree with. It is also what ``bump-my-version`` itself resolves the current version
    from when it rewrites that line, so the two now read the same source.
    """
    result = subprocess.run(  # nosec B603 B607
        ["git", "describe", "--tags", "--abbrev=0"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or None if result.returncode == 0 else None


def _manifest_at(rev: str) -> set[str] | None:
    """Return the hook ids in ``.pre-commit-hooks.yaml`` at *rev*, or None if unresolvable.

    None covers both "that tag does not exist yet" and "this checkout has no tags"; the
    caller distinguishes them, because they need different verdicts.
    """
    result = subprocess.run(  # nosec B603 B607
        ["git", "show", f"{rev}:.pre-commit-hooks.yaml"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return {hook["id"] for hook in yaml.safe_load(result.stdout)}


def _release_ordinal(rev: str) -> tuple[int, ...]:
    """Return a sortable key for a ``vX.Y.Z`` release tag.

    Deliberately hand-rolled rather than ``packaging.version.Version``: this repo does not
    depend on ``packaging``, and reaching for it here would mean asserting through a
    transitive dependency -- which deptry and the lowest-deps job would both be right to
    call out -- for a single ``>=``. Every tag this repo has ever cut is three integers,
    and :func:`test_every_documented_hook_exists_at_the_pinned_rev` is what checks that a
    rev names a real tag; this only has to order two of them.
    """
    parts = rev.lstrip("v").split(".")
    try:
        return tuple(int(part) for part in parts)
    except ValueError:  # pragma: no cover - a non-numeric tag is its own bug
        pytest.fail(f"cannot order release tag {rev!r}: expected vX.Y.Z")


def test_quick_start_does_not_pin_a_stale_rev() -> None:
    """The documented rev is not *behind* the newest release tag.

    `bump-my-version` rewrites this line on release (the `[[tool.bumpversion.files]]`
    entry for `rev: v{current_version}`), so a rev behind the newest tag means either the
    bump did not run or the line was hand-edited — and every published install snippet is
    then stale. That is #366 exactly: the README sat at `v1.2.0` through later releases.

    Not-behind rather than equal, which is what this asserted while the version was
    written in `[project].version`. With the version derived from the tag, a release
    commits the rewritten README *before* the tag it names exists, so for the life of that
    commit the rev is legitimately one release ahead of the newest tag. Requiring equality
    would fail every release PR; requiring not-behind still catches the staleness this
    file was written for, and
    :func:`test_every_documented_hook_exists_at_the_pinned_rev` covers the other
    direction by resolving the rev against real tags.

    Skips in a tagless checkout, which is a local-clone condition: CI fetches tags.
    """
    newest = _newest_tag()
    if newest is None:
        pytest.skip("no release tags in this checkout")
    assert _release_ordinal(_pinned_rev()) >= _release_ordinal(newest), (
        f"README pins {_pinned_rev()} but {newest} is already released — every install snippet we publish is stale"
    )


def test_every_documented_hook_exists_at_the_pinned_rev() -> None:
    """Every hook id in the Quick Start resolves at the rev the Quick Start pins.

    Skips, rather than fails, when the pinned tag does not exist. Two cases, both benign
    and both real in this repo:

    * **A release PR.** The version is bumped before the tag is cut, so the pinned rev is
      unreachable for the life of the PR. CLAUDE.md records this trap as the reason
      ``.pre-commit-config.yaml`` cannot consume this repo through a published ``rev:``;
      failing here would recreate it and make every release PR unmergeable.
    * **A tagless checkout.** CI fetches tags — ``pytest_rhiza.checks.test_release_tags``
      asserts against them and passes there — so this is a local-clone condition, not a
      way for the check to quietly never run.
    """
    rev = _pinned_rev()
    released = _manifest_at(rev)
    if released is None:
        reason = f"{rev} is not tagged in this checkout"
        if rev != _newest_tag():
            reason += " (expected during a release PR: the version is bumped before the tag exists)"
        pytest.skip(reason)

    missing = sorted(_documented_ids() - released)
    assert missing == [], (
        f"README tells consumers to pin {rev} and enable {missing}, "
        f"but {rev}'s .pre-commit-hooks.yaml does not define them. "
        "pre-commit resolves ids at the pinned rev, so the documented snippet fails with "
        "'No hook with id ...'. Cut a release containing them, or stop documenting them yet."
    )
