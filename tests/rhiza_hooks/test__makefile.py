"""Tests for the shared makefile parser (``rhiza_hooks._makefile``).

The target-extraction cases moved here from ``test_check_makefile_targets`` and the
include-following cases from ``test_check_workflow_make_targets`` when the parser was
lifted out of both hooks; they test the parser, not either command line.
"""

from __future__ import annotations

from pathlib import Path

from rhiza_hooks._makefile import collect_targets, extract_targets


def _write(root: Path, name: str, body: str) -> Path:
    """Write *body* to ``root/name``, creating parent directories."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# extract_targets
# ---------------------------------------------------------------------------
def test_extracts_simple_targets() -> None:
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


def test_extracts_targets_with_dependencies() -> None:
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


def test_extracts_phony_targets() -> None:
    """Extracts .PHONY style targets."""
    content = """
.PHONY: install test

install:
	pip install .
"""
    targets = extract_targets(content)
    assert "install" in targets
    # .PHONY is also matched but that's fine


def test_empty_makefile() -> None:
    """Returns empty set for empty Makefile."""
    assert extract_targets("") == set()


def test_ignores_comments() -> None:
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


def test_ignores_recursive_assignment() -> None:
    """`VAR := value` is an assignment, not a target."""
    targets = extract_targets("PREFIX := /usr/local\ninstall:\n\tcp x $(PREFIX)\n")
    assert targets == {"install"}


def test_ignores_simply_expanded_assignment() -> None:
    """`VAR ::= value` (simply-expanded) is an assignment, not a target."""
    targets = extract_targets("FLAGS ::= -O2\ntest:\n\tpytest\n")
    assert targets == {"test"}


def test_extracts_double_colon_rule() -> None:
    """`target:: deps` (double-colon rule) is still a target."""
    targets = extract_targets("clean:: prep\n\trm -rf build\n")
    assert "clean" in targets


def test_ignores_dot_special_and_pattern_targets() -> None:
    """`.PHONY` and pattern rules (`%.o`) are not extracted as recommended targets."""
    targets = extract_targets(".PHONY: build\n%.o: %.c\n\t$(CC) -c $<\nbuild:\n\techo hi\n")
    assert "build" in targets
    assert ".PHONY" not in targets
    assert "%.o" not in targets


def test_extracts_targets_around_non_ascii_text() -> None:
    """A makefile carrying non-ASCII text parses; the bytes are read as UTF-8."""
    targets = extract_targets("# rôle: nettoyer — supprime tout\nclean:\n\trm -rf build\n")
    assert targets == {"clean"}


# ---------------------------------------------------------------------------
# collect_targets
# ---------------------------------------------------------------------------
def test_collects_root_targets(tmp_path: Path) -> None:
    """Targets defined in the root Makefile are collected."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\nfmt::\n\techo fmt\n")
    assert collect_targets(tmp_path) == {"test", "fmt"}


def test_collects_included_targets(tmp_path: Path) -> None:
    """A target defined in an included makefile counts as defined."""
    _write(tmp_path, "Makefile", "include .rhiza/rhiza.mk\ntest:\n\techo hi\n")
    _write(tmp_path, ".rhiza/rhiza.mk", "book:\n\techo book\n")
    assert collect_targets(tmp_path) == {"test", "book"}


def test_collects_transitively_through_globs(tmp_path: Path) -> None:
    """Includes are followed transitively and globs are expanded (rhiza's own layout)."""
    _write(tmp_path, "Makefile", "include .rhiza/rhiza.mk\n")
    _write(tmp_path, ".rhiza/rhiza.mk", "-include .rhiza/make.d/*.mk\nbootstrap:\n\techo b\n")
    _write(tmp_path, ".rhiza/make.d/test.mk", "coverage:\n\techo c\n")
    _write(tmp_path, ".rhiza/make.d/book.mk", "book:\n\techo b\n")
    assert collect_targets(tmp_path) == {"bootstrap", "coverage", "book"}


def test_single_character_glob_is_expanded(tmp_path: Path) -> None:
    """`?` is a glob too, and is expanded against the filesystem like `*`."""
    _write(tmp_path, "Makefile", "-include make.?.mk\n")
    _write(tmp_path, "make.a.mk", "alpha:\n\techo a\n")
    _write(tmp_path, "make.long.mk", "omitted:\n\techo o\n")
    assert collect_targets(tmp_path) == {"alpha"}


def test_missing_include_is_ignored(tmp_path: Path) -> None:
    """An include naming a file that does not exist yields nothing, as with make's -include."""
    _write(tmp_path, "Makefile", "-include local.mk\ntest:\n\techo hi\n")
    assert collect_targets(tmp_path) == {"test"}


def test_variable_driven_include_is_skipped(tmp_path: Path) -> None:
    """An include whose path comes from a variable cannot be resolved, and is skipped."""
    _write(tmp_path, "Makefile", "include $(EXTRA_MK)\ntest:\n\techo hi\n")
    assert collect_targets(tmp_path) == {"test"}


def test_include_cycle_terminates(tmp_path: Path) -> None:
    """A makefile including one that includes it back is visited once, not forever."""
    _write(tmp_path, "Makefile", "include a.mk\ntest:\n\techo hi\n")
    _write(tmp_path, "a.mk", "include Makefile\nother:\n\techo o\n")
    assert collect_targets(tmp_path) == {"test", "other"}


def test_unreadable_makefile_is_skipped(tmp_path: Path) -> None:
    """A binary or undecodable makefile is skipped rather than crashing the hook."""
    _write(tmp_path, "Makefile", "include bad.mk\ntest:\n\techo hi\n")
    (tmp_path / "bad.mk").write_bytes(b"\xff\xfe\x00")
    assert collect_targets(tmp_path) == {"test"}


def test_non_ascii_makefile_is_read_as_utf8(tmp_path: Path) -> None:
    """A UTF-8 makefile with non-ASCII text is decoded regardless of the platform locale.

    Pins the explicit ``encoding="utf-8"``: without it the read follows the C locale,
    so on a cp1252 Windows box these bytes raise UnicodeDecodeError and the whole
    Makefile silently contributes no targets.
    """
    (tmp_path / "Makefile").write_bytes("# nettoyer — tout\nclean:\n\trm -rf build\n".encode())
    assert collect_targets(tmp_path) == {"clean"}


def test_no_makefile_defines_nothing(tmp_path: Path) -> None:
    """A repo with no Makefile has no targets."""
    assert collect_targets(tmp_path) == set()


def test_directory_named_makefile_is_not_read(tmp_path: Path) -> None:
    """A directory called Makefile is not a makefile."""
    (tmp_path / "Makefile").mkdir()
    assert collect_targets(tmp_path) == set()
