#!/usr/bin/env python3
"""Read the targets a repository's makefiles define.

Two hooks need this: ``check_makefile_targets`` asks whether the *recommended*
targets are present, and ``check_workflow_make_targets`` asks whether every target
CI *invokes* exists. Both questions start from the same parse, so the parser lives
here rather than in either hook.

The placement is deliberate. A console script's public surface is its ``main()``;
when one entrypoint imports a helper out of another, the dependency between the two
CLIs is invisible from either one's interface, and a change made for the sake of one
hook's command line silently reaches the other. A ``_``-prefixed leaf module states
the shared part explicitly and imports nothing from the package.
"""

from __future__ import annotations

import re
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

# `include a.mk b/*.mk` and its optional forms (`-include`, `sinclude`).
INCLUDE_PATTERN = re.compile(r"^\s*(?:-|s)?include\s+(.+)$", re.MULTILINE)

# A token holding one of these names something only make or a shell can expand, so
# it cannot be resolved at parse time — not to a path, and not to a target name.
VARIABLE_CHARS = ("$", "`")

# A token holding one of these is a glob. That *is* resolvable against the
# filesystem (which is what an include needs) but never to a literal target name.
GLOB_CHARS = ("*", "?")


def extract_targets(content: str) -> set[str]:
    """Extract target names from Makefile content.

    Args:
        content: Contents of a Makefile

    Returns:
        Set of target names found
    """
    matches = TARGET_PATTERN.findall(content)
    return set(matches)


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


def collect_targets(repo_root: Path) -> set[str]:
    """Return every target defined by the root Makefile and its includes, transitively.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        Set of target names. Empty when there is no Makefile at all.
    """
    targets: set[str] = set()
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
