"""Keep CLAUDE.md's pins and managed-file snapshot in step with the repo (#433).

CLAUDE.md quotes the template ``ref:``, the ``rhiza-task`` CLI the ``Makefile`` shim pins
and the ``pytest-rhiza`` version ``[tool.rhiza-task]`` sets, and it lists every file the
template syncs. Every ``/rhiza:update`` invalidates some of that, and nothing noticed until
a ``/rhiza:quality`` run did: the snapshot was refreshed by hand after six syncs running
(#199, #272, #313, #361, #379, #432).

**What is checked, and where it is anchored.** The prose is full of historical versions
that must not be "corrected" — "left this list at v1.4.0", "0.6.0 is the first release
that skips" — so the pins are not scraped from it. Instead CLAUDE.md carries one HTML
comment, ``<!-- rhiza-current: ref=… rhiza-task=… pytest-rhiza=… -->``, stating which
values it believes are current, and this file holds that comment against the sources:

* ``ref`` against ``ref:`` in ``.rhiza/template.yml``;
* ``rhiza-task`` against ``RHIZA_TASK ?= rhiza-task@…`` in ``Makefile``;
* ``pytest-rhiza`` against the ``pytest-rhiza`` key of ``[tool.rhiza-task]`` in
  ``pyproject.toml``.

A marker is easy to bump without touching the prose it summarises, so each value must
also appear in CLAUDE.md outside the comment. That is deliberately weak — it cannot tell
which mention is the current one — but it turns "updated the marker only" from silent
into a failure whenever the prose never caught up at all.

The file list is checked against ``.rhiza/template.lock``'s ``files:`` block, which is the
record of what the last sync actually placed. A path counts as mentioned when CLAUDE.md
contains either the full path or its basename, because the snapshot groups files under
per-directory headings (``### `.github/` `` then ``dependabot.yml``).

All three inputs are local files, so unlike the template-parity tests nothing here
touches the network. This file lives in ``tests/meta/``, exempt from the test-layout
orphan check, because it tests repository metadata rather than a ``src/`` module.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CLAUDE_MD = _REPO_ROOT / "CLAUDE.md"
_TEMPLATE_YML = _REPO_ROOT / ".rhiza" / "template.yml"
_TEMPLATE_LOCK = _REPO_ROOT / ".rhiza" / "template.lock"
_MAKEFILE = _REPO_ROOT / "Makefile"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

_MARKER_RE = re.compile(r"<!--\s*rhiza-current:(?P<body>[^>]*?)-->")
_MARKER_KEYS = frozenset({"ref", "rhiza-task", "pytest-rhiza"})
_RHIZA_TASK_RE = re.compile(r"^RHIZA_TASK\s*\?=\s*rhiza-task@(?P<version>\S+)\s*$", re.MULTILINE)
_PYTEST_RHIZA_RE = re.compile(r"^pytest-rhiza\s*==\s*(?P<version>\S+)$")


def _claude_md() -> str:
    """Return CLAUDE.md's text."""
    return _CLAUDE_MD.read_text(encoding="utf-8")


def _marker() -> dict[str, str]:
    """Parse the single ``rhiza-current`` comment into ``{key: value}``."""
    matches = list(_MARKER_RE.finditer(_claude_md()))
    assert len(matches) == 1, (
        f"CLAUDE.md must carry exactly one `<!-- rhiza-current: ... -->` comment, found {len(matches)}"
    )
    pairs: dict[str, str] = {}
    for token in matches[0].group("body").split():
        key, sep, value = token.partition("=")
        assert sep, f"malformed rhiza-current entry {token!r}: expected key=value"
        assert value, f"rhiza-current entry {token!r} has an empty value"
        assert key not in pairs, f"rhiza-current names {key!r} twice"
        pairs[key] = value
    return pairs


def _prose() -> str:
    """Return CLAUDE.md with the ``rhiza-current`` comment removed."""
    return _MARKER_RE.sub("", _claude_md())


def _template_ref() -> str:
    """Return ``ref:`` from ``.rhiza/template.yml``."""
    config = yaml.safe_load(_TEMPLATE_YML.read_text(encoding="utf-8"))
    ref = config.get("ref")
    assert isinstance(ref, str), f"no `ref:` in {_TEMPLATE_YML}"
    return ref


def _makefile_rhiza_task() -> str:
    """Return the version in the shim's ``RHIZA_TASK ?= rhiza-task@…`` line."""
    match = _RHIZA_TASK_RE.search(_MAKEFILE.read_text(encoding="utf-8"))
    assert match is not None, f"no `RHIZA_TASK ?= rhiza-task@...` line in {_MAKEFILE}"
    return match.group("version")


def _pyproject_pytest_rhiza() -> str:
    """Return the version ``[tool.rhiza-task]`` pins ``pytest-rhiza`` to."""
    with _PYPROJECT.open("rb") as handle:
        table = tomllib.load(handle).get("tool", {}).get("rhiza-task", {})
    spec = table.get("pytest-rhiza")
    assert isinstance(spec, str), "no `pytest-rhiza` key in [tool.rhiza-task]"
    match = _PYTEST_RHIZA_RE.match(spec.strip())
    assert match is not None, f"[tool.rhiza-task] pytest-rhiza is {spec!r}; expected `pytest-rhiza==X`"
    return match.group("version")


def _lock_files() -> list[str]:
    """Return the ``files:`` block of ``.rhiza/template.lock``."""
    lock = yaml.safe_load(_TEMPLATE_LOCK.read_text(encoding="utf-8"))
    files = lock.get("files")
    assert isinstance(files, list), f"no `files:` list in {_TEMPLATE_LOCK}"
    assert files, f"empty `files:` list in {_TEMPLATE_LOCK}"
    return [str(path) for path in files]


def test_marker_names_exactly_the_tracked_pins() -> None:
    """The comment carries the three pins this file checks — no more, no fewer.

    An unknown key would be a pin nobody checks, and a missing one a pin that silently
    stopped being checked.
    """
    assert set(_marker()) == _MARKER_KEYS


@pytest.mark.parametrize(
    ("key", "source", "actual"),
    [
        ("ref", ".rhiza/template.yml `ref:`", _template_ref),
        ("rhiza-task", "Makefile `RHIZA_TASK ?=`", _makefile_rhiza_task),
        ("pytest-rhiza", "pyproject.toml [tool.rhiza-task] pytest-rhiza", _pyproject_pytest_rhiza),
    ],
    ids=["ref", "rhiza-task", "pytest-rhiza"],
)
def test_marker_pin_matches_its_source(key: str, source: str, actual: Callable[[], str]) -> None:
    """Each pin in the comment equals the value its source file holds."""
    live = actual()
    stated = _marker().get(key)
    assert stated == live, (
        f"CLAUDE.md's rhiza-current says {key}={stated} but {source} is {live}. "
        "A sync moved it: refresh the prose that quotes it, then the comment."
    )


@pytest.mark.parametrize("key", sorted(_MARKER_KEYS))
def test_marker_pin_appears_in_the_prose(key: str) -> None:
    """Each pinned value is quoted somewhere outside the comment.

    Guards against bumping the comment while leaving every prose mention behind.
    """
    value = _marker()[key]
    assert value in _prose(), (
        f"rhiza-current says {key}={value}, but CLAUDE.md never mentions {value} outside "
        "the comment — the prose was not refreshed along with it."
    )


def test_every_synced_file_is_mentioned() -> None:
    """Every path the last sync placed appears in CLAUDE.md, by full path or basename."""
    text = _claude_md()
    missing = [path for path in _lock_files() if path not in text and Path(path).name not in text]
    assert missing == [], (
        f"template.lock's `files:` lists {missing}, which CLAUDE.md never mentions. "
        "Add them to the managed-files snapshot."
    )
