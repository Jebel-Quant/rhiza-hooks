"""Tests for update_readme_help hook."""

from __future__ import annotations

from pathlib import Path

from rhiza_hooks.update_readme_help import update_readme_with_help


class TestUpdateReadmeWithHelp:
    """Tests for update_readme_with_help function."""

    def test_updates_content_between_markers(self, tmp_path: Path) -> None:
        """Content between markers is replaced with help output."""
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

    def test_no_markers_returns_false(self, tmp_path: Path) -> None:
        """File without markers is not modified."""
        readme = tmp_path / "README.md"
        original = "# My Project\n\nNo markers here"
        readme.write_text(original)

        result = update_readme_with_help(readme, "help output")

        assert result is False
        assert readme.read_text() == original

    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        """Missing file returns False without error."""
        readme = tmp_path / "nonexistent.md"

        result = update_readme_with_help(readme, "help output")

        assert result is False

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
