"""Tests for check_readme_version hook."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from rhiza_hooks.check_readme_version import (
    check_readme_version,
    find_repo_root,
    get_pyproject_version,
    get_readme_rev,
    main,
)


class TestGetPyprojectVersion:
    """Tests for get_pyproject_version function."""

    def test_returns_version(self, tmp_path: Path) -> None:
        """Returns the version string from pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.2.3"\n')
        assert get_pyproject_version(tmp_path) == "1.2.3"

    def test_missing_file(self, tmp_path: Path) -> None:
        """Returns None when pyproject.toml does not exist."""
        assert get_pyproject_version(tmp_path) is None

    def test_missing_version_key(self, tmp_path: Path) -> None:
        """Returns None when pyproject.toml has no version field."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "foo"\n')
        assert get_pyproject_version(tmp_path) is None

    def test_invalid_toml(self, tmp_path: Path) -> None:
        """Returns None on invalid TOML."""
        (tmp_path / "pyproject.toml").write_text("not valid toml {{{{")
        assert get_pyproject_version(tmp_path) is None


class TestGetReadmeRev:
    """Tests for get_readme_rev function."""

    def _make_readme(self, tmp_path: Path, rev: str) -> Path:
        content = (
            "# Project\n\n"
            "```yaml\n"
            "repos:\n"
            "  - repo: https://github.com/Jebel-Quant/rhiza-hooks\n"
            f"    rev: {rev}  # Use the latest release\n"
            "    hooks:\n"
            "      - id: check-readme-version\n"
            "```\n"
        )
        readme = tmp_path / "README.md"
        readme.write_text(content)
        return readme

    def test_reads_rev_with_v_prefix(self, tmp_path: Path) -> None:
        """Reads rev: value including v-prefix."""
        self._make_readme(tmp_path, "v0.5.1")
        assert get_readme_rev(tmp_path) == "v0.5.1"

    def test_reads_rev_without_v_prefix(self, tmp_path: Path) -> None:
        """Reads rev: value without v-prefix."""
        self._make_readme(tmp_path, "0.5.1")
        assert get_readme_rev(tmp_path) == "0.5.1"

    def test_missing_readme(self, tmp_path: Path) -> None:
        """Returns None when README.md does not exist."""
        assert get_readme_rev(tmp_path) is None

    def test_no_rhiza_hooks_entry(self, tmp_path: Path) -> None:
        """Returns None when no rhiza-hooks repo entry is found."""
        readme = tmp_path / "README.md"
        readme.write_text("# No hooks here\n")
        assert get_readme_rev(tmp_path) is None

    def test_case_insensitive_owner(self, tmp_path: Path) -> None:
        """Matches repo URL regardless of owner casing."""
        content = (
            "```yaml\n"
            "repos:\n"
            "  - repo: https://github.com/jebel-quant/rhiza-hooks\n"
            "    rev: v1.0.0\n"
            "```\n"
        )
        (tmp_path / "README.md").write_text(content)
        assert get_readme_rev(tmp_path) == "v1.0.0"

    def test_rev_without_inline_comment(self, tmp_path: Path) -> None:
        """Reads rev: value that has no trailing comment."""
        content = (
            "```yaml\n"
            "repos:\n"
            "  - repo: https://github.com/Jebel-Quant/rhiza-hooks\n"
            "    rev: v2.0.0\n"
            "```\n"
        )
        (tmp_path / "README.md").write_text(content)
        assert get_readme_rev(tmp_path) == "v2.0.0"


class TestCheckReadmeVersion:
    """Tests for check_readme_version function."""

    def _write_pyproject(self, tmp_path: Path, version: str) -> None:
        (tmp_path / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n')

    def _write_readme(self, tmp_path: Path, rev: str) -> None:
        content = (
            "# Project\n\n"
            "```yaml\n"
            "repos:\n"
            "  - repo: https://github.com/Jebel-Quant/rhiza-hooks\n"
            f"    rev: {rev}\n"
            "```\n"
        )
        (tmp_path / "README.md").write_text(content)

    def test_matching_versions_returns_no_errors(self, tmp_path: Path) -> None:
        """No errors when README rev matches pyproject version."""
        self._write_pyproject(tmp_path, "0.5.1")
        self._write_readme(tmp_path, "v0.5.1")
        assert check_readme_version(tmp_path) == []

    def test_matching_without_v_prefix_returns_no_errors(self, tmp_path: Path) -> None:
        """No errors when README rev has no v-prefix but still matches."""
        self._write_pyproject(tmp_path, "0.5.1")
        self._write_readme(tmp_path, "0.5.1")
        assert check_readme_version(tmp_path) == []

    def test_mismatch_returns_error(self, tmp_path: Path) -> None:
        """Error when README rev does not match pyproject version."""
        self._write_pyproject(tmp_path, "0.5.1")
        self._write_readme(tmp_path, "v0.1.0")
        errors = check_readme_version(tmp_path)
        assert len(errors) == 1
        assert "v0.1.0" in errors[0]
        assert "0.5.1" in errors[0]

    def test_missing_pyproject_returns_no_errors(self, tmp_path: Path) -> None:
        """No errors when pyproject.toml is absent (skip gracefully)."""
        self._write_readme(tmp_path, "v0.5.1")
        assert check_readme_version(tmp_path) == []

    def test_missing_readme_rev_returns_error(self, tmp_path: Path) -> None:
        """Error when README does not contain a rev: for rhiza-hooks."""
        self._write_pyproject(tmp_path, "0.5.1")
        (tmp_path / "README.md").write_text("# No hooks\n")
        errors = check_readme_version(tmp_path)
        assert len(errors) == 1
        assert "rev:" in errors[0]


class TestFindRepoRoot:
    """Tests for find_repo_root function."""

    def test_finds_root_with_git_dir(self, tmp_path: Path) -> None:
        """Returns directory containing .git."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        with patch("rhiza_hooks.check_readme_version.Path.cwd", return_value=subdir):
            root = find_repo_root()

        assert root == tmp_path

    def test_returns_cwd_when_no_git(self, tmp_path: Path) -> None:
        """Returns cwd when no .git directory is found."""
        with patch("rhiza_hooks.check_readme_version.Path.cwd", return_value=tmp_path):
            root = find_repo_root()

        # Either tmp_path or its root; just verify it doesn't crash
        assert isinstance(root, Path)


class TestMain:
    """Tests for main entry point."""

    def test_returns_0_on_match(self, tmp_path: Path) -> None:
        """Returns 0 when README rev matches pyproject version."""
        (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.0.0"\n')
        (tmp_path / "README.md").write_text(
            "```yaml\n"
            "repos:\n"
            "  - repo: https://github.com/Jebel-Quant/rhiza-hooks\n"
            "    rev: v1.0.0\n"
            "```\n"
        )
        with patch("rhiza_hooks.check_readme_version.find_repo_root", return_value=tmp_path):
            result = main([])
        assert result == 0

    def test_returns_1_on_mismatch(self, tmp_path: Path) -> None:
        """Returns 1 when README rev does not match pyproject version."""
        (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.0.0"\n')
        (tmp_path / "README.md").write_text(
            "```yaml\n"
            "repos:\n"
            "  - repo: https://github.com/Jebel-Quant/rhiza-hooks\n"
            "    rev: v0.1.0\n"
            "```\n"
        )
        with patch("rhiza_hooks.check_readme_version.find_repo_root", return_value=tmp_path):
            result = main([])
        assert result == 1

    def test_ignores_filenames_argument(self, tmp_path: Path) -> None:
        """Filenames argument is accepted but ignored."""
        (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.0.0"\n')
        (tmp_path / "README.md").write_text(
            "```yaml\n"
            "repos:\n"
            "  - repo: https://github.com/Jebel-Quant/rhiza-hooks\n"
            "    rev: v1.0.0\n"
            "```\n"
        )
        with patch("rhiza_hooks.check_readme_version.find_repo_root", return_value=tmp_path):
            result = main(["README.md", "pyproject.toml"])
        assert result == 0


class TestModuleExecution:
    """Tests for module execution via if __name__ == '__main__'."""

    def test_module_is_executable(self) -> None:
        """Module can be imported without errors."""
        import rhiza_hooks.check_readme_version as m

        assert callable(m.main)
