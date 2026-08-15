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

from rhiza_hooks._repo import find_repo_root

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
            ["make", "help"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as e:
        print(f"Error running 'make help': {e}", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print("Error: 'make help' timed out", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("Error: 'make' command not found", file=sys.stderr)
        return None
    else:
        return result.stdout


def update_readme_with_help(readme_path: Path, help_output: str) -> bool:
    r"""Update README.md with the make help output.

    Args:
        readme_path: Path to the README.md file.
        help_output: The output from 'make help'.

    Returns:
        True if the file was modified, False otherwise.

    The marker pair is the whole contract. Without both markers there is nothing
    to replace and the hook is a silent no-op — which is the usual answer to "why
    did my README not update?":

    >>> import contextlib, io, tempfile
    >>> from pathlib import Path
    >>> tmp = tempfile.TemporaryDirectory()
    >>> readme = Path(tmp.name) / "README.md"
    >>> _ = readme.write_text("intro\n", encoding="utf-8")
    >>> update_readme_with_help(readme, "test: run tests\n")
    False

    With both markers present, everything between them is replaced by the fenced
    help output. The "Updated ..." notice goes to stderr, so it is redirected here
    rather than appearing as expected output:

    >>> _ = readme.write_text(
    ...     "intro\n<!-- MAKE_HELP_START -->\nstale\n<!-- MAKE_HELP_END -->\n", encoding="utf-8"
    ... )
    >>> with contextlib.redirect_stderr(io.StringIO()):
    ...     update_readme_with_help(readme, "test: run tests\n")
    True
    >>> print(readme.read_text(encoding="utf-8"), end="")
    intro
    <!-- MAKE_HELP_START -->
    ```
    test: run tests
    ```
    <!-- MAKE_HELP_END -->

    Re-running with the same help output changes nothing, so the hook converges
    instead of failing every commit:

    >>> with contextlib.redirect_stderr(io.StringIO()):
    ...     update_readme_with_help(readme, "test: run tests\n")
    False
    >>> tmp.cleanup()
    """
    if not readme_path.exists():
        print(f"Warning: {readme_path} not found, skipping update", file=sys.stderr)
        return False

    content = readme_path.read_text(encoding="utf-8")

    # Check if markers exist
    # pragma below: equivalent mutant — with only one marker present the substitution
    # pattern (START.*?END) cannot match either way, so `or`->`and` changes no observable
    # behaviour (return value and file contents are identical).
    if START_MARKER not in content or END_MARKER not in content:  # pragma: no mutate
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
        # newline="" suppresses the \n -> os.linesep translation. `content` came back
        # from a universal-newline read and `help_output` from a text-mode subprocess,
        # so `new_content` is all \n; without this the write would emit CRLF on Windows
        # and reflow the entire README instead of just the help block.
        readme_path.write_text(new_content, encoding="utf-8", newline="")
        print(f"Updated {readme_path} with make help output", file=sys.stderr)
        return True

    return False


def main(argv: list[str] | None = None) -> int:
    """Execute the script."""
    # This hook doesn't use filenames, it always operates on the repo root
    _ = argv  # Unused  # pragma: no mutate  # equivalent: value is never read

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


def _run() -> None:
    """Entry point: delegate to :func:`main` and exit with its return code."""
    sys.exit(main())


if __name__ == "__main__":  # pragma: no cover  # pragma: no mutate
    _run()
