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


def _rewrite_workflow_name(filepath: str, expected_name: str) -> None:
    """Rewrite the top-level ``name:`` of a workflow file, preserving comments."""
    # Read file lines to perform replacement while preserving comments
    with open(filepath) as f_read:
        lines = f_read.readlines()

    with open(filepath, "w") as f_write:
        replaced = False  # pragma: no mutate  # equivalent: only ever read via `not replaced`
        skipping_block = False  # pragma: no mutate  # equivalent: only ever read via `if skipping_block`
        for line in lines:
            if skipping_block:
                # Drop the continuation lines of a multi-line/block name scalar.
                # YAML indentation is spaces, so they are blank or space-indented;
                # the first flush-left line ends the scalar.
                if line.strip() == "" or line.startswith(" "):
                    continue
                skipping_block = False  # pragma: no mutate  # equivalent: only ever read via `if skipping_block`
            # Replace only the top-level workflow `name`. It is the sole `name:` key
            # at column 0; job- and step-level `name:` keys are nested and therefore
            # indented, so `startswith("name:")` never matches them. `not replaced`
            # also stops us after the first match (a duplicate top-level key).
            if not replaced and line.startswith("name:"):
                f_write.write(f'name: "{expected_name}"\n')
                replaced = True
                # If the value is a block scalar (`name: >` / `name: |`, plus chomping
                # indicators like `>-`), its value lives on the following indented
                # lines — skip them so we don't leave orphan scalar text behind.
                if line[len("name:") :].strip()[:1] in ("|", ">"):
                    skipping_block = True
            else:
                f_write.write(line)


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
