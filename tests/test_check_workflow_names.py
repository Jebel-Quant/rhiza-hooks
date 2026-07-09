"""Tests for check_workflow_names hook.

Migrated from rhiza's tests/test_rhiza/test_check_workflow_names.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rhiza_hooks.check_workflow_names import _replace_name_lines, _run, check_file, main


class TestCheckFile:
    """Tests for check_file function."""

    def test_correct_prefix_returns_true(self, tmp_path: Path) -> None:
        """File with correct (RHIZA) prefix returns True."""
        workflow = tmp_path / "workflow.yml"
        workflow.write_text('name: "(RHIZA) MY WORKFLOW"\non: push\n')

        assert check_file(str(workflow)) is True

    def test_missing_prefix_updates_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """File without (RHIZA) prefix is rewritten exactly and the update is announced."""
        workflow = tmp_path / "workflow.yml"
        workflow.write_text("name: My Workflow\non: push\n")

        result = check_file(str(workflow))

        assert result is False
        # Exact file content pins the rewritten `name:` line (and that nothing else changed).
        assert workflow.read_text() == 'name: "(RHIZA) MY WORKFLOW"\non: push\n'
        # Exact stdout pins the "Updating ..." message.
        assert capsys.readouterr().out == (f"Updating {workflow}: name 'My Workflow' -> '(RHIZA) MY WORKFLOW'\n")

    def test_missing_name_field_returns_false(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """File without name field returns False with the exact error message."""
        workflow = tmp_path / "workflow.yml"
        workflow.write_text("on: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n")

        result = check_file(str(workflow))

        assert result is False
        assert capsys.readouterr().out == f"Error: {workflow} missing 'name' field.\n"

    def test_invalid_yaml_returns_false(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Invalid YAML returns False with the exact error prefix (no mutated wrapper)."""
        workflow = tmp_path / "workflow.yml"
        workflow.write_text('name: "unterminated\non: push\n')

        result = check_file(str(workflow))

        assert result is False
        # startswith pins the leading literal so a wrapped/mutated message is rejected.
        assert capsys.readouterr().out.startswith(f"Error parsing YAML {workflow}: ")

    def test_first_line_not_name_is_preserved(self, tmp_path: Path) -> None:
        """Only the top-level `name:` line is rewritten; a leading non-name line is kept.

        Pins the `not replaced and line.startswith("name:")` conjunction: with `or` the
        first line would be overwritten regardless of its content.
        """
        workflow = tmp_path / "workflow.yml"
        workflow.write_text("on: push\nname: Foo\n")

        check_file(str(workflow))

        assert workflow.read_text() == 'on: push\nname: "(RHIZA) FOO"\n'

    def test_only_first_name_line_replaced(self, tmp_path: Path) -> None:
        """Replacement stops after the first `name:` line.

        Pins `replaced = True`: if it were reset/falsy, a second `name:` line would be
        rewritten too. PyYAML keeps the last duplicate key, so the expected name is FOO.
        """
        workflow = tmp_path / "workflow.yml"
        workflow.write_text("name: Bar\nname: Foo\non: push\n")

        check_file(str(workflow))

        assert workflow.read_text() == 'name: "(RHIZA) FOO"\nname: Foo\non: push\n'

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

    def test_block_scalar_name_is_collapsed(self, tmp_path: Path) -> None:
        """A folded/block-scalar top-level name is collapsed to one quoted line.

        The indented and blank continuation lines of the scalar are dropped
        rather than left behind as orphan text that would corrupt the YAML.
        """
        workflow = tmp_path / "workflow.yml"
        workflow.write_text("name: >\n  My\n\n  Workflow\non: push\n")

        result = check_file(str(workflow))

        assert result is False
        assert workflow.read_text() == 'name: "(RHIZA) MY WORKFLOW"\non: push\n'

    def test_literal_block_scalar_name_is_collapsed(self, tmp_path: Path) -> None:
        """A literal (`|`) block-scalar name is collapsed to one quoted line."""
        workflow = tmp_path / "workflow.yml"
        workflow.write_text("name: |\n  My\n  Workflow\non: push\n")

        result = check_file(str(workflow))

        assert result is False
        assert workflow.read_text() == 'name: "(RHIZA) MY WORKFLOW"\non: push\n'

    def test_chomped_folded_block_scalar_name_is_collapsed(self, tmp_path: Path) -> None:
        """A folded block scalar with a chomping indicator (`>-`) is collapsed too.

        Pins the block-indicator detection to the leading character (`[:1]`): a
        naive two-char check would miss `>-`/`|-` and leave orphan scalar lines.
        """
        workflow = tmp_path / "workflow.yml"
        workflow.write_text("name: >-\n  My\n  Workflow\non: push\n")

        result = check_file(str(workflow))

        assert result is False
        assert workflow.read_text() == 'name: "(RHIZA) MY WORKFLOW"\non: push\n'

    def test_block_scalar_name_running_to_end_of_file_is_collapsed(self, tmp_path: Path) -> None:
        """A block-scalar name whose continuation lines run to EOF is collapsed.

        Pins the block-continuation count when no flush-left line ends the
        scalar: every trailing line is dropped and only the rewritten name remains.
        """
        workflow = tmp_path / "workflow.yml"
        workflow.write_text("name: |\n  My\n  Workflow\n")

        result = check_file(str(workflow))

        assert result is False
        assert workflow.read_text() == 'name: "(RHIZA) MY WORKFLOW"\n'

    def test_name_with_special_characters(self, tmp_path: Path) -> None:
        """Name with special characters is handled correctly."""
        workflow = tmp_path / "workflow.yml"
        workflow.write_text("name: Build & Deploy\non: push\n")

        check_file(str(workflow))

        content = workflow.read_text()
        assert "(RHIZA) BUILD & DEPLOY" in content


class TestTopLevelVsNestedName:
    """Regression matrix: only the top-level workflow name is touched (#161)."""

    def test_job_and_step_names_are_not_rewritten(self, tmp_path: Path) -> None:
        """Indented job/step `name:` keys are preserved; only the top-level name changes."""
        workflow = tmp_path / "workflow.yml"
        workflow.write_text(
            "name: ci\non: push\njobs:\n  build:\n    name: Build Job\n    steps:\n      - name: Checkout\n"
        )

        result = check_file(str(workflow))

        assert result is False
        assert workflow.read_text() == (
            'name: "(RHIZA) CI"\non: push\njobs:\n  build:\n    name: Build Job\n    steps:\n      - name: Checkout\n'
        )

    def test_missing_top_level_name_with_job_names(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """A workflow with no top-level name (only job names) errors and is left untouched."""
        workflow = tmp_path / "workflow.yml"
        original = "on: push\njobs:\n  build:\n    name: Build Job\n    runs-on: ubuntu-latest\n"
        workflow.write_text(original)

        result = check_file(str(workflow))

        assert result is False
        assert capsys.readouterr().out == f"Error: {workflow} missing 'name' field.\n"
        # The job-level name is not mistaken for the workflow name and the file is unchanged.
        assert workflow.read_text() == original

    def test_already_correct_with_nested_names_is_noop(self, tmp_path: Path) -> None:
        """A correct top-level name returns True and the file is left byte-for-byte unchanged."""
        workflow = tmp_path / "workflow.yml"
        original = 'name: "(RHIZA) CI"\non: push\njobs:\n  build:\n    name: Build Job\n'
        workflow.write_text(original)

        result = check_file(str(workflow))

        assert result is True
        assert workflow.read_text() == original


class TestReplaceNameLines:
    """Tests for the pure ``_replace_name_lines`` transformation."""

    def test_no_top_level_name_returns_lines_unchanged(self) -> None:
        """With no top-level ``name:`` line, the lines are returned unchanged.

        Defensive path: ``_rewrite_workflow_name`` is normally only reached once a
        top-level name is known to exist, but the transformation must be a no-op
        when the raw text has no ``name:`` at column 0 (e.g. a quoted key).
        """
        lines = ["on: push\n", "jobs:\n", "  build:\n", "    name: Nested\n"]

        assert _replace_name_lines(lines, "(RHIZA) X") == lines


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
    """Tests for the module entry point invoked by ``if __name__ == '__main__'``."""

    def test_run_delegates_to_main_and_exits(self) -> None:
        """_run() calls main() and threads its return value into sys.exit.

        _run() looks up the module-level ``main`` at call time, so patching
        ``rhiza_hooks.check_workflow_names.main`` intercepts the delegation
        directly (no runpy fresh-namespace indirection, which cannot see it).
        """
        from unittest.mock import patch

        with (
            patch("rhiza_hooks.check_workflow_names.main", return_value=7) as mock_main,
            patch("sys.exit") as mock_exit,
        ):
            _run()

        mock_main.assert_called_once_with()
        mock_exit.assert_called_once_with(7)
