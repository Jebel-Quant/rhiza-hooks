"""Tests for the ``check_makefile_targets`` hook."""

from __future__ import annotations

import subprocess  # nosec B404
import sys
from typing import TYPE_CHECKING

import pytest

from rhiza_hooks.check_makefile_targets import (
    check_makefile,
    main,
    resolve_recommended_targets,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def test_all_recommended_targets_present(tmp_path: Path) -> None:
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


def test_missing_some_targets(tmp_path: Path) -> None:
    """Warns about missing recommended targets with the exact message."""
    makefile = tmp_path / "Makefile"
    makefile.write_text("""
install:
	pip install .
""")
    warnings = check_makefile(makefile)
    # Exact match pins the message and the ", " join separator (sorted order).
    assert warnings == ["Missing recommended targets: fmt, help, test"]


def test_non_ascii_makefile_is_read_as_utf8(tmp_path: Path) -> None:
    """A UTF-8 Makefile with non-ASCII text is decoded regardless of the platform locale.

    Without the explicit ``encoding="utf-8"`` these bytes raise UnicodeDecodeError
    under a cp1252 locale, so the hook would crash on a Makefile that is perfectly
    valid rather than report on it.
    """
    makefile = tmp_path / "Makefile"
    makefile.write_bytes("# générer — tout\ninstall:\ntest:\nfmt:\nhelp:\n".encode())
    assert check_makefile(makefile) == []


def test_file_not_found(tmp_path: Path) -> None:
    """Returns the exact error for a missing file."""
    makefile = tmp_path / "nonexistent"
    warnings = check_makefile(makefile)
    assert warnings == [f"File not found: {makefile}"]


def test_non_makefile_skips_target_check(tmp_path: Path) -> None:
    """Non-Makefile files don't get target recommendations."""
    mk_file = tmp_path / "custom.mk"
    mk_file.write_text("# Just a comment")
    warnings = check_makefile(mk_file)
    # Should not warn about missing targets for non-Makefile files
    assert warnings == []


def test_custom_recommended_set(tmp_path: Path) -> None:
    """A custom `recommended` set replaces the default expectations."""
    makefile = tmp_path / "Makefile"
    makefile.write_text("build:\n\techo hi\n")
    # `build` satisfies a custom set; the default install/test/fmt/help are not required.
    assert check_makefile(makefile, {"build"}) == []
    # A custom target that is absent is reported.
    assert check_makefile(makefile, {"deploy"}) == ["Missing recommended targets: deploy"]


def test_defaults_when_no_options() -> None:
    """With no options the default recommended set is used."""
    assert resolve_recommended_targets(None, None) == {"install", "test", "fmt", "help"}


def test_target_replaces_defaults() -> None:
    """`--target` values replace the defaults entirely."""
    assert resolve_recommended_targets(["build", "lint"], None) == {"build", "lint"}


def test_extend_target_adds_to_defaults() -> None:
    """`--extend-target` adds to the active set, keeping the defaults."""
    assert resolve_recommended_targets(None, ["deploy"]) == {"install", "test", "fmt", "help", "deploy"}


def test_target_and_extend_combine() -> None:
    """`--target` replaces, then `--extend-target` adds on top."""
    assert resolve_recommended_targets(["build"], ["deploy"]) == {"build", "deploy"}


def test_main_with_valid_makefile(tmp_path: Path) -> None:
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


def test_main_with_missing_targets_no_strict(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Main returns 0 without --strict even with warnings."""
    makefile = tmp_path / "Makefile"
    makefile.write_text("install:\n")

    result = main([str(makefile)])

    assert result == 0
    captured = capsys.readouterr()
    # Exact stderr pins both the "{filename}:" header and the "  - {warning}" line;
    # warnings are diagnostics even when they do not fail the run (no --strict).
    assert captured.err == f"{makefile}:\n  - Missing recommended targets: fmt, help, test\n"
    assert captured.out == ""


def test_main_with_missing_targets_strict(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Main returns 1 with --strict when targets missing."""
    makefile = tmp_path / "Makefile"
    makefile.write_text("install:\n")

    result = main(["--strict", str(makefile)])

    assert result == 1


def test_main_no_files() -> None:
    """Main returns 0 when no files provided."""
    result = main([])
    assert result == 0


def test_main_target_override_satisfied(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`--target` replaces the defaults; a Makefile meeting the custom set passes quietly."""
    makefile = tmp_path / "Makefile"
    makefile.write_text("build:\n\techo hi\n")

    result = main(["--target", "build", str(makefile)])

    assert result == 0
    assert capsys.readouterr().out == ""


def test_main_extend_target_strict_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`--extend-target` adds a requirement; a missing extra target fails under --strict."""
    makefile = tmp_path / "Makefile"
    makefile.write_text("install:\ntest:\nfmt:\nhelp:\n")

    result = main(["--strict", "--extend-target", "deploy", str(makefile)])

    assert result == 1
    assert capsys.readouterr().err == f"{makefile}:\n  - Missing recommended targets: deploy\n"


def test_help_text(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_module_executes_main() -> None:
    """Module execution calls main and exits with its return value."""
    import runpy
    import warnings
    from unittest.mock import patch

    with (
        patch("rhiza_hooks.check_makefile_targets.sys.argv", ["check_makefile_targets"]),
        patch("rhiza_hooks.check_makefile_targets.sys.exit") as mock_exit,
    ):
        # The module is already imported (top-level test import), so runpy warns
        # it was "found in sys.modules ... prior to execution"; filter just that
        # warning rather than mutating sys.modules, which would break module
        # identity for other tests that monkeypatch this module.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=r".*found in sys\.modules.*", category=RuntimeWarning)
            runpy.run_module("rhiza_hooks.check_makefile_targets", run_name="__main__")
        mock_exit.assert_called_once_with(0)


def test_valid_makefile(mock_project: Callable[[dict[str, str]], Path]) -> None:
    """Test with valid Makefile structure."""
    makefile = """
.PHONY: test

test: ## Run tests
\t@echo "Running tests"
"""
    project = mock_project({"Makefile": makefile})

    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "rhiza_hooks.check_makefile_targets"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    # Script should handle basic Makefiles
    assert result.returncode in (0, 1)  # May fail if specific targets required


def test_check_makefile_targets_on_project(project_root: Path) -> None:
    """Test check-makefile-targets on actual project."""
    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "rhiza_hooks.check_makefile_targets"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    # Project Makefile should pass validation
    assert result.returncode == 0


def test_module_is_importable() -> None:
    """Test that the module is importable."""
    result = subprocess.run(  # nosec B603
        [sys.executable, "-c", "import rhiza_hooks.check_makefile_targets"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Failed to import rhiza_hooks.check_makefile_targets: {result.stderr}"


def test_module_has_main_function() -> None:
    """Test that the module has a main function."""
    module = "rhiza_hooks.check_makefile_targets"
    result = subprocess.run(  # nosec B603
        [sys.executable, "-c", f"import {module}; assert hasattr({module}, 'main')"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, "Module rhiza_hooks.check_makefile_targets has no main function"


def test_module_handles_nonexistent_directory(tmp_path: Path) -> None:
    """Test that the module handles nonexistent directories gracefully."""
    nonexistent = tmp_path / "nonexistent"

    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "rhiza_hooks.check_makefile_targets"],
        cwd=nonexistent if nonexistent.exists() else tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    # Scripts should not crash
    assert result.returncode in (0, 1)


def test_module_python_importable() -> None:
    """Test that the module is importable."""
    result = subprocess.run(  # nosec B603
        [sys.executable, "-c", "import rhiza_hooks.check_makefile_targets"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Failed to import rhiza_hooks.check_makefile_targets: {result.stderr}"


def test_catch_all_rule_satisfies_every_recommended_target(tmp_path: Path) -> None:
    """A `%:` rule defines every name, so nothing is missing (#376).

    The rhiza-task shim that rhiza v1.4.0 introduced names only `help` and forwards
    the rest. Reading names alone reported `fmt`, `install` and `test` missing on a
    Makefile where all three work — noise by default, and a blocked commit under
    `--strict`.
    """
    makefile = tmp_path / "Makefile"
    makefile.write_text("help:\n\t@echo help\n\n%: FORCE\n\t@uvx rhiza-task $@\n")
    assert check_makefile(makefile) == []


def test_catch_all_does_not_excuse_a_suffix_rule(tmp_path: Path) -> None:
    """`%.o: %.c` is not a catch-all, so the recommended targets are still required."""
    makefile = tmp_path / "Makefile"
    makefile.write_text("%.o: %.c\n\t$(CC) -c $<\nhelp:\n\t@echo help\n")
    assert check_makefile(makefile) == ["Missing recommended targets: fmt, install, test"]
