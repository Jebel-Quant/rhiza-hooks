"""Shared fixtures for the ``rhiza_hooks`` test package.

These support the subprocess-level integration tests that live alongside the
unit tests in each mirrored ``test_<module>.py`` file: ``project_root`` points at
the real repository (so a hook can be run against this project's own files) and
``mock_project`` builds a throwaway project tree from a ``{path: content}`` map.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def temp_bundles_file(tmp_path: Path):
    """Create a temporary bundles file."""

    def _create(content: str) -> Path:
        """Write the dedented content to a template-bundles.yml and return its path."""
        bundles_file = tmp_path / "template-bundles.yml"
        bundles_file.write_text(dedent(content))
        return bundles_file

    return _create


@pytest.fixture
def project_root() -> Path:
    """Return the rhiza-hooks repository root."""
    return Path(__file__).parent.parent.parent


@pytest.fixture
def mock_project(tmp_path: Path) -> Callable[[dict[str, str]], Path]:
    """Return a factory that materialises a mock project under ``tmp_path``.

    The factory takes a ``{relative_path: file_content}`` mapping, creates every
    file (and any parent directories), and returns the project root.
    """

    def _create_project(files: dict[str, str]) -> Path:
        """Create project files from a {filename: content} mapping and return the root."""
        for filepath, content in files.items():
            file_path = tmp_path / filepath
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
        return tmp_path

    return _create_project
