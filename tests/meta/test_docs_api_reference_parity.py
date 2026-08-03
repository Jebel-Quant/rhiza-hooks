"""Tests that the published API reference covers every module (issue #322).

``docs/api-reference/`` and the ``nav:`` block of ``mkdocs.yml`` are both
hand-maintained, and nothing in the package imports either — so a module added to
``src/rhiza_hooks/`` without a page produces no error anywhere. That is exactly how
the reference came to cover 15 of 21 modules, leaving four *shipped hooks*
(``check-bumpversion-config``, ``check-license-metadata``, ``check-managed-files``,
``check-workflow-make-targets``) absent from the docs site while their entries in
``.pre-commit-hooks.yaml`` and ``[project.scripts]`` were correct throughout.

This is the third parity pair in the repo, and the last one that was unguarded:

* ``test_pre_commit_manifest.py`` — ``.pre-commit-hooks.yaml`` <-> ``[project.scripts]``
* ``scripts/check_test_layout.py`` — ``src/`` modules <-> ``tests/`` modules
* here — ``src/`` modules <-> ``docs/api-reference/`` pages <-> the ``mkdocs.yml`` nav

Every check runs in both directions. A module with no page is an undocumented
feature; a page with no module is a stale page for something deleted; a page absent
from the nav is unreachable on the built site even though the file exists, which is
the failure mode a bare file-existence check would miss.

This file lives in ``tests/meta/`` — exempt from the test-layout orphan check via
``[tool.check_test_layout] exempt_dirs`` — because it tests repository metadata
rather than a ``src/`` module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src" / "rhiza_hooks"
_API_REFERENCE = _REPO_ROOT / "docs" / "api-reference"
_MKDOCS = _REPO_ROOT / "mkdocs.yml"

# The overview page indexes the others rather than documenting a module, so it is
# excluded from the page <-> module comparison (but still required in the nav).
_OVERVIEW = "index"

# ``__init__.py`` only exposes ``__version__`` via importlib.metadata; there is no
# API surface to render, and mkdocstrings would emit an empty page.
_UNDOCUMENTED_MODULES = frozenset({"__init__"})


def _source_modules() -> set[str]:
    """Return the documentable module names under ``src/rhiza_hooks/``."""
    return {path.stem for path in _SRC.glob("*.py")} - _UNDOCUMENTED_MODULES


def _reference_pages() -> set[str]:
    """Return the module names that have a page in ``docs/api-reference/``."""
    return {path.stem for path in _API_REFERENCE.glob("*.md")} - {_OVERVIEW}


def _nav_documents(nav: Any) -> set[str]:
    """Collect every ``docs_dir``-relative document path reachable from a nav tree.

    The nav is an arbitrarily nested mix of lists and single-key mappings, so this
    walks it structurally rather than assuming the current two-level shape — the
    test should keep working if the reference is regrouped.
    """
    if isinstance(nav, str):
        return {nav}
    if isinstance(nav, list):
        return set().union(*(_nav_documents(entry) for entry in nav)) if nav else set()
    if isinstance(nav, dict):
        return set().union(*(_nav_documents(value) for value in nav.values())) if nav else set()
    return set()


def _navigable_reference_pages() -> set[str]:
    """Return the ``api-reference/`` module names reachable from the ``mkdocs.yml`` nav."""
    # mkdocs.yml opens with `INHERIT: docs/mkdocs-base.yml`, which safe_load reads as
    # an ordinary key — the base config is never loaded here, and need not be: the
    # child's `nav:` fully replaces the parent's rather than merging with it.
    config = yaml.safe_load(_MKDOCS.read_text(encoding="utf-8"))
    prefix = "api-reference/"
    return {
        Path(document).stem
        for document in _nav_documents(config["nav"])
        if document.startswith(prefix) and document.endswith(".md")
    } - {_OVERVIEW}


def test_every_module_has_a_reference_page() -> None:
    """Every module under ``src/rhiza_hooks/`` is documented, and no page is stale.

    Both directions matter and fail differently. A module with no page ships an
    undocumented hook or helper; a page with no module renders mkdocstrings' "could
    not find" error on a live site long after the module was renamed or deleted.
    """
    modules = _source_modules()
    pages = _reference_pages()

    assert modules - pages == set(), "modules with no docs/api-reference page"
    assert pages - modules == set(), "docs/api-reference pages with no matching module"


def test_every_reference_page_is_reachable_from_the_nav() -> None:
    """Every reference page appears in the ``mkdocs.yml`` nav, and every nav entry exists.

    ``nav:`` is hand-maintained and fully replaces the base config's, so a page that
    is merely on disk is invisible on the built site. The reverse — a nav entry with
    no file — fails the build under ``--strict``.
    """
    pages = _reference_pages()
    navigable = _navigable_reference_pages()

    assert pages - navigable == set(), "docs/api-reference pages missing from the mkdocs.yml nav"
    assert navigable - pages == set(), "mkdocs.yml nav entries with no docs/api-reference page"


def test_the_overview_indexes_every_reference_page() -> None:
    """The overview's tables link to every module page.

    ``api-reference/index.md`` is the human entry point into the reference; a page
    reachable only from the sidebar is one a reader browsing the overview will never
    be told exists.
    """
    overview = (_API_REFERENCE / f"{_OVERVIEW}.md").read_text(encoding="utf-8")
    unlinked = sorted(page for page in _reference_pages() if f"({page}.md)" not in overview)

    assert unlinked == [], f"pages not linked from api-reference/index.md: {unlinked}"
