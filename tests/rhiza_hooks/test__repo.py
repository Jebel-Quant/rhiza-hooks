"""Tests for the ``rhiza_hooks._repo`` module."""

from __future__ import annotations

from rhiza_hooks._repo import find_repo_root


def test_finds_git_directory(tmp_path, monkeypatch):
    """Test that find_repo_root finds the .git directory."""
    # Create a .git directory
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    # Create a subdirectory
    sub_dir = tmp_path / "subdir"
    sub_dir.mkdir()

    # Change to the subdirectory
    monkeypatch.chdir(sub_dir)

    # Should find the parent directory with .git
    root = find_repo_root()
    assert root == tmp_path


def test_returns_cwd_when_no_git_found(tmp_path, monkeypatch):
    """Test that find_repo_root returns cwd when no .git directory is found."""
    # Change to a directory without .git
    monkeypatch.chdir(tmp_path)

    # Should return current working directory
    root = find_repo_root()
    assert root == tmp_path
