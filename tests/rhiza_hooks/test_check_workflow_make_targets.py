"""Tests for the ``rhiza_hooks.check_workflow_make_targets`` module."""

from __future__ import annotations

import runpy
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

from rhiza_hooks import check_workflow_make_targets as cwmt


def _write(root: Path, name: str, body: str) -> Path:
    """Write *body* to ``root/name``, creating parent directories."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _workflow(root: Path, run: str, name: str = "ci.yml") -> None:
    """Write a minimal GitHub workflow whose single step runs ``run``."""
    body = "name: CI\njobs:\n  build:\n    steps:\n      - run: |\n"
    body += "".join(f"          {line}\n" for line in run.splitlines())
    _write(root, f".github/workflows/{name}", body)


# ---------------------------------------------------------------------------
# collect_targets
# ---------------------------------------------------------------------------
def test_collects_root_targets(tmp_path: Path) -> None:
    """Targets defined in the root Makefile are collected."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\nfmt::\n\techo fmt\n")
    assert cwmt.collect_targets(tmp_path) == {"test", "fmt"}


def test_collects_included_targets(tmp_path: Path) -> None:
    """A target defined in an included makefile counts as defined."""
    _write(tmp_path, "Makefile", "include .rhiza/rhiza.mk\ntest:\n\techo hi\n")
    _write(tmp_path, ".rhiza/rhiza.mk", "book:\n\techo book\n")
    assert cwmt.collect_targets(tmp_path) == {"test", "book"}


def test_collects_transitively_through_globs(tmp_path: Path) -> None:
    """Includes are followed transitively and globs are expanded (rhiza's own layout)."""
    _write(tmp_path, "Makefile", "include .rhiza/rhiza.mk\n")
    _write(tmp_path, ".rhiza/rhiza.mk", "-include .rhiza/make.d/*.mk\nbootstrap:\n\techo b\n")
    _write(tmp_path, ".rhiza/make.d/test.mk", "coverage:\n\techo c\n")
    _write(tmp_path, ".rhiza/make.d/book.mk", "book:\n\techo b\n")
    assert cwmt.collect_targets(tmp_path) == {"bootstrap", "coverage", "book"}


def test_missing_include_is_ignored(tmp_path: Path) -> None:
    """An include naming a file that does not exist yields nothing, as with make's -include."""
    _write(tmp_path, "Makefile", "-include local.mk\ntest:\n\techo hi\n")
    assert cwmt.collect_targets(tmp_path) == {"test"}


def test_variable_driven_include_is_skipped(tmp_path: Path) -> None:
    """An include whose path comes from a variable cannot be resolved, and is skipped."""
    _write(tmp_path, "Makefile", "include $(EXTRA_MK)\ntest:\n\techo hi\n")
    assert cwmt.collect_targets(tmp_path) == {"test"}


def test_include_cycle_terminates(tmp_path: Path) -> None:
    """A makefile including one that includes it back is visited once, not forever."""
    _write(tmp_path, "Makefile", "include a.mk\ntest:\n\techo hi\n")
    _write(tmp_path, "a.mk", "include Makefile\nother:\n\techo o\n")
    assert cwmt.collect_targets(tmp_path) == {"test", "other"}


def test_unreadable_makefile_is_skipped(tmp_path: Path) -> None:
    """A binary or undecodable makefile is skipped rather than crashing the hook."""
    _write(tmp_path, "Makefile", "include bad.mk\ntest:\n\techo hi\n")
    (tmp_path / "bad.mk").write_bytes(b"\xff\xfe\x00")
    assert cwmt.collect_targets(tmp_path) == {"test"}


def test_no_makefile_defines_nothing(tmp_path: Path) -> None:
    """A repo with no Makefile has no targets."""
    assert cwmt.collect_targets(tmp_path) == set()


def test_directory_named_makefile_is_not_read(tmp_path: Path) -> None:
    """A directory called Makefile is not a makefile."""
    (tmp_path / "Makefile").mkdir()
    assert cwmt.collect_targets(tmp_path) == set()


# ---------------------------------------------------------------------------
# invoked_targets
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("snippet", "expected"),
    [
        ("make test", {"test"}),
        ("make fmt test", {"fmt", "test"}),
        ("make -C subdir test", {"test"}),
        ("make -j4 test", {"test"}),
        ("make --jobs 4 test", {"test"}),
        ("make -f other.mk test", {"test"}),
        ("make VAR=1 test", {"test"}),
        ("make test # then relax", {"test"}),
        ("make fmt && make test", {"fmt", "test"}),
        ("make fmt; echo done", {"fmt"}),
        ("make fmt || true", {"fmt"}),
        ("uv run make test", {"test"}),
        ("make test\nmake book", {"test", "book"}),
        ("echo no invocation here", set()),
        ("make", set()),
    ],
)
def test_invocation_parsing(snippet: str, expected: set[str]) -> None:
    """Flags, overrides, separators and multi-target invocations resolve as expected."""
    assert cwmt.invoked_targets(snippet) == expected


@pytest.mark.parametrize(
    "snippet",
    [
        "make ${{ matrix.task }}",
        "make $TARGET",
        "make ${TARGET}",
        "make $(TARGET)",
        "make `echo test`",
        "make test-*",
    ],
)
def test_dynamic_invocations_are_skipped(snippet: str) -> None:
    """A target named through a variable or glob is unresolvable, so it is skipped, not reported."""
    assert cwmt.invoked_targets(snippet) == set()


# ---------------------------------------------------------------------------
# check_workflow_make_targets
# ---------------------------------------------------------------------------
def test_missing_target_is_reported(tmp_path: Path) -> None:
    """A workflow invoking an undefined target fails, naming file and target."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    _workflow(tmp_path, "make validate")
    errors = cwmt.check_workflow_make_targets(tmp_path)
    assert errors == [".github/workflows/ci.yml runs `make validate`, but no Makefile or include defines that target."]


def test_defined_target_passes(tmp_path: Path) -> None:
    """A workflow invoking a defined target is sound."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    _workflow(tmp_path, "make test")
    assert cwmt.check_workflow_make_targets(tmp_path) == []


def test_target_from_an_include_passes(tmp_path: Path) -> None:
    """A target defined in an included makefile satisfies an invocation."""
    _write(tmp_path, "Makefile", "-include .rhiza/make.d/*.mk\n")
    _write(tmp_path, ".rhiza/make.d/test.mk", "coverage:\n\techo c\n")
    _workflow(tmp_path, "make coverage")
    assert cwmt.check_workflow_make_targets(tmp_path) == []


def test_prose_mentioning_make_is_not_an_invocation(tmp_path: Path) -> None:
    """Only shell snippets are scanned, so a step name mentioning make is not parsed as one.

    Pins the reason invocations are read from parsed YAML rather than raw text: this
    workflow would otherwise report a missing target called 'sure'.
    """
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    _write(
        tmp_path,
        ".github/workflows/ci.yml",
        "name: CI\njobs:\n  build:\n    steps:\n      - name: make sure the cache is warm\n"
        "        uses: actions/cache@v4\n",
    )
    assert cwmt.check_workflow_make_targets(tmp_path) == []


def test_multiple_missing_targets_are_each_reported(tmp_path: Path) -> None:
    """Every missing target in a file is reported, in a stable order."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    _workflow(tmp_path, "make validate\nmake audit")
    errors = cwmt.check_workflow_make_targets(tmp_path)
    assert len(errors) == 2
    assert "`make audit`" in errors[0]
    assert "`make validate`" in errors[1]


def test_several_workflows_are_scanned(tmp_path: Path) -> None:
    """Both .yml and .yaml workflow files are read."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    _workflow(tmp_path, "make validate", name="a.yml")
    _workflow(tmp_path, "make audit", name="b.yaml")
    assert len(cwmt.check_workflow_make_targets(tmp_path)) == 2


def test_gitlab_script_keys_are_scanned(tmp_path: Path) -> None:
    """GitLab's script/before_script/after_script lists are scanned too."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    _write(
        tmp_path,
        ".gitlab-ci.yml",
        "build:\n  before_script:\n    - make install\n  script:\n    - make test\n  after_script:\n    - make clean\n",
    )
    errors = cwmt.check_workflow_make_targets(tmp_path)
    assert len(errors) == 2
    assert "`make clean`" in errors[0]
    assert "`make install`" in errors[1]


def test_non_string_script_items_are_ignored(tmp_path: Path) -> None:
    """A script list holding non-strings (odd YAML) does not crash the walk."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    _write(tmp_path, ".gitlab-ci.yml", "build:\n  script:\n    - 42\n    - make test\n")
    assert cwmt.check_workflow_make_targets(tmp_path) == []


def test_unparseable_yaml_is_skipped(tmp_path: Path) -> None:
    """A workflow that will not parse is left to check-yaml and actionlint."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    _write(tmp_path, ".github/workflows/ci.yml", "invalid: yaml: syntax:\n")
    assert cwmt.check_workflow_make_targets(tmp_path) == []


def test_no_makefile_reports_nothing(tmp_path: Path) -> None:
    """With no Makefile every invocation would be 'missing', which is noise, not signal."""
    _workflow(tmp_path, "make test")
    assert cwmt.check_workflow_make_targets(tmp_path) == []


def test_workflow_without_commands_is_quiet(tmp_path: Path) -> None:
    """A workflow with no shell snippets contributes no invocations."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    _write(
        tmp_path,
        ".github/workflows/ci.yml",
        "name: CI\njobs:\n  build:\n    uses: org/repo/.github/workflows/x.yml@v1\n",
    )
    assert cwmt.check_workflow_make_targets(tmp_path) == []


def test_no_ci_definitions_at_all(tmp_path: Path) -> None:
    """A repo with a Makefile but no CI files passes."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    assert cwmt.check_workflow_make_targets(tmp_path) == []


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def test_main_passes(tmp_path: Path, monkeypatch, capsys) -> None:
    """A sound repo exits 0 silently."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    _workflow(tmp_path, "make test")
    monkeypatch.setattr(cwmt, "find_repo_root", lambda: tmp_path)
    assert cwmt.main([]) == 0
    assert capsys.readouterr().out == ""


def test_main_reports_and_fails(tmp_path: Path, monkeypatch, capsys) -> None:
    """A missing target exits 1 and prints an ERROR: line."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    _workflow(tmp_path, "make validate")
    monkeypatch.setattr(cwmt, "find_repo_root", lambda: tmp_path)
    assert cwmt.main(["ignored.yml"]) == 1
    assert "ERROR: .github/workflows/ci.yml runs `make validate`" in capsys.readouterr().out


def test_module_executes_main(tmp_path: Path, monkeypatch) -> None:
    """Module execution calls main and exits with its return value."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    monkeypatch.setattr(cwmt, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(cwmt.sys, "argv", ["check_workflow_make_targets"])

    with patch("rhiza_hooks.check_workflow_make_targets.sys.exit") as mock_exit:
        # The module is already imported (top-level test import), so runpy warns it was
        # "found in sys.modules ... prior to execution"; filter just that warning rather
        # than mutating sys.modules, which would break module identity for the tests above.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=r".*found in sys\.modules.*", category=RuntimeWarning)
            runpy.run_module("rhiza_hooks.check_workflow_make_targets", run_name="__main__")
        mock_exit.assert_called_once_with(0)
