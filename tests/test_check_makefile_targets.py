"""Tests for check_makefile_targets hook."""

from __future__ import annotations

from pathlib import Path

import pytest

from rhiza_hooks.check_makefile_targets import (
    check_makefile,
    extract_targets,
    main,
)


class TestExtractTargets:
    """Tests for extract_targets function."""

    def test_extracts_simple_targets(self) -> None:
        """Extracts simple target names."""
        content = """
install:
	pip install .

test:
	pytest

fmt:
	ruff format .
"""
        targets = extract_targets(content)
        assert "install" in targets
        assert "test" in targets
        assert "fmt" in targets

    def test_extracts_targets_with_dependencies(self) -> None:
        """Extracts targets that have dependencies."""
        content = """
build: install
	python setup.py build

all: build test
	echo "Done"
"""
        targets = extract_targets(content)
        assert "build" in targets
        assert "all" in targets

    def test_extracts_phony_targets(self) -> None:
        """Extracts .PHONY style targets."""
        content = """
.PHONY: install test

install:
	pip install .
"""
        targets = extract_targets(content)
        assert "install" in targets
        # .PHONY is also matched but that's fine

    def test_empty_makefile(self) -> None:
        """Returns empty set for empty Makefile."""
        assert extract_targets("") == set()

    def test_ignores_comments(self) -> None:
        """Doesn't extract from commented lines."""
        content = """
# This is a comment
# install:
test:
	pytest
"""
        targets = extract_targets(content)
        assert "test" in targets
        # Comments starting with # aren't matched because they don't start at line beginning
        # after the # character


class TestCheckMakefile:
    """Tests for check_makefile function."""

    def test_all_recommended_targets_present(self, tmp_path: Path) -> None:
        """No warnings when all recommended targets exist."""
        makefile = tmp_path / "Makefile"
        makefile.write_text("""
install:
	pip install .

test:
	pytest

fmt:
	ruff format .

help:
	@echo "Available targets"
""")
        warnings = check_makefile(makefile)
        assert warnings == []

    def test_missing_some_targets(self, tmp_path: Path) -> None:
        """Warns about missing recommended targets with the exact message."""
        makefile = tmp_path / "Makefile"
        makefile.write_text("""
install:
	pip install .
""")
        warnings = check_makefile(makefile)
        # Exact match pins the message and the ", " join separator (sorted order).
        assert warnings == ["Missing recommended targets: fmt, help, test"]

    def test_file_not_found(self, tmp_path: Path) -> None:
        """Returns the exact error for a missing file."""
        makefile = tmp_path / "nonexistent"
        warnings = check_makefile(makefile)
        assert warnings == [f"File not found: {makefile}"]

    def test_non_makefile_skips_target_check(self, tmp_path: Path) -> None:
        """Non-Makefile files don't get target recommendations."""
        mk_file = tmp_path / "custom.mk"
        mk_file.write_text("# Just a comment")
        warnings = check_makefile(mk_file)
        # Should not warn about missing targets for non-Makefile files
        assert warnings == []


class TestMain:
    """Tests for main function."""

    def test_main_with_valid_makefile(self, tmp_path: Path) -> None:
        """Main returns 0 for valid Makefile."""
        makefile = tmp_path / "Makefile"
        makefile.write_text("""
install:
test:
fmt:
help:
""")
        result = main([str(makefile)])
        assert result == 0

    def test_main_with_missing_targets_no_strict(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Main returns 0 without --strict even with warnings."""
        makefile = tmp_path / "Makefile"
        makefile.write_text("install:\n")

        result = main([str(makefile)])

        assert result == 0
        captured = capsys.readouterr()
        # Exact stdout pins both the "{filename}:" header and the "  - {warning}" line.
        assert captured.out == f"{makefile}:\n  - Missing recommended targets: fmt, help, test\n"

    def test_main_with_missing_targets_strict(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Main returns 1 with --strict when targets missing."""
        makefile = tmp_path / "Makefile"
        makefile.write_text("install:\n")

        result = main(["--strict", str(makefile)])

        assert result == 1

    def test_main_no_files(self) -> None:
        """Main returns 0 when no files provided."""
        result = main([])
        assert result == 0

    def test_help_text(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--help renders the exact argparse description and option help strings."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        # Pin each literal exactly; the mutation engine wraps mutated literals in a
        # sentinel, so asserting it is absent guarantees the rendered text is verbatim.
        assert "XX" not in out
        assert "Check Makefile for recommended targets" in out
        assert "Filenames to check" in out
        assert "Exit with error if recommended targets are missing" in out


class TestModuleExecution:
    """Tests for module execution via if __name__ == '__main__'."""

    def test_module_executes_main(self) -> None:
        """Module execution calls main and exits with its return value."""
        import runpy
        from unittest.mock import patch

        with (
            patch("rhiza_hooks.check_makefile_targets.sys.argv", ["check_makefile_targets"]),
            patch("rhiza_hooks.check_makefile_targets.sys.exit") as mock_exit,
        ):
            runpy.run_module("rhiza_hooks.check_makefile_targets", run_name="__main__")
            mock_exit.assert_called_once_with(0)
