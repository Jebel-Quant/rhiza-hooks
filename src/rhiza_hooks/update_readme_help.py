#!/usr/bin/env python3
"""Script to update README with Makefile help output.

This hook runs 'make help' and embeds the output into README.md
between special marker comments.

Migrated from rhiza's local pre-commit hook that runs 'make readme'.
This is a Python wrapper that provides the same functionality.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404
import sys
from pathlib import Path

# Markers used to identify the section to update in README
START_MARKER = "<!-- MAKE_HELP_START -->"
END_MARKER = "<!-- MAKE_HELP_END -->"


def get_make_help_output() -> str | None:
    """Run 'make help' and capture the output.

    Returns:
        The output from 'make help', or None if the command fails.
    """
    try:
        result = subprocess.run(  # nosec B603 B607
            ["make", "help"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as e:
        print(f"Error running 'make help': {e}")
        return None
    except subprocess.TimeoutExpired:
        print("Error: 'make help' timed out")
        return None
    except FileNotFoundError:
        print("Error: 'make' command not found")
        return None
    else:
        return result.stdout


def update_readme_with_help(readme_path: Path, help_output: str) -> bool:
    """Update README.md with the make help output.

    Args:
        readme_path: Path to the README.md file.
        help_output: The output from 'make help'.

    Returns:
        True if the file was modified, False otherwise.
    """
    if not readme_path.exists():
        print(f"Warning: {readme_path} not found, skipping update")
        return False

    content = readme_path.read_text()

    # Check if markers exist
    if START_MARKER not in content or END_MARKER not in content:
        # No markers, nothing to update
        return False

    # Build the new content between markers
    new_section = f"{START_MARKER}\n```\n{help_output}```\n{END_MARKER}"

    # Replace the content between markers
    pattern = re.compile(
        re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER),
        re.DOTALL,
    )
    new_content = pattern.sub(new_section, content)

    if new_content != content:
        readme_path.write_text(new_content)
        print(f"Updated {readme_path} with make help output")
        return True

    return False


def find_repo_root() -> Path:
    """Find the repository root directory.

    Returns:
        Path to the repository root.
    """
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return Path.cwd()


def main(argv: list[str] | None = None) -> int:
    """Execute the script."""
    # This hook doesn't use filenames, it always operates on the repo root
    _ = argv  # Unused

    repo_root = find_repo_root()
    readme_path = repo_root / "README.md"

    help_output = get_make_help_output()
    if help_output is None:
        # If make help fails, we don't fail the hook
        # This allows the hook to be used in repos without a Makefile
        return 0

    if update_readme_with_help(readme_path, help_output):
        # File was modified, fail so pre-commit knows to re-stage
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
