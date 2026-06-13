"""Tests for check_makefile_targets hook."""

from __future__ import annotations

from pathlib import Path

import pytest

from rhiza_hooks.check_makefile_targets import (
    check_makefile,
    extract_targets,
    main,
    resolve_recommended_targets,
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

    def test_ignores_recursive_assignment(self) -> None:
        """`VAR := value` is an assignment, not a target."""
        targets = extract_targets("PREFIX := /usr/local\ninstall:\n\tcp x $(PREFIX)\n")
        assert targets == {"install"}

    def test_ignores_simply_expanded_assignment(self) -> None:
        """`VAR ::= value` (simply-expanded) is an assignment, not a target."""
        targets = extract_targets("FLAGS ::= -O2\ntest:\n\tpytest\n")
        assert targets == {"test"}

    def test_extracts_double_colon_rule(self) -> None:
        """`target:: deps` (double-colon rule) is still a target."""
        targets = extract_targets("clean:: prep\n\trm -rf build\n")
        assert "clean" in targets

    def test_ignores_dot_special_and_pattern_targets(self) -> None:
        """`.PHONY` and pattern rules (`%.o`) are not extracted as recommended targets."""
        targets = extract_targets(".PHONY: build\n%.o: %.c\n\t$(CC) -c $<\nbuild:\n\techo hi\n")
        assert "build" in targets
        assert ".PHONY" not in targets
        assert "%.o" not in targets


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

    def test_custom_recommended_set(self, tmp_path: Path) -> None:
        """A custom `recommended` set replaces the default expectations."""
        makefile = tmp_path / "Makefile"
        makefile.write_text("build:\n\techo hi\n")
        # `build` satisfies a custom set; the default install/test/fmt/help are not required.
        assert check_makefile(makefile, {"build"}) == []
        # A custom target that is absent is reported.
        assert check_makefile(makefile, {"deploy"}) == ["Missing recommended targets: deploy"]


class TestResolveRecommendedTargets:
    """Tests for resolve_recommended_targets."""

    def test_defaults_when_no_options(self) -> None:
        """With no options the default recommended set is used."""
        assert resolve_recommended_targets(None, None) == {"install", "test", "fmt", "help"}

    def test_target_replaces_defaults(self) -> None:
        """`--target` values replace the defaults entirely."""
        assert resolve_recommended_targets(["build", "lint"], None) == {"build", "lint"}

    def test_extend_target_adds_to_defaults(self) -> None:
        """`--extend-target` adds to the active set, keeping the defaults."""
        assert resolve_recommended_targets(None, ["deploy"]) == {"install", "test", "fmt", "help", "deploy"}

    def test_target_and_extend_combine(self) -> None:
        """`--target` replaces, then `--extend-target` adds on top."""
        assert resolve_recommended_targets(["build"], ["deploy"]) == {"build", "deploy"}


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

    def test_main_target_override_satisfied(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """`--target` replaces the defaults; a Makefile meeting the custom set passes quietly."""
        makefile = tmp_path / "Makefile"
        makefile.write_text("build:\n\techo hi\n")

        result = main(["--target", "build", str(makefile)])

        assert result == 0
        assert capsys.readouterr().out == ""

    def test_main_extend_target_strict_fails(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """`--extend-target` adds a requirement; a missing extra target fails under --strict."""
        makefile = tmp_path / "Makefile"
        makefile.write_text("install:\ntest:\nfmt:\nhelp:\n")

        result = main(["--strict", "--extend-target", "deploy", str(makefile)])

        assert result == 1
        assert capsys.readouterr().out == f"{makefile}:\n  - Missing recommended targets: deploy\n"

    def test_help_text(self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
        """--help renders the exact argparse description and option help strings."""
        # Pin a wide terminal so argparse doesn't wrap the longer option help mid-string.
        monkeypatch.setenv("COLUMNS", "200")
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
        assert "Required target name; repeatable. When given, replaces the default set." in out
        assert "Extra required target name; repeatable. Added on top of the active set." in out


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
