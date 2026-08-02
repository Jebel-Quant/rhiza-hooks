#!/usr/bin/env python3
"""Check that every ``make`` target CI invokes actually exists.

A workflow calling a target the Makefile no longer defines fails only when that
workflow next runs — which, for a scheduled or path-filtered job, can be weeks
after the commit that broke it. The template has already produced this failure:
``make validate`` existed up to rhiza v1.1.3 and was removed by v1.2.1, so
anything still naming it reported healthy repos as broken.

``check-makefile-targets`` asserts that a handful of *recommended* targets exist.
This hook checks the opposite direction — that the targets actually **invoked** are
defined — which is what catches a removal or a rename.

Both sides come from files in the repo, so the check is offline and mechanical:

* **targets** — the root ``Makefile`` plus everything it ``include``s, transitively,
  globs expanded (rhiza's own layout is ``Makefile`` → ``.rhiza/rhiza.mk`` →
  ``.rhiza/make.d/*.mk``); read by :mod:`rhiza_hooks._makefile`, shared with
  ``check-makefile-targets``;
* **invocations** — the shell snippets of every CI definition: ``run:`` in GitHub
  workflows, ``script:``/``before_script:``/``after_script:`` in ``.gitlab-ci.yml``.

Invocations are read out of parsed YAML rather than raw text, so ``name: make sure
the cache is warm`` cannot be mistaken for an invocation of a target called
``sure``. An invocation naming a target through a variable or a matrix expression
(``make ${{ matrix.task }}``) is unresolvable, and is skipped rather than reported:
a false positive here blocks every commit, which is worse than a missed check.

Exit codes:
  0 - every resolvable invocation names a defined target
  1 - at least one invocation names a target nothing defines
"""

from __future__ import annotations

import argparse
import sys
from itertools import chain, takewhile
from pathlib import Path
from typing import Any

import yaml

from rhiza_hooks._makefile import GLOB_CHARS, VARIABLE_CHARS, collect_targets
from rhiza_hooks._repo import find_repo_root

# Where CI definitions live. Workflow files are globbed; the GitLab file is a
# fixed path. Both are optional — a repo may use either platform, or neither.
WORKFLOW_GLOB = ".github/workflows/*.y*ml"
GITLAB_CI = ".gitlab-ci.yml"

# YAML keys whose values are shell snippets, across both platforms.
_SHELL_KEYS = frozenset({"run", "script", "before_script", "after_script"})

# Shell tokens that end the command a `make` word belongs to.
_SEPARATORS = frozenset({"&&", "||", ";", "|", "#"})

# Make flags that consume the following token, so `make -C dir test` does not read
# `dir` as a target. `-j` may appear with or without a value; treating its argument
# as consumed only when it is not itself a target-shaped word is more machinery than
# this is worth, so `-j` is listed and a bare `make -j test` loses `test`. Prefer
# `make -j4 test`, which is what the workflows here write.
_FLAGS_WITH_VALUE = frozenset(
    {"-C", "--directory", "-f", "--file", "--makefile", "-I", "--include-dir", "-o", "-W", "-j", "--jobs"}
)

# A token that cannot be resolved to a literal target name: a variable or command
# substitution, or a glob. Both meanings come from the makefile parser, so the two
# hooks agree on what "unresolvable" means.
_DYNAMIC = (*VARIABLE_CHARS, *GLOB_CHARS)


def _command_strings(value: Any) -> list[str]:
    """Return the shell strings held by the value of a command key.

    A command key carries either one snippet (GitHub's ``run:``) or a list of them
    (GitLab's ``script:``). Anything else — a number, a mapping — is not a command,
    and non-string entries inside a list are dropped rather than crashing the walk.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _snippets_under(key: Any, value: Any) -> list[str]:
    """Return the snippets one mapping entry contributes: its own, or its subtree's."""
    if key in _SHELL_KEYS:
        return _command_strings(value)
    return _shell_snippets(value)


def _shell_snippets(node: Any) -> list[str]:
    """Collect every shell snippet in a parsed CI document.

    Walks the whole tree rather than assuming a platform's schema, gathering the
    string values (and lists of strings) under the keys both platforms use for
    commands.
    """
    if isinstance(node, dict):
        return list(chain.from_iterable(_snippets_under(key, value) for key, value in node.items()))
    if isinstance(node, list):
        return list(chain.from_iterable(_shell_snippets(item) for item in node))
    return []


def _is_dynamic(word: str) -> bool:
    """Report whether a word names something only make or a shell can resolve."""
    return any(char in word for char in _DYNAMIC)


def _drop_flags(words: list[str]) -> list[str]:
    """Drop make's flags and, for the flags that take one, the value that follows."""
    kept: list[str] = []
    skip_next = False
    for word in words:
        if skip_next:
            skip_next = False
        elif word.startswith("-"):
            skip_next = word in _FLAGS_WITH_VALUE
        else:
            kept.append(word)
    return kept


def _targets_in_command(words: list[str]) -> list[str]:
    """Read the target names out of the words following a ``make`` token.

    Stops at the first shell separator, skips flags (and the value of a flag that
    takes one), and skips ``VAR=value`` overrides.

    A single dynamic word abandons the **whole** command rather than just itself.
    ``make ${{ matrix.task }}`` is three words once split, and dropping only the
    ``${{`` would leave ``matrix.task`` and ``}}`` looking like targets — reporting
    two invented names and blocking every commit. Losing a resolvable target that
    happens to share a command with a dynamic one is the cheaper mistake. Flags are
    dropped *first*, so a dynamic flag value (``make -C $DIR test``) costs nothing:
    it is never a target name either way.
    """
    candidates = _drop_flags(list(takewhile(lambda word: word not in _SEPARATORS, words)))
    if any(_is_dynamic(word) for word in candidates):
        return []
    return [word for word in candidates if "=" not in word]


def invoked_targets(snippet: str) -> set[str]:
    """Return the resolvable make targets a shell snippet invokes."""
    targets: set[str] = set()
    for line in snippet.splitlines():
        words = line.replace(";", " ; ").replace("&&", " && ").split()
        for index, word in enumerate(words):
            if word == "make":
                targets.update(_targets_in_command(words[index + 1 :]))
    return targets


def _ci_files(repo_root: Path) -> list[Path]:
    """Return the CI definition files the repo actually has, in a stable order."""
    candidates = [*sorted(repo_root.glob(WORKFLOW_GLOB)), repo_root / GITLAB_CI]
    return [path for path in candidates if path.is_file()]


def _targets_invoked_by(path: Path) -> set[str]:
    """Return every make target one CI definition invokes.

    A file that will not parse as YAML contributes nothing: ``check-yaml`` and
    ``actionlint`` report that, and guessing at a broken document would only produce
    noise.
    """
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError, UnicodeDecodeError, ValueError, OverflowError):
        return set()
    targets: set[str] = set()
    for snippet in _shell_snippets(document):
        targets |= invoked_targets(snippet)
    return targets


def _ci_invocations(repo_root: Path) -> dict[str, set[str]]:
    """Map each CI definition file that invokes make to the targets it names."""
    invocations: dict[str, set[str]] = {}
    for path in _ci_files(repo_root):
        targets = _targets_invoked_by(path)
        if targets:
            invocations[path.relative_to(repo_root).as_posix()] = targets
    return invocations


def check_workflow_make_targets(repo_root: Path) -> list[str]:
    """Report every CI invocation of a make target that nothing defines.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        List of error messages, one per (file, missing target) pair. Empty when
        there is no Makefile — with no targets to compare against, every invocation
        would be reported, which is noise rather than signal.
    """
    defined = collect_targets(repo_root)
    if not defined:
        return []

    return [
        f"{filename} runs `make {target}`, but no Makefile or include defines that target."
        for filename, invoked in _ci_invocations(repo_root).items()
        for target in sorted(invoked - defined)
    ]


def main(argv: list[str] | None = None) -> int:
    """Run the hook and return a process exit code."""
    parser = argparse.ArgumentParser(description="Check every make target invoked by CI exists")
    parser.add_argument(
        "filenames",
        nargs="*",
        help="Filenames (ignored: a target removal must be caught as well as a workflow edit)",
    )
    parser.parse_args(argv)  # validate/consume pre-commit's filename args; result unused

    errors = check_workflow_make_targets(find_repo_root())

    for error in errors:
        print(f"ERROR: {error}")

    return 1 if errors else 0


if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
