#!/usr/bin/env python3
"""Read the targets a repository's makefiles define.

Two hooks need this: ``check_makefile_targets`` asks whether the *recommended*
targets are present, and ``check_workflow_make_targets`` asks whether every target
CI *invokes* exists. Both questions start from the same parse, so the parser lives
here rather than in either hook.

Both are really the same question — "is this name defined?" — and since rhiza v1.4.0
neither can be answered from a list of names alone. The root Makefile is a shim whose
only real rule is ``help``; everything else is served by a catch-all pattern rule that
forwards the goal to the ``rhiza-task`` CLI::

    %: $(UVX) FORCE
        @$(UVX) $(RHIZA_TASK) $(RHIZA_TASK_GOAL)

``make test`` works there, and no ``test:`` rule exists. So the parse yields
:class:`MakefileTargets`, which carries the catch-all flag alongside the names and
answers the question itself in :meth:`MakefileTargets.defines`. Leaving each hook to
apply the flag would be leaving each hook to forget it.

The placement is deliberate. A console script's public surface is its ``main()``;
when one entrypoint imports a helper out of another, the dependency between the two
CLIs is invisible from either one's interface, and a change made for the sake of one
hook's command line silently reaches the other. A ``_``-prefixed leaf module states
the shared part explicitly and imports nothing from the package.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Pattern to match Makefile target definitions.
#
# A rule is `name:` or, for double-colon rules, `name::`. Variable assignments
# (`name := ...`, `name ::= ...`) must NOT be mistaken for targets, so the
# colon-run is matched possessively (`:++`, Python 3.11+) and a following `=`
# is rejected with a negative lookahead — `:++` cannot backtrack to a shorter
# run to dodge the lookahead, so `name :=` and `name ::=` are excluded while
# `name:` and `name::` still match. Leading `[a-zA-Z_]` already excludes
# dot-special targets (`.PHONY`) and pattern rules (`%.o`).
TARGET_PATTERN = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*)[ \t]*:++(?!=)", re.MULTILINE)

# A catch-all rule: the pattern rule whose stem is the *whole* target name, so make
# can build any name at all. `TARGET_PATTERN` cannot see it — it excludes pattern
# rules on purpose — but its presence changes what "defined" means for every target,
# which is why it is parsed here and not in either hook.
#
# Written as a stem of exactly `%`: a suffix rule (`%.o: %.c`) matches only names
# ending in `.o`, so the `[ \t]*` between `%` and the colon-run is what separates the
# two. Double-colon (`%::`) is match-anything too, and `:++(?!=)` rejects `%:=` for
# the same reason `TARGET_PATTERN` does.
#
# `.DEFAULT:` is make's other any-target escape hatch and is deliberately *not*
# matched. `%:` says make can build any name; `.DEFAULT:` is more often a recipe that
# prints an error, and treating that as "everything is defined" would suppress real
# reports. `.DEFAULT_GOAL := help` is unaffected either way — the colon-run has to
# follow the name immediately.
CATCH_ALL_PATTERN = re.compile(r"^%[ \t]*:++(?!=)", re.MULTILINE)

# `include a.mk b/*.mk` and its optional forms (`-include`, `sinclude`).
INCLUDE_PATTERN = re.compile(r"^\s*(?:-|s)?include\s+(.+)$", re.MULTILINE)

# A token holding one of these names something only make or a shell can expand, so
# it cannot be resolved at parse time — not to a path, and not to a target name.
VARIABLE_CHARS = ("$", "`")

# A token holding one of these is a glob. That *is* resolvable against the
# filesystem (which is what an include needs) but never to a literal target name.
GLOB_CHARS = ("*", "?")


@dataclass(frozen=True)
class MakefileTargets:
    """What a set of makefiles can build: the names they define, and whether any name goes.

    The two facts have to travel together. A repo whose Makefile is nothing but a
    catch-all rule defines almost no names and can still build every one a caller
    asks for, so a bare set of names is not enough to answer "is this target
    defined?" — and both hooks ask exactly that question. :meth:`defines` is where
    the answer lives, so the two cannot drift apart.
    """

    names: frozenset[str]
    catch_all: bool

    def defines(self, target: str) -> bool:
        """Report whether *target* can be built.

        A named rule defines it:

        >>> MakefileTargets(frozenset({"test"}), catch_all=False).defines("test")
        True
        >>> MakefileTargets(frozenset({"test"}), catch_all=False).defines("fmt")
        False

        So does a catch-all rule, whatever the name:

        >>> MakefileTargets(frozenset(), catch_all=True).defines("anything")
        True
        """
        return self.catch_all or target in self.names

    def __or__(self, other: MakefileTargets) -> MakefileTargets:
        """Merge what two makefiles define, so an ``include`` contributes both halves."""
        return MakefileTargets(self.names | other.names, self.catch_all or other.catch_all)

    def __bool__(self) -> bool:
        """Report whether anything was found — a repo with no makefile at all is falsy.

        Both hooks decline to report against nothing: with no rules to compare, every
        invocation looks undefined, which is noise rather than signal. A lone
        catch-all rule *is* something, so it is truthy.
        """
        return bool(self.names) or self.catch_all


def extract_targets(content: str) -> MakefileTargets:
    """Extract what one makefile's content defines.

    Args:
        content: Contents of a Makefile

    Returns:
        The named targets found, and whether a catch-all rule is present.
    """
    return MakefileTargets(
        names=frozenset(TARGET_PATTERN.findall(content)),
        catch_all=CATCH_ALL_PATTERN.search(content) is not None,
    )


def _expand_include_token(token: str, base: Path) -> list[Path]:
    """Resolve one whitespace-separated word of an ``include`` directive to paths.

    A variable-driven token yields nothing: its value is not knowable here. A glob is
    expanded against the filesystem; anything else is a literal path, returned whether
    or not it exists — the caller skips what it cannot read.
    """
    if any(char in token for char in VARIABLE_CHARS):
        return []
    if any(char in token for char in GLOB_CHARS):
        return sorted(base.glob(token))
    return [base / token]


def _include_paths(content: str, base: Path) -> list[Path]:
    """Resolve the include directives in one makefile to concrete paths.

    Globs are expanded and missing files simply yield nothing, which matches make's
    own behaviour for the optional (``-include``) form and is harmless for the
    mandatory one — a Makefile whose include is missing is broken in a way this hook
    is not trying to report.
    """
    return [
        path
        for directive in INCLUDE_PATTERN.findall(content)
        for token in directive.split()
        for path in _expand_include_token(token, base)
    ]


def collect_targets(repo_root: Path) -> MakefileTargets:
    """Return everything the root Makefile and its includes define, transitively.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        The named targets and the catch-all flag, merged across every makefile
        reached. Falsy when there is no Makefile at all.
    """
    targets = MakefileTargets(frozenset(), catch_all=False)
    seen: set[Path] = set()
    queue = [repo_root / "Makefile"]

    while queue:
        path = queue.pop()
        resolved = path.resolve()
        if resolved in seen or not path.is_file():
            continue
        seen.add(resolved)
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        targets |= extract_targets(content)
        queue.extend(_include_paths(content, repo_root))

    return targets
