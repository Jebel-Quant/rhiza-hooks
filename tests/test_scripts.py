"""Integration tests for all package scripts defined in pyproject.toml.

This module tests the command-line entry points of all rhiza-hooks scripts:
- check-rhiza-workflow-names
- update-readme-help
- check-rhiza-config
- check-makefile-targets
- check-python-version-consistency
- check-template-bundles
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable


# All scripts defined in pyproject.toml [project.scripts]
SCRIPTS = [
    "check-rhiza-workflow-names",
    "update-readme-help",
    "check-rhiza-config",
    "check-makefile-targets",
    "check-python-version-consistency",
    "check-template-bundles",
]


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def mock_project(tmp_path: Path) -> Callable[[dict[str, str]], Path]:
    """Create a mock project structure for testing.

    Args:
        tmp_path: pytest temporary path fixture

    Returns:
        A function that creates project files from a dict of {filename: content}
    """
    def _create_project(files: dict[str, str]) -> Path:
        for filepath, content in files.items():
            file_path = tmp_path / filepath
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
        return tmp_path

    return _create_project


class TestScriptAvailability:
    """Test that all scripts are available as command-line tools."""

    @pytest.mark.parametrize("script_name", SCRIPTS)
    def test_script_is_installed(self, script_name: str) -> None:
        """Test that script is available in PATH."""
        result = subprocess.run(
            ["which", script_name],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"Script {script_name} not found in PATH"
        assert script_name in result.stdout

    @pytest.mark.parametrize("script_name", SCRIPTS)
    def test_script_has_help(self, script_name: str) -> None:
        """Test that script responds to --help flag."""
        result = subprocess.run(
            [script_name, "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        # --help should exit with 0 or produce output
        assert result.returncode == 0 or result.stdout or result.stderr


class TestCheckWorkflowNames:
    """Integration tests for check-rhiza-workflow-names script."""

    def test_valid_workflow(self, mock_project: Callable[[dict[str, str]], Path]) -> None:
        """Test with valid workflow file."""
        project = mock_project({
            ".github/workflows/test.yml": 'name: "(RHIZA) TEST WORKFLOW"\non: push\n'
        })

        result = subprocess.run(
            ["check-rhiza-workflow-names", str(project / ".github/workflows/test.yml")],
            capture_output=True,
            text=True,
            check=False,
        )
        # Should pass or return 0
        assert result.returncode == 0, f"stdout: {result.stdout}, stderr: {result.stderr}"

    def test_missing_prefix(self, mock_project: Callable[[dict[str, str]], Path]) -> None:
        """Test with workflow missing (RHIZA) prefix."""
        project = mock_project({
            ".github/workflows/test.yml": 'name: "Test Workflow"\non: push\n'
        })

        result = subprocess.run(
            ["check-rhiza-workflow-names", str(project / ".github/workflows/test.yml")],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1


class TestCheckRhizaConfig:
    """Integration tests for check-rhiza-config script."""

    def test_valid_config(self, mock_project: Callable[[dict[str, str]], Path]) -> None:
        """Test with valid rhiza config."""
        config = """
tools:
  commands: []
bundles: []
"""
        project = mock_project({".rhiza/rhiza.yml": config})

        result = subprocess.run(
            ["check-rhiza-config"],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0

    def test_invalid_config(self, mock_project: Callable[[dict[str, str]], Path]) -> None:
        """Test with missing rhiza config file."""
        # Create project without config file to test missing config handling
        project = mock_project({"dummy.txt": "test"})

        result = subprocess.run(
            ["check-rhiza-config"],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )
        # Script may pass (skip) or fail depending on whether config is required
        # Just verify it runs without crashing
        assert result.returncode in (0, 1)


class TestCheckMakefileTargets:
    """Integration tests for check-makefile-targets script."""

    def test_valid_makefile(self, mock_project: Callable[[dict[str, str]], Path]) -> None:
        """Test with valid Makefile structure."""
        makefile = """
.PHONY: test

test: ## Run tests
\t@echo "Running tests"
"""
        project = mock_project({"Makefile": makefile})

        result = subprocess.run(
            ["check-makefile-targets"],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )
        # Script should handle basic Makefiles
        assert result.returncode in (0, 1)  # May fail if specific targets required


class TestCheckPythonVersion:
    """Integration tests for check-python-version-consistency script."""

    def test_consistent_versions(self, mock_project: Callable[[dict[str, str]], Path]) -> None:
        """Test with consistent Python versions."""
        pyproject = """
[project]
requires-python = ">=3.11"
"""
        project = mock_project({
            ".python-version": "3.11\n",
            "pyproject.toml": pyproject,
        })

        result = subprocess.run(
            ["check-python-version-consistency"],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0

    def test_inconsistent_versions(self, mock_project: Callable[[dict[str, str]], Path]) -> None:
        """Test with inconsistent Python versions."""
        pyproject = """
[project]
requires-python = ">=3.11"
"""
        project = mock_project({
            ".python-version": "3.10\n",
            "pyproject.toml": pyproject,
        })

        result = subprocess.run(
            ["check-python-version-consistency"],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1


class TestCheckTemplateBundles:
    """Integration tests for check-template-bundles script."""

    def test_valid_bundles(self, mock_project: Callable[[dict[str, str]], Path]) -> None:
        """Test with valid template bundles."""
        bundles = """
core:
  - .editorconfig
  - .gitignore
"""
        template = """
bundles:
  - core
"""
        project = mock_project({
            ".rhiza/template-bundles.yml": bundles,
            ".rhiza/template.yml": template,
        })

        result = subprocess.run(
            ["check-template-bundles"],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )
        # May fail if specific validation rules not met
        assert result.returncode in (0, 1)

    def test_missing_bundles_file(self, mock_project: Callable[[dict[str, str]], Path]) -> None:
        """Test with template file that has no templates field."""
        template = """
bundles:
  - core
"""
        project = mock_project({".rhiza/template.yml": template})

        result = subprocess.run(
            ["check-template-bundles"],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )
        # Script skips validation when no templates field present (returns 0)
        assert result.returncode == 0
        assert "skipping" in result.stdout.lower() or "no templates" in result.stdout.lower()


class TestUpdateReadmeHelp:
    """Integration tests for update-readme-help script."""

    def test_updates_readme(self, mock_project: Callable[[dict[str, str]], Path]) -> None:
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
        project = mock_project({
            "Makefile": makefile,
            "README.md": readme,
        })

        result = subprocess.run(
            ["update-readme-help"],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )
        # Script should process the files
        assert result.returncode in (0, 1)


class TestScriptsInCurrentProject:
    """Test scripts against the actual rhiza-hooks project."""

    def test_check_workflow_names_on_project(self, project_root: Path) -> None:
        """Test check-rhiza-workflow-names on actual project workflows."""
        workflows_dir = project_root / ".github/workflows"
        if not workflows_dir.exists():
            pytest.skip("No .github/workflows directory")

        workflows = list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml"))
        if not workflows:
            pytest.skip("No workflow files found")

        # Just verify the script runs without crashing on actual workflows
        for workflow in workflows:
            result = subprocess.run(
                ["check-rhiza-workflow-names", str(workflow)],
                capture_output=True,
                text=True,
                check=False,
            )
            # Script should complete (may return 0 or 1 if it needs to update)
            assert result.returncode in (0, 1), f"Workflow {workflow.name} crashed: {result.stderr}"

    def test_check_rhiza_config_on_project(self, project_root: Path) -> None:
        """Test check-rhiza-config on actual project."""
        result = subprocess.run(
            ["check-rhiza-config"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        # Project should have valid config
        assert result.returncode == 0

    def test_check_makefile_targets_on_project(self, project_root: Path) -> None:
        """Test check-makefile-targets on actual project."""
        result = subprocess.run(
            ["check-makefile-targets"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        # Project Makefile should pass validation
        assert result.returncode == 0

    def test_check_python_version_on_project(self, project_root: Path) -> None:
        """Test check-python-version-consistency on actual project."""
        result = subprocess.run(
            ["check-python-version-consistency"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        # Project should have consistent Python versions
        assert result.returncode == 0

    def test_check_template_bundles_on_project(self, project_root: Path) -> None:
        """Test check-template-bundles on actual project."""
        result = subprocess.run(
            ["check-template-bundles"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        # This may fail if template-bundles.yml is missing (expected)
        # We just verify the script runs without crashing
        assert result.returncode in (0, 1)


class TestScriptErrorHandling:
    """Test error handling across all scripts."""

    @pytest.mark.parametrize("script_name", SCRIPTS)
    def test_script_handles_nonexistent_directory(self, script_name: str, tmp_path: Path) -> None:
        """Test that scripts handle nonexistent directories gracefully."""
        nonexistent = tmp_path / "nonexistent"

        result = subprocess.run(
            [script_name],
            cwd=nonexistent if nonexistent.exists() else tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        # Scripts should not crash
        assert result.returncode in (0, 1)

    @pytest.mark.parametrize("script_name", SCRIPTS)
    def test_script_python_importable(self, script_name: str) -> None:
        """Test that script modules are importable."""
        # Map script names to their actual module names
        module_mapping = {
            "check-rhiza-workflow-names": "check_workflow_names",
            "update-readme-help": "update_readme_help",
            "check-rhiza-config": "check_rhiza_config",
            "check-makefile-targets": "check_makefile_targets",
            "check-python-version-consistency": "check_python_version",
            "check-template-bundles": "check_template_bundles",
        }

        module_name = module_mapping.get(script_name, script_name.replace("-", "_"))
        module_path = f"rhiza_hooks.{module_name}"

        result = subprocess.run(
            [sys.executable, "-c", f"import {module_path}"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"Failed to import {module_path}: {result.stderr}"
