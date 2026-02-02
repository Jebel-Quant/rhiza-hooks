"""Tests for check_workflow_names hook.

Migrated from rhiza's tests/test_rhiza/test_check_workflow_names.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rhiza_hooks.check_workflow_names import check_file, main


class TestCheckFile:
    """Tests for check_file function."""

    def test_correct_prefix_returns_true(self, tmp_path: Path) -> None:
        """File with correct (RHIZA) prefix returns True."""
        workflow = tmp_path / "workflow.yml"
        workflow.write_text('name: "(RHIZA) MY WORKFLOW"\non: push\n')

        assert check_file(str(workflow)) is True

    def test_missing_prefix_updates_file(self, tmp_path: Path) -> None:
        """File without (RHIZA) prefix is updated and returns False."""
        workflow = tmp_path / "workflow.yml"
        workflow.write_text("name: My Workflow\non: push\n")

        result = check_file(str(workflow))

        assert result is False
        content = workflow.read_text()
        assert "(RHIZA) MY WORKFLOW" in content

    def test_missing_name_field_returns_false(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """File without name field returns False with error message."""
        workflow = tmp_path / "workflow.yml"
        workflow.write_text("on: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n")

        result = check_file(str(workflow))

        assert result is False
        captured = capsys.readouterr()
        assert "missing 'name' field" in captured.out

    def test_invalid_yaml_returns_false(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Invalid YAML returns False with error message."""
        workflow = tmp_path / "workflow.yml"
        workflow.write_text("name: test\n  invalid: yaml: syntax:\n")

        result = check_file(str(workflow))

        assert result is False
        captured = capsys.readouterr()
        assert "Error parsing YAML" in captured.out

    def test_empty_file_returns_true(self, tmp_path: Path) -> None:
        """Empty YAML file returns True (nothing to check)."""
        workflow = tmp_path / "workflow.yml"
        workflow.write_text("")

        assert check_file(str(workflow)) is True

    def test_preserves_other_content(self, tmp_path: Path) -> None:
        """Updating name prefix preserves other file content."""
        original = """name: CI Pipeline
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""
        workflow = tmp_path / "workflow.yml"
        workflow.write_text(original)

        check_file(str(workflow))

        content = workflow.read_text()
        # Check name was updated
        assert "(RHIZA) CI PIPELINE" in content
        # Check other content preserved
        assert "branches: [main]" in content
        assert "runs-on: ubuntu-latest" in content
        assert "actions/checkout@v4" in content

    def test_quoted_name_with_prefix(self, tmp_path: Path) -> None:
        """File with quoted name containing prefix returns True."""
        workflow = tmp_path / "workflow.yml"
        workflow.write_text('name: "(RHIZA) TEST"\non: push\n')

        assert check_file(str(workflow)) is True

    def test_unquoted_name_with_prefix(self, tmp_path: Path) -> None:
        """File with unquoted name containing prefix returns True."""
        workflow = tmp_path / "workflow.yml"
        workflow.write_text("name: (RHIZA) TEST\non: push\n")

        assert check_file(str(workflow)) is True

    def test_name_with_special_characters(self, tmp_path: Path) -> None:
        """Name with special characters is handled correctly."""
        workflow = tmp_path / "workflow.yml"
        workflow.write_text("name: Build & Deploy\non: push\n")

        check_file(str(workflow))

        content = workflow.read_text()
        assert "(RHIZA) BUILD & DEPLOY" in content


class TestMain:
    """Tests for main function."""

    def test_main_all_valid_returns_zero(self, tmp_path: Path) -> None:
        """Returns 0 when all files are valid."""
        w1 = tmp_path / "workflow1.yml"
        w1.write_text('name: "(RHIZA) TEST1"\non: push\n')
        w2 = tmp_path / "workflow2.yml"
        w2.write_text('name: "(RHIZA) TEST2"\non: push\n')

        result = main([str(w1), str(w2)])
        assert result == 0

    def test_main_invalid_exits_with_one(self, tmp_path: Path) -> None:
        """Exits with 1 when a file needs updating."""
        workflow = tmp_path / "workflow.yml"
        workflow.write_text("name: Test Workflow\non: push\n")

        with pytest.raises(SystemExit) as exc_info:
            main([str(workflow)])
        assert exc_info.value.code == 1

    def test_main_no_files_returns_zero(self) -> None:
        """Returns 0 when no files provided."""
        result = main([])
        assert result == 0

    def test_main_mixed_files(self, tmp_path: Path) -> None:
        """Exits with 1 when at least one file needs updating."""
        w1 = tmp_path / "workflow1.yml"
        w1.write_text('name: "(RHIZA) VALID"\non: push\n')
        w2 = tmp_path / "workflow2.yml"
        w2.write_text("name: Invalid Name\non: push\n")

        with pytest.raises(SystemExit) as exc_info:
            main([str(w1), str(w2)])
        assert exc_info.value.code == 1


class TestModuleExecution:
    """Tests for module execution via if __name__ == '__main__'."""

    def test_module_executes_main(self) -> None:
        """Module execution calls main."""
        import runpy
        from unittest.mock import patch

        with patch("rhiza_hooks.check_workflow_names.sys.argv", ["check_workflow_names"]):
            # main() returns 0 when no files provided, doesn't call sys.exit
            runpy.run_module("rhiza_hooks.check_workflow_names", run_name="__main__")
