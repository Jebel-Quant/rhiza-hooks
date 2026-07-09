#!/usr/bin/env python3
"""Script to ensure GitHub Actions workflows have the (RHIZA) prefix.

This hook checks that all rhiza workflow files have their 'name' field
properly formatted with the (RHIZA) prefix in uppercase. If not, it
automatically updates the file.

Migrated from: https://github.com/Jebel-Quant/rhiza/.rhiza/scripts/check_workflow_names.py
"""

from __future__ import annotations

import sys

import yaml


def _expected_name(name: str) -> str:
    """Return the canonical ``(RHIZA) <UPPERCASE>`` form of a workflow name."""
    prefix = "(RHIZA) "
    # Remove prefix if present to verify the rest of the string
    clean_name = name[len(prefix) :] if name.startswith(prefix) else name
    # Collapse any internal/trailing whitespace (e.g. from a folded/block YAML
    # scalar, where PyYAML yields newlines) so the rewrite is a single line.
    clean_name = " ".join(clean_name.split())
    return f"{prefix}{clean_name.upper()}"


def _is_block_scalar_name(line: str) -> bool:
    """True if a top-level ``name:`` line opens a block scalar (``|`` / ``>``).

    Detection keys on the leading indicator character (``[:1]``) so chomping
    variants like ``>-`` / ``|-`` are recognised too.
    """
    return line[len("name:") :].strip()[:1] in ("|", ">")


def _is_block_continuation(line: str) -> bool:
    """True if ``line`` continues a block scalar's value.

    YAML indentation is spaces, so a scalar's continuation lines are blank or
    space-indented; the first flush-left line ends the scalar.
    """
    return line.strip() == "" or line.startswith(" ")


def _count_block_continuations(following: list[str]) -> int:
    """Count the leading block-scalar continuation lines in ``following``."""
    count = 0
    for line in following:
        if not _is_block_continuation(line):
            break
        count += 1
    return count


def _replace_name_lines(lines: list[str], expected_name: str) -> list[str]:
    """Return ``lines`` with the first top-level ``name:`` set to ``expected_name``.

    Only the top-level workflow ``name`` is rewritten: it is the sole ``name:``
    key at column 0, so job- and step-level ``name:`` keys (always indented)
    never match, and only the first match is replaced. If the value is a block
    scalar (``name: >`` / ``name: |``), its continuation lines are dropped so no
    orphan scalar text is left behind. When no top-level ``name:`` line exists,
    the lines are returned unchanged.
    """
    for idx, line in enumerate(lines):
        if line.startswith("name:"):
            tail = idx + 1
            if _is_block_scalar_name(line):
                tail += _count_block_continuations(lines[idx + 1 :])
            return [*lines[:idx], f'name: "{expected_name}"\n', *lines[tail:]]
    return list(lines)


def _rewrite_workflow_name(filepath: str, expected_name: str) -> None:
    """Rewrite the top-level ``name:`` of a workflow file, preserving comments."""
    with open(filepath) as f_read:
        lines = f_read.readlines()
    with open(filepath, "w") as f_write:
        f_write.writelines(_replace_name_lines(lines, expected_name))


def check_file(filepath: str) -> bool:
    """Check if the workflow file has the correct name prefix and update if needed.

    Args:
        filepath: Path to the workflow file.

    Returns:
        bool: True if file is correct, False if it was updated or has errors.
    """
    with open(filepath) as f:
        try:
            content = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            print(f"Error parsing YAML {filepath}: {exc}")
            return False

    if not isinstance(content, dict):
        # Empty file or not a dict
        return True

    name = content.get("name")
    if not name:
        print(f"Error: {filepath} missing 'name' field.")
        return False

    expected_name = _expected_name(name)

    if name == expected_name:
        return True

    print(f"Updating {filepath}: name '{name}' -> '{expected_name}'")
    _rewrite_workflow_name(filepath, expected_name)
    return False  # Fail so pre-commit knows files were modified


def main(argv: list[str] | None = None) -> int:
    """Execute the script."""
    files = argv if argv is not None else sys.argv[1:]
    failed = False  # pragma: no mutate  # equivalent: only ever read via `if failed`
    for f in files:
        if not check_file(f):
            failed = True

    if failed:
        sys.exit(1)
    return 0


def _run() -> None:
    """Entry point: delegate to :func:`main` and exit with its return code."""
    sys.exit(main())


if __name__ == "__main__":  # pragma: no cover  # pragma: no mutate
    _run()
