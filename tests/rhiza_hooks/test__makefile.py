"""Tests for the shared makefile parser (``rhiza_hooks._makefile``).

The target-extraction cases moved here from ``test_check_makefile_targets`` and the
include-following cases from ``test_check_workflow_make_targets`` when the parser was
lifted out of both hooks; they test the parser, not either command line.
"""

from __future__ import annotations

from pathlib import Path

from rhiza_hooks._makefile import MakefileTargets, collect_targets, extract_targets


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
    targets = extract_targets(content).names
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
    targets = extract_targets(content).names
    assert "build" in targets
    assert "all" in targets


def test_extracts_phony_targets() -> None:
    """Extracts .PHONY style targets."""
    content = """
.PHONY: install test

install:
	pip install .
"""
    targets = extract_targets(content).names
    assert "install" in targets
    # .PHONY is also matched but that's fine


def test_empty_makefile() -> None:
    """Returns empty set for empty Makefile."""
    assert extract_targets("").names == set()


def test_ignores_comments() -> None:
    """Doesn't extract from commented lines."""
    content = """
# This is a comment
# install:
test:
	pytest
"""
    targets = extract_targets(content).names
    assert "test" in targets
    # Comments starting with # aren't matched because they don't start at line beginning
    # after the # character


def test_ignores_recursive_assignment() -> None:
    """`VAR := value` is an assignment, not a target."""
    targets = extract_targets("PREFIX := /usr/local\ninstall:\n\tcp x $(PREFIX)\n").names
    assert targets == {"install"}


def test_ignores_simply_expanded_assignment() -> None:
    """`VAR ::= value` (simply-expanded) is an assignment, not a target."""
    targets = extract_targets("FLAGS ::= -O2\ntest:\n\tpytest\n").names
    assert targets == {"test"}


def test_extracts_double_colon_rule() -> None:
    """`target:: deps` (double-colon rule) is still a target."""
    targets = extract_targets("clean:: prep\n\trm -rf build\n").names
    assert "clean" in targets


def test_ignores_dot_special_and_pattern_targets() -> None:
    """`.PHONY` and pattern rules (`%.o`) are not extracted as recommended targets."""
    targets = extract_targets(".PHONY: build\n%.o: %.c\n\t$(CC) -c $<\nbuild:\n\techo hi\n").names
    assert "build" in targets
    assert ".PHONY" not in targets
    assert "%.o" not in targets


def test_extracts_targets_around_non_ascii_text() -> None:
    """A makefile carrying non-ASCII text parses; the bytes are read as UTF-8."""
    targets = extract_targets("# rôle: nettoyer — supprime tout\nclean:\n\trm -rf build\n").names
    assert targets == {"clean"}


# ---------------------------------------------------------------------------
# collect_targets
# ---------------------------------------------------------------------------
def test_collects_root_targets(tmp_path: Path) -> None:
    """Targets defined in the root Makefile are collected."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\nfmt::\n\techo fmt\n")
    assert collect_targets(tmp_path).names == {"test", "fmt"}


def test_collects_included_targets(tmp_path: Path) -> None:
    """A target defined in an included makefile counts as defined."""
    _write(tmp_path, "Makefile", "include .rhiza/rhiza.mk\ntest:\n\techo hi\n")
    _write(tmp_path, ".rhiza/rhiza.mk", "book:\n\techo book\n")
    assert collect_targets(tmp_path).names == {"test", "book"}


def test_collects_transitively_through_globs(tmp_path: Path) -> None:
    """Includes are followed transitively and globs are expanded (rhiza's own layout)."""
    _write(tmp_path, "Makefile", "include .rhiza/rhiza.mk\n")
    _write(tmp_path, ".rhiza/rhiza.mk", "-include .rhiza/make.d/*.mk\nbootstrap:\n\techo b\n")
    _write(tmp_path, ".rhiza/make.d/test.mk", "coverage:\n\techo c\n")
    _write(tmp_path, ".rhiza/make.d/book.mk", "book:\n\techo b\n")
    assert collect_targets(tmp_path).names == {"bootstrap", "coverage", "book"}


def test_single_character_glob_is_expanded(tmp_path: Path) -> None:
    """`?` is a glob too, and is expanded against the filesystem like `*`."""
    _write(tmp_path, "Makefile", "-include make.?.mk\n")
    _write(tmp_path, "make.a.mk", "alpha:\n\techo a\n")
    _write(tmp_path, "make.long.mk", "omitted:\n\techo o\n")
    assert collect_targets(tmp_path).names == {"alpha"}


def test_missing_include_is_ignored(tmp_path: Path) -> None:
    """An include naming a file that does not exist yields nothing, as with make's -include."""
    _write(tmp_path, "Makefile", "-include local.mk\ntest:\n\techo hi\n")
    assert collect_targets(tmp_path).names == {"test"}


def test_variable_driven_include_is_skipped(tmp_path: Path) -> None:
    """An include whose path comes from a variable cannot be resolved, and is skipped."""
    _write(tmp_path, "Makefile", "include $(EXTRA_MK)\ntest:\n\techo hi\n")
    assert collect_targets(tmp_path).names == {"test"}


def test_include_cycle_terminates(tmp_path: Path) -> None:
    """A makefile including one that includes it back is visited once, not forever."""
    _write(tmp_path, "Makefile", "include a.mk\ntest:\n\techo hi\n")
    _write(tmp_path, "a.mk", "include Makefile\nother:\n\techo o\n")
    assert collect_targets(tmp_path).names == {"test", "other"}


def test_unreadable_makefile_is_skipped(tmp_path: Path) -> None:
    """A binary or undecodable makefile is skipped rather than crashing the hook."""
    _write(tmp_path, "Makefile", "include bad.mk\ntest:\n\techo hi\n")
    (tmp_path / "bad.mk").write_bytes(b"\xff\xfe\x00")
    assert collect_targets(tmp_path).names == {"test"}


def test_non_ascii_makefile_is_read_as_utf8(tmp_path: Path) -> None:
    """A UTF-8 makefile with non-ASCII text is decoded regardless of the platform locale.

    Pins the explicit ``encoding="utf-8"``: without it the read follows the C locale,
    so on a cp1252 Windows box these bytes raise UnicodeDecodeError and the whole
    Makefile silently contributes no targets.
    """
    (tmp_path / "Makefile").write_bytes("# nettoyer — tout\nclean:\n\trm -rf build\n".encode())
    assert collect_targets(tmp_path).names == {"clean"}


def test_no_makefile_defines_nothing(tmp_path: Path) -> None:
    """A repo with no Makefile has no targets."""
    assert collect_targets(tmp_path).names == set()


def test_directory_named_makefile_is_not_read(tmp_path: Path) -> None:
    """A directory called Makefile is not a makefile."""
    (tmp_path / "Makefile").mkdir()
    assert collect_targets(tmp_path).names == set()


# ---------------------------------------------------------------------------
# catch-all detection
# ---------------------------------------------------------------------------
# The rhiza-task shim, reduced to the two rules that matter: `help` is the only
# named target, and `%:` forwards every other goal to the CLI.
_SHIM = """\
.DEFAULT_GOAL := help
.PHONY: help

help: $(UVX)
\t@$(UVX) $(RHIZA_TASK) list

%: $(UVX) FORCE
\t@$(UVX) $(RHIZA_TASK) $@
"""


def test_shim_defines_help_by_name_and_the_rest_by_catch_all() -> None:
    """The v1.4+ root Makefile names one target and serves the others through `%:`.

    This is the whole bug behind #376: `make test` works here, and reading only the
    names says it does not exist.
    """
    targets = extract_targets(_SHIM)
    assert targets.names == {"help"}
    assert targets.catch_all is True
    assert targets.defines("test")


def test_double_colon_catch_all_is_a_catch_all() -> None:
    """`%::` is match-anything too."""
    assert extract_targets("%::\n\techo x\n").catch_all is True


def test_suffix_rule_is_not_a_catch_all() -> None:
    """`%.o: %.c` matches only names ending in `.o`, so it defines nothing by itself."""
    targets = extract_targets("%.o: %.c\n\t$(CC) -c $<\n")
    assert targets.catch_all is False
    assert not targets.defines("test")


def test_default_target_is_not_treated_as_a_catch_all() -> None:
    """`.DEFAULT:` is deliberately not a catch-all — it is usually an error recipe.

    Pins the choice documented on CATCH_ALL_PATTERN: treating it as "everything is
    defined" would suppress real reports in repos that use it to complain about an
    unknown target.
    """
    assert extract_targets(".DEFAULT:\n\t@echo unknown target\n").catch_all is False


def test_default_goal_assignment_is_not_a_catch_all() -> None:
    """`.DEFAULT_GOAL := help` is an assignment; the colon-run must follow the name."""
    assert extract_targets(".DEFAULT_GOAL := help\ntest:\n\techo hi\n").catch_all is False


def test_percent_assignment_is_not_a_catch_all() -> None:
    """`%:=` is rejected by the same lookahead that keeps `VAR :=` from being a target."""
    assert extract_targets("%:= weird\n").catch_all is False


def test_catch_all_in_an_include_counts(tmp_path: Path) -> None:
    """The flag merges across includes, exactly as the names do."""
    _write(tmp_path, "Makefile", "-include local.mk\nhelp:\n\techo h\n")
    _write(tmp_path, "local.mk", "%:\n\techo forwarded\n")
    targets = collect_targets(tmp_path)
    assert targets.names == {"help"}
    assert targets.defines("anything")


def test_no_makefile_has_no_catch_all(tmp_path: Path) -> None:
    """A repo with no Makefile defines nothing, by name or otherwise."""
    targets = collect_targets(tmp_path)
    assert targets.catch_all is False
    assert not targets.defines("test")


# ---------------------------------------------------------------------------
# MakefileTargets
# ---------------------------------------------------------------------------
class TestMakefileTargets:
    """The type both hooks read, and the one place that decides what 'defined' means."""

    def test_defines_a_named_target(self) -> None:
        """A name in the set is defined."""
        assert MakefileTargets(frozenset({"test"}), catch_all=False).defines("test")

    def test_does_not_define_an_absent_target(self) -> None:
        """A name that is neither listed nor caught is not defined."""
        assert not MakefileTargets(frozenset({"test"}), catch_all=False).defines("fmt")

    def test_catch_all_defines_any_name(self) -> None:
        """With a catch-all rule every name is buildable, listed or not."""
        assert MakefileTargets(frozenset(), catch_all=True).defines("whatever")

    def test_merge_unions_names_and_ors_the_flag(self) -> None:
        """`|` carries both halves, so an include cannot drop the catch-all."""
        merged = MakefileTargets(frozenset({"help"}), catch_all=False) | MakefileTargets(
            frozenset({"test"}), catch_all=True
        )
        assert merged.names == {"help", "test"}
        assert merged.catch_all is True

    def test_merge_of_two_plain_makefiles_stays_plain(self) -> None:
        """Nothing invents a catch-all that neither side had."""
        merged = MakefileTargets(frozenset({"a"}), catch_all=False) | MakefileTargets(frozenset({"b"}), catch_all=False)
        assert merged == MakefileTargets(frozenset({"a", "b"}), catch_all=False)

    def test_nothing_found_is_falsy(self) -> None:
        """No names and no catch-all means there was no makefile to compare against."""
        assert not MakefileTargets(frozenset(), catch_all=False)

    def test_names_alone_are_truthy(self) -> None:
        """An ordinary Makefile is something to compare against."""
        assert MakefileTargets(frozenset({"test"}), catch_all=False)

    def test_a_lone_catch_all_is_truthy(self) -> None:
        """A Makefile that is nothing but `%:` still defines every target."""
        assert MakefileTargets(frozenset(), catch_all=True)
