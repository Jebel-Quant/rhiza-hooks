"""Tests for the ``rhiza_hooks._managed`` module."""

from __future__ import annotations

from pathlib import Path

import pytest

from rhiza_hooks._managed import managed_paths, template_repository


@pytest.fixture
def rhiza_repo(tmp_path: Path):
    """Return a factory writing ``.rhiza/template.lock`` and ``.rhiza/template.yml``.

    Either document can be given as ``None`` to leave that file absent.
    """

    def write(lock: str | None, config: str | None = None) -> Path:
        """Write the two documents into a fresh repo root and return it."""
        rhiza = tmp_path / ".rhiza"
        rhiza.mkdir(exist_ok=True)
        if lock is not None:
            (rhiza / "template.lock").write_text(lock, encoding="utf-8")
        if config is not None:
            (rhiza / "template.yml").write_text(config, encoding="utf-8")
        return tmp_path

    return write


def test_lists_the_locked_files(rhiza_repo):
    """Every path in the lock's files: block is managed."""
    root = rhiza_repo("files:\n- Makefile\n- ruff.toml\n")
    assert managed_paths(root) == {"Makefile", "ruff.toml"}


def test_subtracts_excluded_paths(rhiza_repo):
    """A path the project excludes is not managed, even though the lock still lists it."""
    root = rhiza_repo(
        "files:\n- Makefile\n- .pre-commit-config.yaml\n",
        "exclude:\n- .pre-commit-config.yaml\n",
    )
    assert managed_paths(root) == {"Makefile"}


def test_ignores_the_locks_own_exclude_key(rhiza_repo):
    """Exclusions come from template.yml; the lock's own exclude: is not consulted.

    Pins the reason the subtraction reads template.yml: a real lock carries
    ``exclude: []`` even in a repo with active exclusions, so trusting it would
    flag files the project owns.
    """
    root = rhiza_repo(
        "exclude: []\nfiles:\n- Makefile\n- .pre-commit-config.yaml\n",
        "exclude:\n- .pre-commit-config.yaml\n",
    )
    assert managed_paths(root) == {"Makefile"}


def test_missing_lock_manages_nothing(tmp_path: Path):
    """A repo with no lock (managed but never synced) has no managed paths."""
    assert managed_paths(tmp_path) == set()


@pytest.mark.parametrize("lock", ["", "not a mapping", "files: Makefile", "files:\n  a: b", "[1, 2]"])
def test_unusable_lock_manages_nothing(rhiza_repo, lock):
    """An empty, non-mapping or wrong-shaped lock yields no managed paths rather than erroring."""
    assert managed_paths(rhiza_repo(lock)) == set()


def test_missing_config_applies_no_exclusions(rhiza_repo):
    """With no template.yml there is nothing to subtract, so every locked file is managed."""
    root = rhiza_repo("files:\n- Makefile\n")
    assert managed_paths(root) == {"Makefile"}


@pytest.mark.parametrize("config", ["", "exclude: Makefile", "exclude:\n  a: b"])
def test_unusable_config_applies_no_exclusions(rhiza_repo, config):
    """A malformed exclude: is ignored rather than erroring — check-rhiza-config reports it."""
    root = rhiza_repo("files:\n- Makefile\n", config)
    assert managed_paths(root) == {"Makefile"}


def test_non_string_entries_are_stringified(rhiza_repo):
    """Numeric or otherwise odd YAML scalars in files: still compare as strings."""
    root = rhiza_repo("files:\n- 42\n- Makefile\n")
    assert managed_paths(root) == {"42", "Makefile"}


def test_template_repository_is_read_from_the_lock(rhiza_repo):
    """The repo the last sync came from is reported so errors can name it."""
    root = rhiza_repo("repo: jebel-quant/rhiza\nfiles: []\n")
    assert template_repository(root) == "jebel-quant/rhiza"


def test_template_repository_missing_lock(tmp_path: Path):
    """With no lock there is no recorded template repository."""
    assert template_repository(tmp_path) is None


@pytest.mark.parametrize("lock", ["files: []", "repo: 42", "repo:\n  a: b"])
def test_template_repository_absent_or_wrong_type(rhiza_repo, lock):
    """A lock with no usable repo: value reports None rather than a stringified oddity."""
    assert template_repository(rhiza_repo(lock)) is None
