"""Tests for the ``rhiza_hooks.check_managed_files`` module."""

from __future__ import annotations

import runpy
import shutil
import subprocess  # nosec B404
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

from rhiza_hooks import check_managed_files as cmf


@pytest.fixture
def managed_repo(tmp_path: Path):
    """Return a factory writing a lock (and optionally a template.yml) into a repo root."""

    def write(files: str, exclude: str | None = None, repo: str = "jebel-quant/rhiza") -> Path:
        """Write the .rhiza documents from newline-free YAML fragments; return the root."""
        rhiza = tmp_path / ".rhiza"
        rhiza.mkdir(exist_ok=True)
        (rhiza / "template.lock").write_text(f"repo: {repo}\nfiles:\n{files}", encoding="utf-8")
        if exclude is not None:
            (rhiza / "template.yml").write_text(f"exclude:\n{exclude}", encoding="utf-8")
        return tmp_path

    return write


def test_managed_file_is_reported(managed_repo):
    """Committing a managed file fails, naming the file and the template repository."""
    root = managed_repo("- Makefile\n- ruff.toml\n")
    errors = cmf.check_managed_files(["Makefile"], root, set())
    assert len(errors) == 1
    assert errors[0].startswith("Makefile is owned by jebel-quant/rhiza")
    assert ".rhiza/template.yml" in errors[0]


def test_unmanaged_file_passes(managed_repo):
    """A file the project owns is not reported."""
    root = managed_repo("- Makefile\n")
    assert cmf.check_managed_files(["src/rhiza_hooks/_repo.py"], root, set()) == []


def test_excluded_file_passes(managed_repo):
    """A path excluded in template.yml is not synced, so editing it is legitimate."""
    root = managed_repo("- Makefile\n- .pre-commit-config.yaml\n", exclude="- .pre-commit-config.yaml\n")
    assert cmf.check_managed_files([".pre-commit-config.yaml"], root, set()) == []


def test_allow_waives_one_path(managed_repo):
    """--allow waives a single managed path without waiving the rest."""
    root = managed_repo("- Makefile\n- ruff.toml\n")
    errors = cmf.check_managed_files(["Makefile", "ruff.toml"], root, {"Makefile"})
    assert len(errors) == 1
    assert errors[0].startswith("ruff.toml is owned by")


def test_multiple_offenders_are_sorted_and_deduplicated(managed_repo):
    """Every offending path is reported once, in a stable order."""
    root = managed_repo("- Makefile\n- ruff.toml\n")
    errors = cmf.check_managed_files(["ruff.toml", "Makefile", "Makefile"], root, set())
    assert [e.split(" ", 1)[0] for e in errors] == ["Makefile", "ruff.toml"]


def test_unsynced_repo_reports_nothing(tmp_path: Path):
    """With no lock (managed but never synced) nothing is owned upstream."""
    assert cmf.check_managed_files(["Makefile"], tmp_path, set()) == []


def test_lock_without_repo_falls_back_to_generic_wording(managed_repo):
    """A lock that records no repo: still produces an actionable message."""
    rhiza_root = managed_repo("- Makefile\n")
    (rhiza_root / ".rhiza" / "template.lock").write_text("files:\n- Makefile\n", encoding="utf-8")
    errors = cmf.check_managed_files(["Makefile"], rhiza_root, set())
    assert errors[0].startswith("Makefile is owned by the template repository")


def test_absolute_path_is_normalised(managed_repo):
    """An absolute path inside the repo is compared as a repo-relative one."""
    root = managed_repo("- Makefile\n")
    assert len(cmf.check_managed_files([str(root / "Makefile")], root, set())) == 1


def test_dot_prefixed_path_is_normalised(managed_repo):
    """A './'-prefixed path is compared as a plain repo-relative one."""
    root = managed_repo("- Makefile\n")
    assert len(cmf.check_managed_files(["./Makefile"], root, set())) == 1


def test_path_outside_the_repo_is_ignored(managed_repo, tmp_path: Path):
    """A path outside the repository cannot be managed and is left alone."""
    root = managed_repo("- Makefile\n")
    outside = tmp_path.parent / "elsewhere" / "Makefile"
    assert cmf.check_managed_files([str(outside)], root, set()) == []


def test_repo_relative_keeps_foreign_absolute_paths(tmp_path: Path):
    """repo_relative returns an unrelated absolute path unchanged, as POSIX."""
    assert cmf.repo_relative("/somewhere/else/Makefile", tmp_path) == "/somewhere/else/Makefile"


def test_main_passes_on_clean_commit(managed_repo, monkeypatch, capsys):
    """A commit touching no managed file exits 0 and says nothing."""
    root = managed_repo("- Makefile\n")
    monkeypatch.setattr(cmf, "find_repo_root", lambda: root)
    assert cmf.main(["src/foo.py"]) == 0
    assert capsys.readouterr().out == ""


def test_main_fails_and_explains_the_bypass(managed_repo, monkeypatch, capsys):
    """A commit touching a managed file exits 1, prints ERROR: and names the SKIP bypass."""
    root = managed_repo("- Makefile\n")
    monkeypatch.setattr(cmf, "find_repo_root", lambda: root)
    assert cmf.main(["Makefile"]) == 1
    out = capsys.readouterr().out
    assert "ERROR: Makefile is owned by jebel-quant/rhiza" in out
    assert "SKIP=check-managed-files" in out


def test_main_honours_allow(managed_repo, monkeypatch):
    """--allow is threaded through to the check."""
    root = managed_repo("- Makefile\n")
    monkeypatch.setattr(cmf, "find_repo_root", lambda: root)
    assert cmf.main(["Makefile", "--allow", "Makefile"]) == 0


def test_module_executes_main(managed_repo, monkeypatch):
    """Module execution calls main and exits with its return value."""
    root = managed_repo("- Makefile\n")
    monkeypatch.setattr(cmf, "find_repo_root", lambda: root)
    monkeypatch.setattr(cmf.sys, "argv", ["check_managed_files"])

    with patch("rhiza_hooks.check_managed_files.sys.exit") as mock_exit:
        # The module is already imported (top-level test import), so runpy warns it
        # was "found in sys.modules ... prior to execution"; filter just that warning
        # rather than mutating sys.modules, which would break module identity for the
        # tests above that monkeypatch this module.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=r".*found in sys\.modules.*", category=RuntimeWarning)
            runpy.run_module("rhiza_hooks.check_managed_files", run_name="__main__")
        mock_exit.assert_called_once_with(0)


# ---------------------------------------------------------------------------
# Narrowing to files that actually differ from HEAD
# ---------------------------------------------------------------------------
def _git(args: list[str], cwd: Path) -> None:
    """Run a git command in ``cwd``, raising if it fails."""
    subprocess.run(  # nosec B603 B607
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        timeout=30,
    )


@pytest.fixture
def git_repo(managed_repo):
    """Return a committed repo whose Makefile is template-owned."""
    if shutil.which("git") is None:  # pragma: no cover - git is present in CI and dev
        pytest.skip("git is required for the modified-paths tests")
    root = managed_repo("- Makefile\n")
    (root / "Makefile").write_text("test:\n\techo hi\n", encoding="utf-8")
    _git(["init"], root)
    _git(["config", "user.email", "test@example.com"], root)
    _git(["config", "user.name", "Test"], root)
    _git(["add", "-A"], root)
    _git(["-c", "commit.gpgsign=false", "commit", "-m", "initial"], root)
    return root


def test_unmodified_managed_file_passes(git_repo):
    """A managed file that is merely present is not an offence — only a changed one is.

    This is what keeps `pre-commit run --all-files` (used by `make fmt` and CI) from
    reporting every managed file in the repo on a clean tree.
    """
    assert cmf.check_managed_files(["Makefile"], git_repo, set()) == []


def test_modified_managed_file_is_reported(git_repo):
    """Once the managed file actually differs from HEAD it is reported."""
    (git_repo / "Makefile").write_text("test:\n\techo changed\n", encoding="utf-8")
    errors = cmf.check_managed_files(["Makefile"], git_repo, set())
    assert len(errors) == 1
    assert errors[0].startswith("Makefile is owned by jebel-quant/rhiza")


def test_staged_managed_file_is_reported(git_repo):
    """A staged change counts: that is exactly what a commit is about to record."""
    (git_repo / "Makefile").write_text("test:\n\techo staged\n", encoding="utf-8")
    _git(["add", "Makefile"], git_repo)
    assert len(cmf.check_managed_files(["Makefile"], git_repo, set())) == 1


def test_modified_paths_without_git_metadata(tmp_path: Path):
    """Outside a work tree git cannot answer, so the paths given are trusted as-is."""
    assert cmf.modified_paths(tmp_path) is None


def test_modified_paths_when_git_is_missing(managed_repo, monkeypatch):
    """A missing git binary degrades to trusting the given paths rather than crashing."""
    root = managed_repo("- Makefile\n")

    def boom(*args, **kwargs):
        """Stand in for a git binary that is not installed."""
        raise FileNotFoundError("git")

    monkeypatch.setattr(cmf.subprocess, "run", boom)
    assert cmf.modified_paths(root) is None
    # ...and the check still reports, because the given paths are trusted.
    assert len(cmf.check_managed_files(["Makefile"], root, set())) == 1
