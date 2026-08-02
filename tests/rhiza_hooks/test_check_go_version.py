"""Tests for the check_go_version hook.

Combines unit tests, subprocess-level integration tests and property-based
(Hypothesis) invariants for the ``rhiza_hooks.check_go_version`` module.
"""

from __future__ import annotations

import subprocess  # nosec B404
import sys
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rhiza_hooks.check_go_version import (
    _check_at_least,
    _normalize,
    check_version_consistency,
    get_go_mod_directives,
    get_go_version_file,
    main,
    parse_go_mod,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def _write(root: Path, name: str, content: str) -> None:
    """Write dedented *content* to ``root/name``."""
    (root / name).write_text(dedent(content))


# ---------------------------------------------------------------------------
# Unit tests: _normalize
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.22.5", "1.22.5"),
        ("go1.22.5", "1.22.5"),
        ("  go1.22.5\n", "1.22.5"),
        ("default", "default"),
        ("", ""),
        # Only a leading "go" is stripped, and only once.
        ("gogo1.22", "go1.22"),
        ("golang1.22", "lang1.22"),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    """Normalizing strips surrounding whitespace and one leading ``go`` prefix."""
    assert _normalize(raw) == expected


# ---------------------------------------------------------------------------
# Unit tests: parse_go_mod
# ---------------------------------------------------------------------------
def test_parse_go_directive() -> None:
    """The ``go`` directive is extracted."""
    assert parse_go_mod("module example.com/demo\n\ngo 1.22\n") == {"go": "1.22"}


def test_parse_toolchain_directive_strips_go_prefix() -> None:
    """``toolchain go1.22.5`` is normalized to ``1.22.5``."""
    assert parse_go_mod("go 1.22\ntoolchain go1.22.5\n") == {"go": "1.22", "toolchain": "1.22.5"}


def test_parse_ignores_comments() -> None:
    """A trailing ``//`` comment is stripped before matching."""
    assert parse_go_mod("go 1.22 // minimum supported\n") == {"go": "1.22"}


def test_parse_ignores_full_line_comment() -> None:
    """A whole-line comment yields no directive."""
    assert parse_go_mod("// go 1.99\ngo 1.22\n") == {"go": "1.22"}


def test_parse_skips_require_block() -> None:
    """Contents of a parenthesised block never become top-level directives."""
    text = """\
        module example.com/demo

        go 1.22

        require (
        \tgo.uber.org/zap v1.27.0
        \tgithub.com/spf13/cobra v1.8.0
        )

        toolchain go1.22.5
    """
    assert parse_go_mod(dedent(text)) == {"go": "1.22", "toolchain": "1.22.5"}


def test_parse_resumes_after_block_close() -> None:
    """A directive after the closing paren is picked up again (pins the block exit)."""
    text = "require (\n\tfoo v1.0.0\n)\ngo 1.23\n"
    assert parse_go_mod(text) == {"go": "1.23"}


def test_parse_ignores_indented_directive_inside_block() -> None:
    """A ``go`` line inside a block is not mistaken for the top-level directive."""
    text = "go 1.22\nrequire (\n\tgo 1.99\n)\n"
    assert parse_go_mod(text) == {"go": "1.22"}


def test_parse_ignores_directive_on_later_line_of_block() -> None:
    """A directive on the *second* body line of a block is still skipped.

    Every other block test has a single-line body, which the ``continue`` skips
    before the loop re-evaluates ``in_block``. That leaves the exit condition
    unpinned: invert it to ``line == ")"`` and the block would close after one
    line, exposing the rest of the body as top-level directives.
    """
    text = "go 1.22\nrequire (\n\tfoo v1.0.0\n\ttoolchain go1.99.0\n)\n"
    assert parse_go_mod(text) == {"go": "1.22"}


def test_parse_detects_block_opened_with_trailing_comment() -> None:
    """``require ( // comment`` still opens a block.

    Comment stripping is what makes the ``endswith("(")`` test work here. The
    other comment tests use lines where the trailing text cannot change the
    match, so only this shape pins the strip to the block-detection path.
    """
    text = "go 1.22\nrequire ( // direct deps\n\ttoolchain go1.99.0\n)\n"
    assert parse_go_mod(text) == {"go": "1.22"}


def test_parse_ignores_single_line_require() -> None:
    """A single-line ``require`` directive contributes nothing."""
    assert parse_go_mod("go 1.22\nrequire example.com/x v1.0.0\n") == {"go": "1.22"}


def test_parse_ignores_module_path_starting_with_go() -> None:
    """``go.uber.org/zap`` at top level does not match the ``go`` directive."""
    assert parse_go_mod("replace go.uber.org/zap => ./vendor/zap\ngo 1.22\n") == {"go": "1.22"}


def test_parse_duplicate_directive_keeps_last() -> None:
    """A repeated directive (invalid go.mod) keeps its last occurrence."""
    assert parse_go_mod("go 1.21\ngo 1.22\n") == {"go": "1.22"}


def test_parse_empty_text() -> None:
    """Empty go.mod text yields no directives."""
    assert parse_go_mod("") == {}


def test_parse_non_numeric_toolchain() -> None:
    """``toolchain default`` is captured verbatim (it carries no version)."""
    assert parse_go_mod("go 1.22\ntoolchain default\n") == {"go": "1.22", "toolchain": "default"}


# ---------------------------------------------------------------------------
# Unit tests: get_go_mod_directives
# ---------------------------------------------------------------------------
def test_directives_from_file(tmp_path: Path) -> None:
    """Directives are read from the repository's go.mod."""
    _write(tmp_path, "go.mod", "module example.com/demo\n\ngo 1.22\ntoolchain go1.22.5\n")
    assert get_go_mod_directives(tmp_path) == {"go": "1.22", "toolchain": "1.22.5"}


def test_directives_missing_file_returns_empty(tmp_path: Path) -> None:
    """A missing go.mod yields no directives."""
    assert get_go_mod_directives(tmp_path) == {}


def test_directives_unreadable_returns_empty(tmp_path: Path) -> None:
    """An OSError on read (path is a directory) is treated as unspecified."""
    (tmp_path / "go.mod").mkdir()
    assert get_go_mod_directives(tmp_path) == {}


def test_directives_undecodable_returns_empty(tmp_path: Path) -> None:
    """Bytes that are not UTF-8 are treated as unspecified, not raised.

    The read pins ``encoding="utf-8"`` so every platform decodes identically; the
    price is that a latin-1 go.mod now raises everywhere rather than only where the
    locale happens to be strict, so the decode error is caught alongside OSError.
    """
    (tmp_path / "go.mod").write_bytes(b"go 1.22 // caf\xe9\n")
    assert get_go_mod_directives(tmp_path) == {}


# ---------------------------------------------------------------------------
# Unit tests: get_go_version_file
# ---------------------------------------------------------------------------
def test_go_version_file_is_read(tmp_path: Path) -> None:
    """The pinned toolchain is read and stripped."""
    _write(tmp_path, ".go-version", "1.22.5\n")
    assert get_go_version_file(tmp_path) == "1.22.5"


def test_go_version_file_strips_go_prefix(tmp_path: Path) -> None:
    """A ``go``-prefixed pin is normalized like the toolchain directive."""
    _write(tmp_path, ".go-version", "go1.22.5\n")
    assert get_go_version_file(tmp_path) == "1.22.5"


def test_go_version_file_missing_returns_none(tmp_path: Path) -> None:
    """A missing .go-version yields None."""
    assert get_go_version_file(tmp_path) is None


def test_go_version_file_blank_returns_none(tmp_path: Path) -> None:
    """A blank .go-version declares no pin."""
    _write(tmp_path, ".go-version", "  \n")
    assert get_go_version_file(tmp_path) is None


def test_go_version_file_unreadable_returns_none(tmp_path: Path) -> None:
    """An OSError on read (path is a directory) is treated as unspecified."""
    (tmp_path / ".go-version").mkdir()
    assert get_go_version_file(tmp_path) is None


def test_go_version_file_undecodable_returns_none(tmp_path: Path) -> None:
    """A .go-version that is not UTF-8 is treated as unspecified, not raised."""
    (tmp_path / ".go-version").write_bytes(b"1.22.5 \xe9\n")
    assert get_go_version_file(tmp_path) is None


# ---------------------------------------------------------------------------
# Unit tests: _check_at_least
# ---------------------------------------------------------------------------
def test_check_at_least_satisfied() -> None:
    """No error when the source is at or above the minimum."""
    assert _check_at_least("a", "1.23", "b", "1.22") == []


def test_check_at_least_equal_is_satisfied() -> None:
    """Equality satisfies the bound (pins >= rather than >)."""
    assert _check_at_least("a", "1.22", "b", "1.22.0") == []


def test_check_at_least_violated() -> None:
    """An error names both sides and their labels."""
    assert _check_at_least("a", "1.21", "b", "1.22") == ["Go version mismatch: a is 1.21, which is below b 1.22"]


def test_check_at_least_unparseable_source_is_ignored() -> None:
    """A non-numeric source (``default``) carries no version to compare."""
    assert _check_at_least("a", "default", "b", "1.22") == []


def test_check_at_least_unparseable_minimum_is_ignored() -> None:
    """A non-numeric minimum carries no version to compare."""
    assert _check_at_least("a", "1.21", "b", "unknown") == []


# ---------------------------------------------------------------------------
# Unit tests: check_version_consistency
# ---------------------------------------------------------------------------
def test_consistent_project_has_no_errors(tmp_path: Path) -> None:
    """A pin matching the toolchain directive and above the go directive is consistent."""
    _write(tmp_path, "go.mod", "module example.com/demo\n\ngo 1.22\ntoolchain go1.22.5\n")
    _write(tmp_path, ".go-version", "1.22.5\n")
    assert check_version_consistency(tmp_path) == []


def test_toolchain_below_go_directive_is_reported(tmp_path: Path) -> None:
    """The toolchain directive may not be below the go directive."""
    _write(tmp_path, "go.mod", "go 1.23\ntoolchain go1.22.5\n")
    assert check_version_consistency(tmp_path) == [
        "Go version mismatch: go.mod toolchain is 1.22.5, which is below the go.mod go directive 1.23"
    ]


def test_go_version_file_below_go_directive_is_reported(tmp_path: Path) -> None:
    """A .go-version below the go directive could not build the module."""
    _write(tmp_path, "go.mod", "go 1.22\n")
    _write(tmp_path, ".go-version", "1.21.0\n")
    assert check_version_consistency(tmp_path) == [
        "Go version mismatch: .go-version is 1.21.0, which is below the go.mod go directive 1.22"
    ]


def test_go_version_file_above_go_directive_is_fine(tmp_path: Path) -> None:
    """A .go-version newer than the go directive is the normal case."""
    _write(tmp_path, "go.mod", "go 1.22\n")
    _write(tmp_path, ".go-version", "1.24.1\n")
    assert check_version_consistency(tmp_path) == []


def test_go_version_file_disagrees_with_toolchain(tmp_path: Path) -> None:
    """.go-version and the toolchain directive must name the same version."""
    _write(tmp_path, "go.mod", "go 1.22\ntoolchain go1.22.5\n")
    _write(tmp_path, ".go-version", "1.23.1\n")
    assert check_version_consistency(tmp_path) == [
        "Go version mismatch: .go-version pins 1.23.1, but the go.mod toolchain directive pins 1.22.5"
    ]


def test_go_version_file_agrees_modulo_trailing_zero(tmp_path: Path) -> None:
    """``1.22`` and ``1.22.0`` name the same toolchain, not a mismatch."""
    _write(tmp_path, "go.mod", "go 1.22\ntoolchain go1.22.0\n")
    _write(tmp_path, ".go-version", "1.22\n")
    assert check_version_consistency(tmp_path) == []


def test_all_three_relationships_can_fail_together(tmp_path: Path) -> None:
    """Every violated relationship is reported, in declaration order."""
    _write(tmp_path, "go.mod", "go 1.23\ntoolchain go1.21.0\n")
    _write(tmp_path, ".go-version", "1.22.0\n")
    assert check_version_consistency(tmp_path) == [
        "Go version mismatch: go.mod toolchain is 1.21.0, which is below the go.mod go directive 1.23",
        "Go version mismatch: .go-version is 1.22.0, which is below the go.mod go directive 1.23",
        "Go version mismatch: .go-version pins 1.22.0, but the go.mod toolchain directive pins 1.21.0",
    ]


def test_go_mod_without_toolchain_is_fine(tmp_path: Path) -> None:
    """A go.mod with no toolchain directive skips the toolchain comparisons."""
    _write(tmp_path, "go.mod", "module example.com/demo\n\ngo 1.22\n")
    assert check_version_consistency(tmp_path) == []


def test_go_version_file_alone_is_fine(tmp_path: Path) -> None:
    """A .go-version with no go.mod has nothing to disagree with."""
    _write(tmp_path, ".go-version", "1.22.5\n")
    assert check_version_consistency(tmp_path) == []


def test_go_mod_without_go_directive_is_fine(tmp_path: Path) -> None:
    """A go.mod with only a toolchain directive skips the go-directive comparisons."""
    _write(tmp_path, "go.mod", "module example.com/demo\n\ntoolchain go1.22.5\n")
    _write(tmp_path, ".go-version", "1.22.5\n")
    assert check_version_consistency(tmp_path) == []


def test_no_go_files_is_consistent(tmp_path: Path) -> None:
    """A repository with no Go files at all passes (this hook is opt-in per repo)."""
    assert check_version_consistency(tmp_path) == []


# ---------------------------------------------------------------------------
# Unit tests: main
# ---------------------------------------------------------------------------
def test_main_consistent_returns_zero(tmp_path: Path) -> None:
    """Returns 0 when versions are consistent."""
    _write(tmp_path, "go.mod", "go 1.22\ntoolchain go1.22.5\n")
    _write(tmp_path, ".go-version", "1.22.5\n")

    with patch("rhiza_hooks.check_go_version.find_repo_root", return_value=tmp_path):
        assert main([]) == 0


def test_main_inconsistent_returns_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Returns 1 and prints each error with the ERROR prefix."""
    _write(tmp_path, "go.mod", "go 1.22\n")
    _write(tmp_path, ".go-version", "1.21.0\n")

    with patch("rhiza_hooks.check_go_version.find_repo_root", return_value=tmp_path):
        assert main([]) == 1

    assert capsys.readouterr().out == (
        "ERROR: Go version mismatch: .go-version is 1.21.0, which is below the go.mod go directive 1.22\n"
    )


def test_main_no_files_returns_zero(tmp_path: Path) -> None:
    """Returns 0 when no Go version files exist."""
    with patch("rhiza_hooks.check_go_version.find_repo_root", return_value=tmp_path):
        assert main([]) == 0


def test_main_accepts_filenames_argument(tmp_path: Path) -> None:
    """Main accepts (and ignores) pre-commit's filename arguments."""
    with patch("rhiza_hooks.check_go_version.find_repo_root", return_value=tmp_path):
        assert main(["go.mod", ".go-version"]) == 0


def test_unknown_flag_exits() -> None:
    """An unknown flag is parsed and rejected (pins parse_args, not a no-op)."""
    with pytest.raises(SystemExit):
        main(["--definitely-not-a-flag"])


def test_help_text(capsys: pytest.CaptureFixture[str]) -> None:
    """--help renders the exact argparse description, arg name, and help strings."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "XX" not in out  # no mutated literal survived into the rendered help
    assert "Check Go version consistency" in out
    assert "Filenames (ignored, checks repo root)" in out
    assert "filenames" in out


# ---------------------------------------------------------------------------
# Unit tests: module execution via if __name__ == '__main__'
# ---------------------------------------------------------------------------
def test_module_executes_main(tmp_path: Path) -> None:
    """Module execution calls main and exits with its return value."""
    with (
        patch("rhiza_hooks.check_go_version.find_repo_root", return_value=tmp_path),
        patch("rhiza_hooks.check_go_version.sys.argv", ["check_go_version"]),
        patch("rhiza_hooks.check_go_version.sys.exit") as mock_exit,
    ):
        import runpy
        import warnings

        # The module is already imported (top-level test import), so runpy warns
        # it was "found in sys.modules ... prior to execution"; filter just that
        # warning rather than mutating sys.modules.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=r".*found in sys\.modules.*", category=RuntimeWarning)
            runpy.run_module("rhiza_hooks.check_go_version", run_name="__main__")
        mock_exit.assert_called_once_with(0)


# ---------------------------------------------------------------------------
# Subprocess-level integration tests
# ---------------------------------------------------------------------------
def test_subprocess_consistent(mock_project: Callable[[dict[str, str]], Path]) -> None:
    """A consistent Go project exits 0 when run as a module."""
    project = mock_project(
        {
            "go.mod": "module example.com/demo\n\ngo 1.22\ntoolchain go1.22.5\n",
            ".go-version": "1.22.5\n",
        }
    )

    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "rhiza_hooks.check_go_version"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


def test_subprocess_inconsistent(mock_project: Callable[[dict[str, str]], Path]) -> None:
    """A .go-version disagreeing with the toolchain directive exits 1."""
    project = mock_project(
        {
            "go.mod": "module example.com/demo\n\ngo 1.22\ntoolchain go1.22.5\n",
            ".go-version": "1.23.1\n",
        }
    )

    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "rhiza_hooks.check_go_version"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "toolchain directive pins 1.22.5" in result.stdout


def test_subprocess_on_this_project(project_root: Path) -> None:
    """This (Python-only) repository declares no Go versions, so the hook passes."""
    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "rhiza_hooks.check_go_version"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Property-based tests (Hypothesis)
# ---------------------------------------------------------------------------
# Hypothesis rejects function-scoped fixtures, so these drive the pure parsing
# and comparison layers directly rather than materialising files.
_minor = st.integers(min_value=0, max_value=99)
_patch = st.integers(min_value=0, max_value=30)


@given(_minor, _patch)
def test_property_toolchain_prefix_roundtrip(minor: int, patch_level: int) -> None:
    """``toolchain go<v>`` always parses back to ``<v>``."""
    version = f"1.{minor}.{patch_level}"
    assert parse_go_mod(f"go 1.{minor}\ntoolchain go{version}\n")["toolchain"] == version


@given(_minor, _minor)
def test_property_at_or_above_minimum_never_errors(first: int, second: int) -> None:
    """A source at or above the minimum is always silent."""
    source, minimum = max(first, second), min(first, second)
    assert _check_at_least("src", f"1.{source}", "min", f"1.{minimum}") == []


@given(_minor, _minor)
def test_property_below_minimum_always_errors(first: int, second: int) -> None:
    """A source strictly below the minimum always yields exactly one error."""
    source, minimum = min(first, second), max(first, second)
    if source == minimum:
        return
    errors = _check_at_least("src", f"1.{source}", "min", f"1.{minimum}")
    assert errors == [f"Go version mismatch: src is 1.{source}, which is below min 1.{minimum}"]


@given(st.lists(st.tuples(st.sampled_from(["foo", "bar"]), _minor), min_size=1, max_size=5))
def test_property_require_block_contents_are_never_directives(entries: list[tuple[str, int]]) -> None:
    """No require-block line can ever produce a top-level directive."""
    body = "".join(f"\tgo.uber.org/{name} v1.{version}.0\n" for name, version in entries)
    assert parse_go_mod(f"require (\n{body})\n") == {}
