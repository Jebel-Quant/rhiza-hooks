"""Guard `.rhiza/template.yml`'s ``exclude:`` block against dead entries (issue #378).

An ``exclude:`` entry names a path the template ships that this repo refuses. When
upstream stops shipping that path the entry excludes nothing, but it still reads as a
live decision with a paragraph of rationale attached, and the next person has to
re-derive whether it matters. That happened twice in one day — #374 pruned the entries
the template had stopped shipping, #375 dropped the two retired workflows — and both were
hand-audits. Together they removed 23 lines that no gate would ever have flagged.

``tests/meta/test_pre_commit_template_parity.py`` already solves the identical problem
one layer up: a waiver there must name a hook the template still declares. An
``exclude:`` entry is a waiver in exactly that sense, so it is held to the same rule.

How the shipped set is derived, and why not from the lock:

* **The template repository is the oracle, at the ref this repo pins.** Bundle ownership
  in rhiza is expressed through the filesystem — every file a bundle ships lives under
  ``bundles/<bundle>/`` in the template repo — so the shipped set is the union of those
  directories over the bundles the selected profiles and templates expand to.
* **`.rhiza/template.lock` is not the oracle.** It is regenerated only on sync, so it
  records the state at the *last* sync and legitimately disagrees with ``template.yml``
  between a hand edit and the next ``/rhiza:update``. It is used below for one narrower
  question it genuinely answers — what the last sync actually did — and never to decide
  whether an entry is dead.

**Source path versus destination path.** The sync has been observed matching ``exclude:``
against a file's path inside the template clone (``bundles/legal/SECURITY.md``) rather
than its destination in this repo (``SECURITY.md``); the lock at the currently pinned ref
shows destination matching instead. Both spellings are therefore accepted here: this file
asserts that an entry *names a file the selected bundles ship*, which is the necessary
condition for it to bite under either rule. It deliberately does not claim the entry does
bite — CLAUDE.md's warning to verify that before relying on an exclusion still stands, and
``test_live_exclusions_kept_their_file_out_of_the_last_sync`` below is as close as a test
can get to checking it without running a sync.

Same network dependency and the same skip condition as the pre-commit parity test: a
transport failure skips (an offline machine cannot tell a healthy repository from a broken
one), an HTTP error fails (a 404 means the pinned ref is wrong, which is a real finding).
"""

from __future__ import annotations

import io
import tarfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_TEMPLATE_YML = _REPO_ROOT / ".rhiza" / "template.yml"
_TEMPLATE_LOCK = _REPO_ROOT / ".rhiza" / "template.lock"

# The archive is ~600 KB, so it wants more headroom than a single raw file fetch.
_FETCH_TIMEOUT_SECONDS = 60.0

# Where bundle-owned files live inside the template clone.
_BUNDLES_ROOT = "bundles"


def _pinned_template() -> tuple[str, str]:
    """Return the ``(repository, ref)`` this repo pins in ``.rhiza/template.yml``."""
    config = _template_config()
    repository = config.get("repository") or config.get("template-repository")
    ref = config.get("ref") or config.get("template-branch")
    assert isinstance(repository, str), f"no template repository in {_TEMPLATE_YML}"
    assert isinstance(ref, str), f"no pinned ref in {_TEMPLATE_YML}"
    return repository, ref


def _template_config() -> dict[str, Any]:
    """The raw parsed ``.rhiza/template.yml``.

    Read raw rather than through ``rhiza_hooks._config_schema.normalize_config``: that
    helper maps ``profiles`` onto the canonical ``templates`` key, so a config carrying
    both — as this one does — loses whichever comes first. The sync unions the two (the
    lock records ``github-project`` and ``legal`` under separate keys and ships the files
    of both), and this file needs that union.
    """
    parsed = yaml.safe_load(_TEMPLATE_YML.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict), f"{_TEMPLATE_YML} is not a mapping"
    return parsed


def _declared_names(config: dict[str, Any], *keys: str) -> list[str]:
    """Collect the string entries of every list-valued ``keys`` present in ``config``."""
    names: list[str] = []
    for key in keys:
        value = config.get(key)
        if isinstance(value, list):
            names.extend(str(entry) for entry in value)
    return names


def _fetch(url: str, *, what: str) -> bytes:
    """GET ``url``, skipping on a transport failure and failing on an HTTP error."""
    # The scheme is fixed by each caller's literal prefix, but the repository and ref come
    # from a file, so bandit sees a computed URL and cannot rule out `file:` or a custom
    # scheme (B310). Re-assert it, as `rhiza_hooks._bundles_fetch` does for the same
    # reason, which is what makes the suppressions below true rather than merely quiet.
    # The sibling parity test needs no `noqa`: it builds its URL in the same function, so
    # ruff can see the literal prefix. Here the URL arrives as an argument and it cannot.
    assert urlparse(url).scheme == "https", f"refusing to fetch a non-https URL: {url}"
    try:
        with urllib.request.urlopen(url, timeout=_FETCH_TIMEOUT_SECONDS) as response:  # noqa: S310  # nosec B310
            return bytes(response.read())
    except urllib.error.HTTPError as exc:  # pragma: no cover - needs a bad pin to reach
        pytest.fail(f"HTTP {exc.code} fetching {what} from {url}: the pinned ref or the path is wrong")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        pytest.skip(f"cannot reach {url} ({exc}); network-dependent parity check skipped")


def _fetch_bundles_doc(repository: str, ref: str) -> dict[str, Any]:
    """Fetch and parse the template's ``.rhiza/template-bundles.yml`` at ``ref``."""
    url = f"https://raw.githubusercontent.com/{repository}/{ref}/.rhiza/template-bundles.yml"
    parsed = yaml.safe_load(_fetch(url, what="the bundles document"))
    assert isinstance(parsed, dict), f"bundles document at {ref} is not a mapping"
    return parsed


def _fetch_tracked_paths(repository: str, ref: str) -> set[str]:
    """Every file path in the template repository at ``ref``, relative to its root.

    Taken from the source archive rather than the GitHub tree API: codeload needs no
    token and imposes no per-IP rate limit, which matters on shared CI runners. Symlinks
    count as files — a bundle directory may point at a file elsewhere in the template
    rather than hold its own copy.
    """
    url = f"https://codeload.github.com/{repository}/tar.gz/{ref}"
    archive = _fetch(url, what="the template archive")
    paths: set[str] = set()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in tar:
            if not (member.isfile() or member.issym()):
                continue
            # GitHub archives are rooted at a single `<repo>-<ref>/` directory.
            _root, _, relative = member.name.partition("/")
            if relative:
                paths.add(relative)
    assert paths, f"the archive of {repository}@{ref} contained no files"
    return paths


def _expand_bundles(names: list[str], bundles_doc: dict[str, Any]) -> set[str]:
    """Expand profile and bundle names to the transitive set of bundles they select.

    Profiles expand to their ``bundles:`` list; a bundle expands to itself plus its
    ``requires:``, followed transitively. Requirements are included because the sync
    ships them too, and a wider shipped set can only make this file *less* likely to
    call a live entry dead.
    """
    profiles = bundles_doc.get("profiles") or {}
    bundles = bundles_doc.get("bundles") or {}

    pending = list(names)
    unknown: list[str] = []
    selected: set[str] = set()
    while pending:
        name = pending.pop()
        if name in profiles:
            pending.extend(str(bundle) for bundle in profiles[name].get("bundles") or [])
            continue
        if name not in bundles:
            unknown.append(name)
            continue
        if name in selected:
            continue
        selected.add(name)
        pending.extend(str(required) for required in bundles[name].get("requires") or [])

    assert not unknown, (
        f"{_TEMPLATE_YML.name} selects {sorted(set(unknown))}, which the template's bundles "
        "document declares as neither a profile nor a bundle"
    )
    return selected


def _matches(entry: str, path: str) -> bool:
    """Whether ``entry`` names ``path`` exactly or is a directory containing it."""
    entry = entry.rstrip("/")
    return path == entry or path.startswith(f"{entry}/")


@pytest.fixture(scope="module")
def exclude_entries() -> list[str]:
    """The paths this repo excludes from the sync."""
    return _declared_names(_template_config(), "exclude")


@pytest.fixture(scope="module")
def shipped_paths() -> set[str]:
    """Paths the selected bundles ship, in both source and destination spelling.

    A bundle's files live under ``bundles/<bundle>/`` in the template clone and land at
    the remainder of that path in this repo, so each shipped file contributes both — see
    the module docstring on why either spelling is accepted.
    """
    repository, ref = _pinned_template()
    selected = _expand_bundles(
        _declared_names(_template_config(), "profiles", "templates"), _fetch_bundles_doc(repository, ref)
    )
    tracked = _fetch_tracked_paths(repository, ref)

    paths: set[str] = set()
    for bundle in selected:
        prefix = f"{_BUNDLES_ROOT}/{bundle}/"
        for source in tracked:
            if source.startswith(prefix):
                paths.add(source)
                paths.add(source[len(prefix) :])
    assert paths, f"the selected bundles {sorted(selected)} own no files at {repository}@{ref}"
    return paths


def test_every_exclude_entry_names_a_file_the_template_ships(
    exclude_entries: list[str], shipped_paths: set[str]
) -> None:
    """An exclusion for a path the template no longer ships is dead weight, so it is reported.

    This is the check #374 and #375 performed by hand. Removing a dead entry is safe by
    construction: it suppresses nothing, because there is nothing left to suppress.
    """
    repository, ref = _pinned_template()
    dead = [entry for entry in exclude_entries if not any(_matches(entry, path) for path in shipped_paths)]
    assert dead == [], (
        f"exclude: entries in {_TEMPLATE_YML.name} naming paths {repository}@{ref} no longer ships: "
        f"{dead}. Drop them (and their rationale comment) — they exclude nothing. If one names a "
        "file the template still ships, check the spelling against bundles/<bundle>/ upstream."
    )


def test_live_exclusions_kept_their_file_out_of_the_last_sync(exclude_entries: list[str]) -> None:
    """An exclusion in force at the last sync must not appear among the files it synced.

    The closest a test can get to CLAUDE.md's "verify such an entry actually bites":
    ``.rhiza/template.lock`` records what the sync did, so a path listed under ``files:``
    was written into this repo despite the exclusion. Only entries the lock itself records
    under ``exclude:`` are checked — ``template.yml`` may have gained one since the last
    sync, and an exclusion cannot be blamed for a sync that predates it.
    """
    lock = yaml.safe_load(_TEMPLATE_LOCK.read_text(encoding="utf-8"))
    assert isinstance(lock, dict), f"{_TEMPLATE_LOCK} is not a mapping"
    in_force = set(_declared_names(lock, "exclude")) & set(exclude_entries)
    synced = _declared_names(lock, "files")

    ignored = {entry: [path for path in synced if _matches(entry, path)] for entry in sorted(in_force)}
    offenders = {entry: paths for entry, paths in ignored.items() if paths}
    assert offenders == {}, (
        f"the last sync wrote files the exclusion should have kept out: {offenders}. The exclusion "
        "did not bite — restore this repo's copy of those paths and treat the entry as advisory "
        "until the sync engine honours it."
    )


def test_every_shipped_source_path_has_its_destination_spelling(shipped_paths: set[str]) -> None:
    """The fixture's both-spellings contract, asserted rather than described.

    Executable documentation of the matching rule the module docstring explains: a file
    the template ships is offered to the other tests both as ``bundles/<bundle>/<path>``
    and as ``<path>``, so an ``exclude:`` entry written either way is recognised.
    """
    sources = sorted(path for path in shipped_paths if path.startswith(f"{_BUNDLES_ROOT}/"))
    missing = [source for source in sources if source.split("/", 2)[2] not in shipped_paths]
    assert missing == [], f"source paths offered without their destination spelling: {missing}"
