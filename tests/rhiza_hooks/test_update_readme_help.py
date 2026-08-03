"""Tests for the update_readme_help hook and its script entry point."""

from __future__ import annotations

import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from rhiza_hooks.update_readme_help import (
    _run,
    find_repo_root,
    get_make_help_output,
    main,
    update_readme_with_help,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def test_success() -> None:
    """Returns stdout and invokes subprocess.run with the exact command and options."""
    mock_result = MagicMock()
    mock_result.stdout = "help output"
    with patch("rhiza_hooks.update_readme_help.subprocess.run", return_value=mock_result) as mock_run:
        result = get_make_help_output()
        assert result == "help output"
        # Pin the command list and every keyword argument exactly.
        mock_run.assert_called_once_with(
            ["make", "help"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )


def test_called_process_error(capsys: pytest.CaptureFixture[str]) -> None:
    """Returns None and prints the exact error prefix on CalledProcessError."""
    with patch(
        "rhiza_hooks.update_readme_help.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "make"),
    ):
        result = get_make_help_output()
        assert result is None
        # startswith pins the leading literal; the {e} tail is interpreter-defined.
        assert capsys.readouterr().out.startswith("Error running 'make help': ")


def test_timeout_expired(capsys: pytest.CaptureFixture[str]) -> None:
    """Returns None and prints the exact timeout message."""
    with patch(
        "rhiza_hooks.update_readme_help.subprocess.run",
        side_effect=subprocess.TimeoutExpired("make", 30),
    ):
        result = get_make_help_output()
        assert result is None
        assert capsys.readouterr().out == "Error: 'make help' timed out\n"


def test_file_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    """Returns None and prints the exact message when make is not found."""
    with patch(
        "rhiza_hooks.update_readme_help.subprocess.run",
        side_effect=FileNotFoundError(),
    ):
        result = get_make_help_output()
        assert result is None
        assert capsys.readouterr().out == "Error: 'make' command not found\n"


def test_finds_git_dir(tmp_path: Path) -> None:
    """Returns directory containing .git."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    subdir = tmp_path / "src" / "package"
    subdir.mkdir(parents=True)

    with patch("rhiza_hooks.update_readme_help.Path.cwd", return_value=subdir):
        result = find_repo_root()
        assert result == tmp_path


def test_no_git_dir_returns_cwd(tmp_path: Path) -> None:
    """Returns cwd when no .git found."""
    subdir = tmp_path / "src" / "package"
    subdir.mkdir(parents=True)

    with patch("rhiza_hooks.update_readme_help.Path.cwd", return_value=subdir):
        result = find_repo_root()
        # When no .git found, returns cwd (which is subdir in this case)
        assert result == subdir


def test_updates_content_between_markers(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Content between markers is replaced with help output and the update is announced."""
    readme = tmp_path / "README.md"
    readme.write_text("# My Project\n\n<!-- MAKE_HELP_START -->\nold content\n<!-- MAKE_HELP_END -->\n\nFooter text")

    result = update_readme_with_help(readme, "new help output\n")

    assert result is True
    content = readme.read_text()
    assert "new help output" in content
    assert "old content" not in content
    assert "Footer text" in content
    # Exact stdout pins the "Updated ..." message.
    assert capsys.readouterr().out == f"Updated {readme} with make help output\n"


def test_non_ascii_readme_round_trips_as_utf8(tmp_path: Path) -> None:
    """A README holding non-ASCII text survives the rewrite byte-for-byte.

    Both the read and the write pin ``encoding="utf-8"``. Without that the hook
    follows the platform locale on each side, so on a cp1252 Windows box this README
    fails to decode at all — and, had it decoded, would be written back mojibake.
    """
    readme = tmp_path / "README.md"
    original = "# Projet 🪝\n\nRôle : générer — voilà.\n\n<!-- MAKE_HELP_START -->\nold\n<!-- MAKE_HELP_END -->\n"
    readme.write_bytes(original.encode())

    assert update_readme_with_help(readme, "cible : aide\n") is True

    content = readme.read_text(encoding="utf-8")
    assert "# Projet 🪝" in content
    assert "Rôle : générer — voilà." in content
    assert "cible : aide" in content


def test_lf_line_endings_survive_the_rewrite(tmp_path: Path) -> None:
    r"""A README with LF endings keeps them outside the help block.

    ``content`` comes back from a universal-newline read and ``help_output`` from a
    text-mode subprocess, so ``new_content`` is all ``\n``; the write pins
    ``newline=""`` so those stay ``\n`` instead of becoming ``os.linesep``. Without it
    a help-block refresh rewrites every line ending in the README on Windows.

    ``read_bytes`` is deliberate — ``read_text`` would translate CRLF back to LF and
    pass regardless. Only the Windows CI leg can fail this; the static half of the
    invariant is enforced in ``tests/meta/test_encoding_hygiene.py``.
    """
    readme = tmp_path / "README.md"
    readme.write_bytes(b"# Title\n\n<!-- MAKE_HELP_START -->\nold\n<!-- MAKE_HELP_END -->\n\nFooter\n")

    assert update_readme_with_help(readme, "help me\n") is True

    assert readme.read_bytes() == (
        b"# Title\n\n<!-- MAKE_HELP_START -->\n```\nhelp me\n```\n<!-- MAKE_HELP_END -->\n\nFooter\n"
    )


def test_no_markers_returns_false(tmp_path: Path) -> None:
    """File without markers is not modified."""
    readme = tmp_path / "README.md"
    original = "# My Project\n\nNo markers here"
    readme.write_text(original)

    result = update_readme_with_help(readme, "help output")

    assert result is False
    assert readme.read_text() == original


def test_missing_file_returns_false(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Missing file returns False and prints the exact warning."""
    readme = tmp_path / "nonexistent.md"

    result = update_readme_with_help(readme, "help output")

    assert result is False
    assert capsys.readouterr().out == f"Warning: {readme} not found, skipping update\n"


def test_no_change_returns_false(tmp_path: Path) -> None:
    """Returns False when content hasn't changed."""
    readme = tmp_path / "README.md"
    readme.write_text("<!-- MAKE_HELP_START -->\n```\nsame content\n```\n<!-- MAKE_HELP_END -->")

    result = update_readme_with_help(readme, "same content\n")

    assert result is False


def test_preserves_surrounding_content(tmp_path: Path) -> None:
    """Content before and after markers is preserved."""
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Header\n\n"
        "Some intro text.\n\n"
        "<!-- MAKE_HELP_START -->\n"
        "old\n"
        "<!-- MAKE_HELP_END -->\n\n"
        "## Next Section\n"
        "More content."
    )

    update_readme_with_help(readme, "updated help\n")

    content = readme.read_text()
    assert content.startswith("# Header")
    assert "Some intro text." in content
    assert "## Next Section" in content
    assert "More content." in content


def test_main_no_makefile_returns_zero() -> None:
    """Returns 0 when make help fails (no Makefile)."""
    with patch("rhiza_hooks.update_readme_help.get_make_help_output", return_value=None):
        result = main([])
        assert result == 0


def test_main_readme_updated_returns_one(tmp_path: Path) -> None:
    """Returns 1 when README was updated."""
    readme = tmp_path / "README.md"
    readme.write_text("<!-- MAKE_HELP_START -->\nold\n<!-- MAKE_HELP_END -->")
    (tmp_path / ".git").mkdir()

    with (
        patch("rhiza_hooks.update_readme_help.get_make_help_output", return_value="new help\n"),
        patch("rhiza_hooks.update_readme_help.find_repo_root", return_value=tmp_path),
    ):
        result = main([])
        assert result == 1


def test_main_readme_unchanged_returns_zero(tmp_path: Path) -> None:
    """Returns 0 when README was not changed."""
    readme = tmp_path / "README.md"
    readme.write_text("<!-- MAKE_HELP_START -->\n```\nsame content\n```\n<!-- MAKE_HELP_END -->")
    (tmp_path / ".git").mkdir()

    with (
        patch("rhiza_hooks.update_readme_help.get_make_help_output", return_value="same content\n"),
        patch("rhiza_hooks.update_readme_help.find_repo_root", return_value=tmp_path),
    ):
        result = main([])
        assert result == 0


def test_main_no_markers_returns_zero(tmp_path: Path) -> None:
    """Returns 0 when README has no markers."""
    readme = tmp_path / "README.md"
    readme.write_text("# Just a readme\n\nNo markers here.")
    (tmp_path / ".git").mkdir()

    with (
        patch("rhiza_hooks.update_readme_help.get_make_help_output", return_value="help output\n"),
        patch("rhiza_hooks.update_readme_help.find_repo_root", return_value=tmp_path),
    ):
        result = main([])
        assert result == 0


def test_run_delegates_to_main_and_exits() -> None:
    """_run() calls main() and threads its return value into sys.exit.

    _run() looks up the module-level ``main`` at call time, so patching
    ``rhiza_hooks.update_readme_help.main`` intercepts the delegation
    directly (no runpy fresh-namespace indirection, which cannot see it).
    """
    with (
        patch("rhiza_hooks.update_readme_help.main", return_value=7) as mock_main,
        patch("sys.exit") as mock_exit,
    ):
        _run()

    mock_main.assert_called_once_with()
    mock_exit.assert_called_once_with(7)


def test_updates_readme(mock_project: Callable[[dict[str, str]], Path]) -> None:
    """Test updating README with Makefile help."""
    makefile = """
.PHONY: test

test: ## Run tests
\t@echo "Running tests"
"""
    readme = """# Project

<!-- BEGIN_MAKEFILE_TARGETS -->
<!-- END_MAKEFILE_TARGETS -->
"""
    project = mock_project(
        {
            "Makefile": makefile,
            "README.md": readme,
        }
    )

    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "rhiza_hooks.update_readme_help"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    # Script should process the files
    assert result.returncode in (0, 1)


def test_module_is_importable() -> None:
    """Test that the module is importable."""
    module_name = "rhiza_hooks.update_readme_help"
    # Just verify the module is importable
    result = subprocess.run(  # nosec B603
        [sys.executable, "-c", f"import {module_name}"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Failed to import {module_name}: {result.stderr}"


def test_module_has_main_function() -> None:
    """Test that the module has a main function."""
    module_name = "rhiza_hooks.update_readme_help"
    # Verify the module has a main function
    result = subprocess.run(  # nosec B603
        [sys.executable, "-c", f"import {module_name}; assert hasattr({module_name}, 'main')"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Module {module_name} has no main function"


def test_module_handles_nonexistent_directory(tmp_path: Path) -> None:
    """Test that the module handles nonexistent directories gracefully."""
    module_name = "rhiza_hooks.update_readme_help"
    nonexistent = tmp_path / "nonexistent"

    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", module_name],
        cwd=nonexistent if nonexistent.exists() else tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    # Scripts should not crash
    assert result.returncode in (0, 1)


def test_module_python_importable() -> None:
    """Test that the module is importable."""
    module_path = "rhiza_hooks.update_readme_help"

    result = subprocess.run(  # nosec B603
        [sys.executable, "-c", f"import {module_path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Failed to import {module_path}: {result.stderr}"
