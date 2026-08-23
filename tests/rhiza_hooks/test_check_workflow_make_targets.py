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
# invoked_targets
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("snippet", "expected"),
    [
        ("make test", {"test"}),
        ("make fmt test", {"fmt", "test"}),
        ("make -C subdir test", {"test"}),
        # Flags are dropped before the dynamic check, so a variable *flag value* does
        # not abandon the command the way a variable target name does.
        ("make -C $DIR test", {"test"}),
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


def test_scalar_command_value_is_ignored(tmp_path: Path) -> None:
    """A command key holding neither a string nor a list contributes nothing.

    ``script: 42`` is not a command. Reading it as one used to iterate an int and
    raise TypeError, taking the whole hook down over a malformed CI file that
    check-yaml and actionlint are the ones meant to report.
    """
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    _write(tmp_path, ".gitlab-ci.yml", "build:\n  script: 42\n")
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
# summarize
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("files", "invocations", "expected_count"),
    [
        (0, {}, 0),
        (8, {}, 0),
        (1, {"ci.yml": {"test"}}, 1),
        (1, {"ci.yml": {"fmt", "test"}}, 2),
        (2, {"ci.yml": {"test"}, ".gitlab-ci.yml": {"test"}}, 2),
    ],
)
def test_summarize_counts_file_target_pairs(files: int, invocations: dict[str, set[str]], expected_count: int) -> None:
    """The summary counts (file, target) pairs — what the check actually compares."""
    assert cwmt.summarize(files, invocations) == (
        f"inspected {files} CI file(s), found {expected_count} resolvable `make` target invocation(s)"
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def test_main_passes(tmp_path: Path, monkeypatch, capsys) -> None:
    """A sound repo exits 0, writing only the summary, and that to stderr."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    _workflow(tmp_path, "make test")
    monkeypatch.setattr(cwmt, "find_repo_root", lambda: tmp_path)
    assert cwmt.main([]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "inspected 1 CI file(s), found 1 resolvable `make` target invocation(s)\n"


def test_main_summarizes_a_vacuous_run(tmp_path: Path, monkeypatch, capsys) -> None:
    """A repo whose CI delegates to a reusable workflow passes, but says it compared nothing.

    This is the shape of every rhiza-managed repo: `uses:` keeps the commands in
    another repository, so there is nothing here for the hook to read.
    """
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    _write(
        tmp_path,
        ".github/workflows/ci.yml",
        "name: CI\njobs:\n  ci:\n    uses: org/repo/.github/workflows/ci.yml@v1\n",
    )
    monkeypatch.setattr(cwmt, "find_repo_root", lambda: tmp_path)
    assert cwmt.main([]) == 0
    assert "found 0 resolvable `make` target invocation(s)" in capsys.readouterr().err


def test_require_invocations_fails_a_vacuous_run(tmp_path: Path, monkeypatch, capsys) -> None:
    """With the flag, CI files that yield no invocation are an error rather than a silent pass."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    _write(
        tmp_path,
        ".github/workflows/ci.yml",
        "name: CI\njobs:\n  ci:\n    uses: org/repo/.github/workflows/ci.yml@v1\n",
    )
    monkeypatch.setattr(cwmt, "find_repo_root", lambda: tmp_path)
    assert cwmt.main(["--require-invocations"]) == 1
    err = capsys.readouterr().err
    assert "ERROR: no CI file invokes `make`" in err
    assert "found 0 resolvable `make` target invocation(s)" in err


def test_require_invocations_passes_when_ci_invokes_make(tmp_path: Path, monkeypatch) -> None:
    """The flag is satisfied by a single resolvable invocation."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    _workflow(tmp_path, "make test")
    monkeypatch.setattr(cwmt, "find_repo_root", lambda: tmp_path)
    assert cwmt.main(["--require-invocations"]) == 0


def test_require_invocations_spares_a_repo_with_no_ci(tmp_path: Path, monkeypatch) -> None:
    """A repo shipping no CI file is not claiming to have invocations, so the flag is silent.

    Only a repo that ships CI and yields nothing from it is what the flag is for;
    failing on an absent CI directory would report a state the flag cannot speak to.
    """
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    monkeypatch.setattr(cwmt, "find_repo_root", lambda: tmp_path)
    assert cwmt.main(["--require-invocations"]) == 0


def test_require_invocations_still_reports_an_undefined_target(tmp_path: Path, monkeypatch, capsys) -> None:
    """The flag adds a check; it does not replace the one the hook exists for."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    _workflow(tmp_path, "make validate")
    monkeypatch.setattr(cwmt, "find_repo_root", lambda: tmp_path)
    assert cwmt.main(["--require-invocations"]) == 1
    err = capsys.readouterr().err
    assert "`make validate`" in err
    assert "--require-invocations" not in err


def test_main_reports_and_fails(tmp_path: Path, monkeypatch, capsys) -> None:
    """A missing target exits 1 and prints an ERROR: line."""
    _write(tmp_path, "Makefile", "test:\n\techo hi\n")
    _workflow(tmp_path, "make validate")
    monkeypatch.setattr(cwmt, "find_repo_root", lambda: tmp_path)
    assert cwmt.main(["ignored.yml"]) == 1
    err = capsys.readouterr().err
    assert "ERROR: .github/workflows/ci.yml runs `make validate`" in err
    # The summary is context for the errors, so it comes first.
    assert err.index("inspected 1 CI file(s)") < err.index("ERROR:")


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


# ---------------------------------------------------------------------------
# catch-all rules (#376)
# ---------------------------------------------------------------------------
def test_catch_all_rule_resolves_every_invocation(tmp_path: Path) -> None:
    """A `%:` rule defines every name, so no invocation can be reported missing.

    Honest rather than lenient: with a catch-all, make cannot tell a typo from a real
    target either, which is why the rhiza-task shim leaves that to the CLI.
    """
    _write(tmp_path, "Makefile", "help:\n\t@echo help\n\n%: FORCE\n\t@uvx rhiza-task $@\n")
    _workflow(tmp_path, "make anything-at-all")
    assert cwmt.check_workflow_make_targets(tmp_path) == []


def test_suffix_rule_does_not_resolve_an_invocation(tmp_path: Path) -> None:
    """`%.o: %.c` is a pattern rule but not a catch-all, so reporting continues."""
    _write(tmp_path, "Makefile", "%.o: %.c\n\t$(CC) -c $<\ntest:\n\techo hi\n")
    _workflow(tmp_path, "make validate")
    assert len(cwmt.check_workflow_make_targets(tmp_path)) == 1


def test_main_reports_that_a_catch_all_skipped_the_comparison(tmp_path: Path, monkeypatch, capsys) -> None:
    """The summary says why nothing was compared, so a silenced check is not a silent one."""
    _write(tmp_path, "Makefile", "help:\n\t@echo help\n\n%: FORCE\n\t@uvx rhiza-task $@\n")
    _workflow(tmp_path, "make test")
    monkeypatch.setattr(cwmt, "find_repo_root", lambda: tmp_path)
    assert cwmt.main([]) == 0
    assert "a catch-all rule (`%:`) defines every name, so none was compared" in capsys.readouterr().err


def test_summarize_notes_a_catch_all() -> None:
    """The catch-all clause is appended to the counts, not substituted for them."""
    assert cwmt.summarize(2, {"ci.yml": {"test"}}, catch_all=True) == (
        "inspected 2 CI file(s), found 1 resolvable `make` target invocation(s); "
        "a catch-all rule (`%:`) defines every name, so none was compared"
    )
