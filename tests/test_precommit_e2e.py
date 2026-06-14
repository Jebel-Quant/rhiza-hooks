"""End-to-end test that runs a hook through pre-commit (issue #184).

The other test modules call ``main()`` directly or invoke the modules with
``python -m``. Neither exercises the wiring that pre-commit actually relies on:
the ``entry:`` declared in ``.pre-commit-hooks.yaml`` must resolve to a console
script declared in ``[project.scripts]`` of ``pyproject.toml``. A regression in
either (a renamed entry, a dropped script) would pass every other test yet break
real consumers.

This module uses ``pre-commit try-repo`` to build this repository's hooks into
an isolated environment from its manifest and run one against a throwaway git
repo. That path goes manifest -> ``[project.scripts]`` -> installed console
script -> ``main()`` exactly as a downstream user would hit it.

The test is skipped (never failed) when the environment cannot support it:
``pre-commit``/``git`` missing, or the isolated build cannot reach the network.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

import pytest

# Phrases that indicate pre-commit could not *build/install* the hook environment
# (network, build backend, resolver) rather than a genuine wiring failure. When
# any appears we skip instead of failing, so an offline box does not break CI.
_ENV_FAILURE_MARKERS = (
    "InstallError",
    "Failed to install",
    "Could not install",
    "ResolutionImpossible",
    "Connection",
    "Temporary failure in name resolution",
    "Network is unreachable",
    "ReadTimeoutError",
    "SSLError",
)

# A self-contained hook with no network use and ``pass_filenames: false`` /
# ``always_run: true`` — ideal for a deterministic end-to-end run.
_HOOK_ID = "check-python-version-consistency"


@pytest.fixture
def repo_root() -> Path:
    """Return the rhiza-hooks repository root (the try-repo target)."""
    return Path(__file__).parent.parent


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command, capturing text output, with a generous timeout."""
    return subprocess.run(  # nosec B603
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


@pytest.mark.timeout(600)
def test_hook_runs_through_pre_commit_try_repo(repo_root: Path, tmp_path: Path) -> None:
    """`pre-commit try-repo` builds this repo's hooks and runs one successfully.

    Proves the ``.pre-commit-hooks.yaml`` entry resolves to the installed
    ``[project.scripts]`` console script end to end.
    """
    if shutil.which("git") is None:
        pytest.skip("git is required for the end-to-end test")

    # A throwaway git repo with versions that the hook considers consistent, so a
    # correctly wired hook must exit 0.
    (tmp_path / ".python-version").write_text("3.11\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "e2e"\nrequires-python = ">=3.11"\n')

    init = _run(["git", "init"], cwd=tmp_path)
    assert init.returncode == 0, init.stderr
    # try-repo / --all-files operate on tracked files.
    _run(["git", "add", "-A"], cwd=tmp_path)

    # Prefer the installed console entry point; fall back to `python -m pre_commit`.
    if shutil.which("pre-commit") is not None:
        base = ["pre-commit"]
    elif importlib.util.find_spec("pre_commit") is not None:
        base = [sys.executable, "-m", "pre_commit"]
    else:
        pytest.skip("pre-commit is required for the end-to-end test")

    try:
        result = _run(
            [*base, "try-repo", str(repo_root), _HOOK_ID, "--all-files", "--verbose"],
            cwd=tmp_path,
        )
    except FileNotFoundError:
        pytest.skip("pre-commit is not installed")
    except subprocess.TimeoutExpired:
        pytest.skip("pre-commit try-repo timed out (slow/no network for the isolated build)")

    combined = f"{result.stdout}\n{result.stderr}"

    if result.returncode != 0 and any(marker in combined for marker in _ENV_FAILURE_MARKERS):
        pytest.skip(f"pre-commit could not build the hook environment:\n{combined}")

    # A clean run proves the wiring: pre-commit found the hook in the manifest,
    # installed the console script from [project.scripts], and ran it to success.
    assert result.returncode == 0, f"try-repo failed:\n{combined}"
    assert _HOOK_ID in combined or "Check Python version consistency" in combined, combined
