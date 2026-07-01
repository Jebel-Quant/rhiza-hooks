"""Tests for update_readme_help hook."""

from __future__ import annotations

import runpy
import subprocess  # nosec B404
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rhiza_hooks.update_readme_help import (
    find_repo_root,
    get_make_help_output,
    main,
    update_readme_with_help,
)


class TestGetMakeHelpOutput:
    """Tests for get_make_help_output function."""

    def test_success(self) -> None:
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

    def test_called_process_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Returns None and prints the exact error prefix on CalledProcessError."""
        with patch(
            "rhiza_hooks.update_readme_help.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "make"),
        ):
            result = get_make_help_output()
            assert result is None
            # startswith pins the leading literal; the {e} tail is interpreter-defined.
            assert capsys.readouterr().out.startswith("Error running 'make help': ")

    def test_timeout_expired(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Returns None and prints the exact timeout message."""
        with patch(
            "rhiza_hooks.update_readme_help.subprocess.run",
            side_effect=subprocess.TimeoutExpired("make", 30),
        ):
            result = get_make_help_output()
            assert result is None
            assert capsys.readouterr().out == "Error: 'make help' timed out\n"

    def test_file_not_found(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Returns None and prints the exact message when make is not found."""
        with patch(
            "rhiza_hooks.update_readme_help.subprocess.run",
            side_effect=FileNotFoundError(),
        ):
            result = get_make_help_output()
            assert result is None
            assert capsys.readouterr().out == "Error: 'make' command not found\n"


class TestFindRepoRoot:
    """Tests for find_repo_root function."""

    def test_finds_git_dir(self, tmp_path: Path) -> None:
        """Returns directory containing .git."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        subdir = tmp_path / "src" / "package"
        subdir.mkdir(parents=True)

        with patch("rhiza_hooks.update_readme_help.Path.cwd", return_value=subdir):
            result = find_repo_root()
            assert result == tmp_path

    def test_no_git_dir_returns_cwd(self, tmp_path: Path) -> None:
        """Returns cwd when no .git found."""
        subdir = tmp_path / "src" / "package"
        subdir.mkdir(parents=True)

        with patch("rhiza_hooks.update_readme_help.Path.cwd", return_value=subdir):
            result = find_repo_root()
            # When no .git found, returns cwd (which is subdir in this case)
            assert result == subdir


class TestUpdateReadmeWithHelp:
    """Tests for update_readme_with_help function."""

    def test_updates_content_between_markers(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Content between markers is replaced with help output and the update is announced."""
        readme = tmp_path / "README.md"
        readme.write_text(
            "# My Project\n\n<!-- MAKE_HELP_START -->\nold content\n<!-- MAKE_HELP_END -->\n\nFooter text"
        )

        result = update_readme_with_help(readme, "new help output\n")

        assert result is True
        content = readme.read_text()
        assert "new help output" in content
        assert "old content" not in content
        assert "Footer text" in content
        # Exact stdout pins the "Updated ..." message.
        assert capsys.readouterr().out == f"Updated {readme} with make help output\n"

    def test_no_markers_returns_false(self, tmp_path: Path) -> None:
        """File without markers is not modified."""
        readme = tmp_path / "README.md"
        original = "# My Project\n\nNo markers here"
        readme.write_text(original)

        result = update_readme_with_help(readme, "help output")

        assert result is False
        assert readme.read_text() == original

    def test_missing_file_returns_false(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Missing file returns False and prints the exact warning."""
        readme = tmp_path / "nonexistent.md"

        result = update_readme_with_help(readme, "help output")

        assert result is False
        assert capsys.readouterr().out == f"Warning: {readme} not found, skipping update\n"

    def test_no_change_returns_false(self, tmp_path: Path) -> None:
        """Returns False when content hasn't changed."""
        readme = tmp_path / "README.md"
        readme.write_text("<!-- MAKE_HELP_START -->\n```\nsame content\n```\n<!-- MAKE_HELP_END -->")

        result = update_readme_with_help(readme, "same content\n")

        assert result is False

    def test_preserves_surrounding_content(self, tmp_path: Path) -> None:
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


class TestMain:
    """Tests for main function."""

    def test_main_no_makefile_returns_zero(self) -> None:
        """Returns 0 when make help fails (no Makefile)."""
        with patch("rhiza_hooks.update_readme_help.get_make_help_output", return_value=None):
            result = main([])
            assert result == 0

    def test_main_readme_updated_returns_one(self, tmp_path: Path) -> None:
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

    def test_main_readme_unchanged_returns_zero(self, tmp_path: Path) -> None:
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

    def test_main_no_markers_returns_zero(self, tmp_path: Path) -> None:
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


class TestModuleExecution:
    """Tests for module execution via if __name__ == '__main__'."""

    def test_module_executes_main(self) -> None:
        """Module execution calls main and exits with its return value."""
        expected_exit_code = 7
        with (
            patch("rhiza_hooks.update_readme_help.main", return_value=expected_exit_code) as mock_main,
            patch("sys.exit") as mock_exit,
        ):
            # The module is already imported (top-level test import), so runpy warns
            # it was "found in sys.modules ... prior to execution"; filter just that
            # warning rather than mutating sys.modules, which would break module
            # identity for other tests that monkeypatch this module.
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=r".*found in sys\.modules.*", category=RuntimeWarning)
                runpy.run_module("rhiza_hooks.update_readme_help", run_name="__main__")
            mock_main.assert_called_once_with([])
            mock_exit.assert_called_once_with(expected_exit_code)
