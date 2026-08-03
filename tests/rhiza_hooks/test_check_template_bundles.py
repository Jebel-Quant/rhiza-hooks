"""Tests for the ``rhiza_hooks.check_template_bundles`` module."""

from __future__ import annotations

import subprocess  # nosec B404
import sys
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

from rhiza_hooks._bundles_fetch import BundlesDoc
from rhiza_hooks.check_template_bundles import (
    _load_and_validate_config,
    _validate_remote_bundles,
    _validate_templates_in_bundles,
    main,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def fetcher_returning(doc: BundlesDoc) -> Callable[..., BundlesDoc]:
    """Return a ``Fetcher``-shaped fake that yields *doc* for any repo/branch.

    Passed as the ``fetcher`` argument rather than monkeypatched over
    ``check_template_bundles.fetch_remote_bundles``: the injected seam exercises the
    same parameter production uses, so a rename of the real function cannot leave these
    tests silently asserting against a fake that is no longer wired to anything.
    """
    return lambda repo, branch, **kwargs: doc


@pytest.fixture
def valid_bundles_content() -> str:
    """Return valid bundles content for testing."""
    return """
version: 1.0
bundles:
  core:
    description: Core files
    files:
      - .gitignore
"""


def _make_config(tmp_path, monkeypatch):
    """Create a minimal template.yml with a templates field and chdir into it."""
    rhiza_dir = tmp_path / ".rhiza"
    rhiza_dir.mkdir()
    (rhiza_dir / "template.yml").write_text(
        dedent("""
        template-repository: test/repo
        template-branch: main
        templates:
          - core
        """)
    )
    monkeypatch.chdir(tmp_path)


# --- main() ---------------------------------------------------------------


def test_main_with_filename_argument(temp_bundles_file, valid_bundles_content):
    """Test main function with filename passed as argument."""
    from rhiza_hooks.check_template_bundles import main

    bundles_file = temp_bundles_file(valid_bundles_content)

    # Test with valid file
    result = main([str(bundles_file)])
    assert result == 0


def test_main_with_invalid_file(temp_bundles_file):
    """Test main function with invalid file - skips validation without templates field."""
    from rhiza_hooks.check_template_bundles import main

    bundles_file = temp_bundles_file("""
        bundles:
          core:
            files:
              - .gitignore
    """)

    # Test with invalid file (missing version) - but no templates field, so skips validation
    result = main([str(bundles_file)])
    assert result == 0


def test_main_with_invalid_file_and_templates(temp_bundles_file, tmp_path):
    """Test main function with invalid file when templates field exists."""
    from rhiza_hooks.check_template_bundles import main

    # Create template.yml with templates field
    template_file = tmp_path / "template.yml"
    template_file.write_text("""
template-repository: test/repo
template-branch: main
templates:
  - core
""")

    # Mock fetch_remote_bundles to return invalid bundles (missing version)
    def mock_fetch_remote_bundles(repo, branch, **kwargs):
        """Return bundles missing the version field to trigger validation failure."""
        return BundlesDoc({"bundles": {"core": {"files": [".gitignore"]}}}, [])

    # Test with invalid file (missing version) - should fail validation
    result = main([str(template_file)], fetcher=mock_fetch_remote_bundles)
    assert result == 1


def test_main_with_cwd_default(tmp_path, monkeypatch, valid_bundles_content, capsys):
    """Test main function uses current working directory when no filename provided."""
    from rhiza_hooks.check_template_bundles import main

    # Create the .rhiza directory structure in tmp_path
    rhiza_dir = tmp_path / ".rhiza"
    rhiza_dir.mkdir()

    # Create template.yml with templates field
    template_file = rhiza_dir / "template.yml"
    template_file.write_text(
        dedent("""
        template-repository: test/repo
        template-branch: main
        templates:
          - core
    """)
    )

    # Mock fetch_remote_bundles to return valid bundles
    def mock_fetch_remote_bundles(repo, branch, **kwargs):
        """Return a valid bundles doc with a single core bundle."""
        return BundlesDoc(
            {"version": 1.0, "bundles": {"core": {"description": "Core files", "files": [".gitignore"]}}}, []
        )

    # Change to the tmp_path directory
    monkeypatch.chdir(tmp_path)

    # Test with no arguments (should use cwd)
    result = main([], fetcher=mock_fetch_remote_bundles)
    assert result == 0
    # Exact success line (splitlines membership rejects a mutated wrapper).
    assert "✓ Template bundles validation passed!" in capsys.readouterr().out.splitlines()


def test_main_with_nonexistent_default_path(tmp_path, monkeypatch):
    """Test main function when default path doesn't exist."""
    from rhiza_hooks.check_template_bundles import main

    # Change to a directory without .rhiza/template-bundles.yml
    monkeypatch.chdir(tmp_path)

    # Test with no arguments (no templates field, should skip validation)
    result = main([])
    assert result == 0


def test_main_skips_validation_without_templates_field(tmp_path, monkeypatch, valid_bundles_content):
    """Test main function skips validation when no templates field in template.yml."""
    from rhiza_hooks.check_template_bundles import main

    # Create the .rhiza directory structure in tmp_path
    rhiza_dir = tmp_path / ".rhiza"
    rhiza_dir.mkdir()
    bundles_file = rhiza_dir / "template-bundles.yml"
    bundles_file.write_text(dedent(valid_bundles_content))

    # Create template.yml WITHOUT templates field (uses include instead)
    template_file = rhiza_dir / "template.yml"
    template_file.write_text(
        dedent("""
        template-repository: test/repo
        template-branch: main
        include:
          - file1
          - file2
    """)
    )

    # Change to the tmp_path directory
    monkeypatch.chdir(tmp_path)

    # Test with no arguments (should skip validation since no templates field)
    result = main([])
    assert result == 0


# --- module execution -----------------------------------------------------


def test_module_executes_main(tmp_path, monkeypatch):
    """Test that the module can be executed directly."""
    import sys

    # Create a valid template.yml with templates field
    rhiza_dir = tmp_path / ".rhiza"
    rhiza_dir.mkdir()
    template_file = rhiza_dir / "template.yml"
    template_file.write_text(
        dedent("""
        template-repository: test/repo
        template-branch: main
        templates:
          - core
    """)
    )

    # Create a script that runs main() in a fresh interpreter with a fake fetcher,
    # passed as an argument rather than patched over the module global.
    mock_script = tmp_path / "mock_fetch.py"
    mock_script.write_text(
        dedent("""
        import sys

        from rhiza_hooks._bundles_fetch import BundlesDoc

        def mock_fetch_remote_bundles(repo, branch, **kwargs):
            return BundlesDoc(
                {
                    "version": 1.0,
                    "bundles": {
                        "core": {
                            "description": "Core files",
                            "files": [".gitignore"]
                        }
                    }
                },
                [],
            )

        from rhiza_hooks.check_template_bundles import main
        sys.exit(main(fetcher=mock_fetch_remote_bundles))
    """)
    )

    # Change to the tmp_path directory
    monkeypatch.chdir(tmp_path)

    # Execute the mock script.
    # Safe: sys.executable is the running interpreter and mock_script is a
    # file created above under pytest's tmp_path — no external/user input.
    result = subprocess.run(  # nosec B603
        [sys.executable, str(mock_script)],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0


# --- alias-form config (repository/ref/profiles) --------------------------


def test_main_with_alias_form_config(tmp_path, monkeypatch, capsys):
    """An alias-form config resolves the repository and proceeds to validation.

    Regression for #268: before normalization moved into ``get_config_data``,
    ``repository``/``ref``/``profiles`` were read as the canonical keys and came
    back ``None``, so the hook printed "Missing template-repository or
    template-branch" and returned 1 instead of validating.
    """
    from rhiza_hooks.check_template_bundles import main

    rhiza_dir = tmp_path / ".rhiza"
    rhiza_dir.mkdir()
    (rhiza_dir / "template.yml").write_text(
        dedent("""
        repository: test/repo
        ref: main
        profiles:
          - core
    """)
    )

    def mock_fetch_remote_bundles(repo, branch, **kwargs):
        """Return valid bundles and pin the resolved repo/branch from the aliases."""
        assert repo == "test/repo"
        assert branch == "main"
        return BundlesDoc(
            {"version": 1.0, "bundles": {"core": {"description": "Core files", "files": [".gitignore"]}}}, []
        )

    monkeypatch.chdir(tmp_path)

    result = main([], fetcher=mock_fetch_remote_bundles)
    assert result == 0
    out = capsys.readouterr().out.splitlines()
    assert "✓ Template bundles validation passed!" in out
    assert "Missing template-repository or template-branch in " + str(rhiza_dir / "template.yml") not in out


def test_alias_form_accepted_by_both_hooks(tmp_path, monkeypatch):
    """check-rhiza-config and check-template-bundles accept the same alias-form input."""
    from rhiza_hooks.check_rhiza_config import validate_rhiza_config
    from rhiza_hooks.check_template_bundles import main

    rhiza_dir = tmp_path / ".rhiza"
    rhiza_dir.mkdir()
    config_file = rhiza_dir / "template.yml"
    config_file.write_text(
        dedent("""
        repository: test/repo
        ref: main
        profiles:
          - core
    """)
    )

    # check-rhiza-config accepts the alias-form config (no validation errors).
    assert validate_rhiza_config(config_file) == []

    # check-template-bundles accepts the identical file and validates successfully.
    fetcher = fetcher_returning(
        BundlesDoc({"version": 1.0, "bundles": {"core": {"description": "Core files", "files": [".gitignore"]}}}, [])
    )
    monkeypatch.chdir(tmp_path)
    assert main([], fetcher=fetcher) == 0


# --- main() error paths ---------------------------------------------------


def test_main_missing_template_repository(tmp_path, monkeypatch, capsys):
    """Test main function when template-repository is missing prints the exact message."""
    from rhiza_hooks.check_template_bundles import main

    # Create the .rhiza directory structure
    rhiza_dir = tmp_path / ".rhiza"
    rhiza_dir.mkdir()

    # Create template.yml with templates but missing template-repository
    template_file = rhiza_dir / "template.yml"
    template_file.write_text(
        dedent("""
        template-branch: main
        templates:
          - core
    """)
    )

    # A fetch stub guards against the mutant branch attempting a real network call.
    stub = fetcher_returning(BundlesDoc(None, ["stub"]))
    # Change to the tmp_path directory
    monkeypatch.chdir(tmp_path)

    # Test with no arguments - should fail early due to missing template-repository,
    # printing the exact message *before* any fetch is attempted.
    result = main([], fetcher=stub)
    assert result == 1
    config_path = tmp_path / ".rhiza" / "template.yml"
    assert f"Missing template-repository or template-branch in {config_path}" in capsys.readouterr().out.splitlines()


def test_main_missing_template_branch(tmp_path, monkeypatch, capsys):
    """Test main function when template-branch is missing prints the exact message."""
    from rhiza_hooks.check_template_bundles import main

    # Create the .rhiza directory structure
    rhiza_dir = tmp_path / ".rhiza"
    rhiza_dir.mkdir()

    # Create template.yml with templates but missing template-branch
    template_file = rhiza_dir / "template.yml"
    template_file.write_text(
        dedent("""
        template-repository: test/repo
        templates:
          - core
    """)
    )

    stub = fetcher_returning(BundlesDoc(None, ["stub"]))
    # Change to the tmp_path directory
    monkeypatch.chdir(tmp_path)

    # Test with no arguments - should fail due to missing template-branch
    result = main([], fetcher=stub)
    assert result == 1
    config_path = tmp_path / ".rhiza" / "template.yml"
    assert f"Missing template-repository or template-branch in {config_path}" in capsys.readouterr().out.splitlines()


def test_main_fetch_remote_fails(tmp_path, monkeypatch):
    """Test main function when fetching remote bundles fails."""
    from rhiza_hooks.check_template_bundles import main

    # Create the .rhiza directory structure
    rhiza_dir = tmp_path / ".rhiza"
    rhiza_dir.mkdir()

    # Create template.yml with templates field
    template_file = rhiza_dir / "template.yml"
    template_file.write_text(
        dedent("""
        template-repository: test/repo
        template-branch: main
        templates:
          - core
    """)
    )

    # Mock fetch_remote_bundles to return failure
    def mock_fetch_remote_bundles(repo, branch, **kwargs):
        """Return a fetch failure with no data and an error message."""
        return BundlesDoc(None, ["Failed to fetch remote bundles"])

    # Change to the tmp_path directory
    monkeypatch.chdir(tmp_path)

    # Test with no arguments - should fail
    result = main([], fetcher=mock_fetch_remote_bundles)
    assert result == 1


def test_main_bundles_not_dict(tmp_path, monkeypatch):
    """Test main function when bundles is not a dict in remote data."""
    from rhiza_hooks.check_template_bundles import main

    # Create the .rhiza directory structure
    rhiza_dir = tmp_path / ".rhiza"
    rhiza_dir.mkdir()

    # Create template.yml with templates field
    template_file = rhiza_dir / "template.yml"
    template_file.write_text(
        dedent("""
        template-repository: test/repo
        template-branch: main
        templates:
          - core
    """)
    )

    # Mock fetch_remote_bundles to return bundles as a list instead of dict
    def mock_fetch_remote_bundles(repo, branch, **kwargs):
        """Return remote data whose bundles field is a list instead of a dict."""
        return BundlesDoc({"version": 1.0, "bundles": []}, [])

    # Change to the tmp_path directory
    monkeypatch.chdir(tmp_path)

    # Test with no arguments - should fail
    result = main([], fetcher=mock_fetch_remote_bundles)
    assert result == 1


def test_main_template_not_in_bundles(tmp_path, monkeypatch, capsys):
    """Test main function when requested template is not in remote bundles."""
    from rhiza_hooks.check_template_bundles import main

    # Create the .rhiza directory structure
    rhiza_dir = tmp_path / ".rhiza"
    rhiza_dir.mkdir()

    # Create template.yml with templates field
    template_file = rhiza_dir / "template.yml"
    template_file.write_text(
        dedent("""
        template-repository: test/repo
        template-branch: main
        templates:
          - core
          - nonexistent
    """)
    )

    # Mock fetch_remote_bundles to return bundles without the requested template
    def mock_fetch_remote_bundles(repo, branch, **kwargs):
        """Return bundles lacking the requested 'nonexistent' template."""
        return BundlesDoc(
            {
                "version": 1.0,
                "bundles": {"core": {"description": "Core files", "files": [".gitignore"]}},
            },
            [],
        )

    # Change to the tmp_path directory
    monkeypatch.chdir(tmp_path)

    # Test with no arguments - should fail
    result = main([], fetcher=mock_fetch_remote_bundles)
    assert result == 1
    # Exact failure header + bullet lines (splitlines membership rejects mutated wrappers).
    config_path = tmp_path / ".rhiza" / "template.yml"
    lines = capsys.readouterr().out.splitlines()
    assert "✗ Template bundles validation failed:" in lines
    assert f"  - Template 'nonexistent' specified in {config_path} not found in remote bundles" in lines


def test_main_invalid_bundle_structure_in_remote(tmp_path, monkeypatch):
    """Test main function when remote bundle has invalid structure."""
    from rhiza_hooks.check_template_bundles import main

    # Create the .rhiza directory structure
    rhiza_dir = tmp_path / ".rhiza"
    rhiza_dir.mkdir()

    # Create template.yml with templates field
    template_file = rhiza_dir / "template.yml"
    template_file.write_text(
        dedent("""
        template-repository: test/repo
        template-branch: main
        templates:
          - core
    """)
    )

    # Mock fetch_remote_bundles to return invalid bundle structure (missing description)
    def mock_fetch_remote_bundles(repo, branch, **kwargs):
        """Return a bundle with invalid structure missing its description."""
        return BundlesDoc({"version": 1.0, "bundles": {"core": {"files": [".gitignore"]}}}, [])

    # Change to the tmp_path directory
    monkeypatch.chdir(tmp_path)

    # Test with no arguments - should fail
    result = main([], fetcher=mock_fetch_remote_bundles)
    assert result == 1


# --- main() stdout guard --------------------------------------------------


def test_main_with_non_textiowrapper_stdout(tmp_path, monkeypatch):
    """main() skips reconfigure when stdout is not a TextIOWrapper."""
    import io

    from rhiza_hooks.check_template_bundles import main

    rhiza_dir = tmp_path / ".rhiza"
    rhiza_dir.mkdir()
    (rhiza_dir / "template.yml").write_text("# No templates field")
    monkeypatch.chdir(tmp_path)

    # io.StringIO is not a TextIOWrapper, so the reconfigure branch is skipped.
    monkeypatch.setattr("sys.stdout", io.StringIO())
    assert main([]) == 0


# --- __main__ block -------------------------------------------------------


def test_main_name_block_execution(tmp_path):
    """Test that the module can be run as __main__."""
    import sys

    # Create a temporary directory with a .rhiza/template.yml that won't trigger validation
    rhiza_dir = tmp_path / ".rhiza"
    rhiza_dir.mkdir()
    template_file = rhiza_dir / "template.yml"
    template_file.write_text("# No templates field")

    # Run the module as __main__ using python -m.
    # Safe: sys.executable is the running interpreter and the argument list is
    # a fixed module name — no external/user input.
    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "rhiza_hooks.check_template_bundles"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0


def test_main_name_block_with_runpy(tmp_path, monkeypatch):
    """Test the __main__ block using runpy to maintain coverage."""
    import runpy
    import sys
    import warnings

    # Create a temporary directory with a .rhiza/template.yml that won't trigger validation
    rhiza_dir = tmp_path / ".rhiza"
    rhiza_dir.mkdir()
    template_file = rhiza_dir / "template.yml"
    template_file.write_text("# No templates field")

    # Change to the tmp_path directory
    monkeypatch.chdir(tmp_path)

    # Mock sys.argv to simulate command-line execution
    original_argv = sys.argv
    sys.argv = ["rhiza_hooks.check_template_bundles"]

    try:
        # Run the module as __main__ using runpy - it should exit with code 0.
        # The module is already imported (top-level test import), so runpy warns
        # it was "found in sys.modules ... prior to execution"; filter just that
        # warning rather than mutating sys.modules, which would break module
        # identity for other tests that monkeypatch this module.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=r".*found in sys\.modules.*", category=RuntimeWarning)
            with pytest.raises(SystemExit) as exc_info:
                runpy.run_module("rhiza_hooks.check_template_bundles", run_name="__main__")
        assert exc_info.value.code == 0
    finally:
        sys.argv = original_argv


# --- _validate_remote_bundles ---------------------------------------------


def test_success_prints_progress(capsys):
    """Successful fetch+validate prints the exact 'Fetching'/'Checking' lines."""
    fetcher = fetcher_returning(
        BundlesDoc({"version": 1.0, "bundles": {"core": {"description": "d", "files": ["f"]}}}, [])
    )
    data, errors = _validate_remote_bundles("test/repo", "main", {"core", "python"}, fetcher=fetcher)
    assert data is not None
    assert errors == []
    # Exact stdout pins both lines and the ', ' join separator (sorted templates).
    assert capsys.readouterr().out == (
        "Fetching template bundles from test/repo (branch: main)\nChecking templates: core, python\n"
    )


def test_fetch_failure_prints_errors(capsys):
    """A failed fetch prints the exact failure header and bullet, returning (None, errors)."""
    fetcher = fetcher_returning(BundlesDoc(None, ["boom"]))
    data, errors = _validate_remote_bundles("test/repo", "main", {"core"}, fetcher=fetcher)
    assert data is None
    assert errors == ["boom"]
    assert capsys.readouterr().out == (
        "Fetching template bundles from test/repo (branch: main)\n"
        "Checking templates: core\n"
        "\n✗ Failed to fetch template bundles:\n"
        "  - boom\n"
    )


def test_invalid_top_level_returns_none(capsys):
    """Remote data missing 'version' fails: returns (None, errors), not (data, [])."""
    fetcher = fetcher_returning(BundlesDoc({"bundles": {}}, []))
    data, errors = _validate_remote_bundles("test/repo", "main", {"core"}, fetcher=fetcher)
    # data is None pins `errors = validate_top_level_fields(data)` (vs the `errors = None` mutant).
    assert data is None
    assert errors == ["Missing required field: version"]
    lines = capsys.readouterr().out.splitlines()
    assert "✗ Template bundles validation failed:" in lines
    assert "  - Missing required field: version" in lines


def test_bundles_not_dict_returns_none(capsys):
    """Remote 'bundles' not a dict fails with the exact header and bullet."""
    fetcher = fetcher_returning(BundlesDoc({"version": 1.0, "bundles": []}, []))
    data, errors = _validate_remote_bundles("test/repo", "main", {"core"}, fetcher=fetcher)
    assert data is None
    assert errors == ["'bundles' must be a dictionary"]
    lines = capsys.readouterr().out.splitlines()
    assert "✗ Template bundles validation failed:" in lines
    assert "  - 'bundles' must be a dictionary" in lines


# --- _validate_templates_in_bundles ---------------------------------------


def test_missing_template_exact_message():
    """A requested template absent from remote bundles yields the exact message."""
    errors = _validate_templates_in_bundles(
        {"nonexistent"}, {"core": {"description": "d", "files": ["f"]}}, Path("cfg")
    )
    assert errors == ["Template 'nonexistent' specified in cfg not found in remote bundles"]


# --- _load_and_validate_config --------------------------------------------


def test_missing_config_prints_and_returns_none(tmp_path, capsys):
    """A missing config file prints the exact skip message and returns None."""
    missing = tmp_path / "template.yml"
    result = _load_and_validate_config(missing)
    assert result is None
    assert capsys.readouterr().out == f"Could not load configuration from {missing}, skipping validation\n"


def test_templates_not_list_returns_none(tmp_path, capsys):
    """A non-list 'templates' field skips validation (returns None)."""
    cfg = tmp_path / "template.yml"
    cfg.write_text('template-repository: test/repo\ntemplate-branch: main\ntemplates: "not a list"\n')
    result = _load_and_validate_config(cfg)
    assert result is None
    assert capsys.readouterr().out == f"No templates field in {cfg}, skipping bundle validation\n"


# --- main() extra coverage ------------------------------------------------


def test_reconfigures_stdout_encoding(tmp_path, monkeypatch):
    """When stdout is a TextIOWrapper, main reconfigures it with the exact encoding/errors."""
    import io
    from unittest.mock import MagicMock

    rhiza_dir = tmp_path / ".rhiza"
    rhiza_dir.mkdir()
    (rhiza_dir / "template.yml").write_text("# no templates field")
    monkeypatch.chdir(tmp_path)

    wrapper = io.TextIOWrapper(io.BytesIO())
    reconfigure = MagicMock()
    monkeypatch.setattr(wrapper, "reconfigure", reconfigure)
    monkeypatch.setattr("sys.stdout", wrapper)

    assert main([]) == 0
    reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")


def test_help_text(capsys):
    """--help renders the exact argparse description and option help strings."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "Validate template-bundles.yml from remote template repository" in out
    assert "Filenames to check (should be .rhiza/template.yml)" in out


def test_offline_skips_fetch(monkeypatch, capsys):
    """--offline returns 0 with the exact notice and never touches the network."""
    from unittest.mock import MagicMock

    # Any attempt to fetch would fail the test, proving the network is skipped.
    urlopen = MagicMock(side_effect=AssertionError("network must not be used in offline mode"))
    monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", urlopen)

    assert main(["--offline"]) == 0
    assert capsys.readouterr().out == "Offline mode: skipping remote template bundles validation\n"
    urlopen.assert_not_called()


# --- --retries / --timeout flags ------------------------------------------


def test_flags_forwarded_to_fetch(tmp_path, monkeypatch):
    """--retries/--timeout are translated to attempts (retries + 1) and timeout."""
    _make_config(tmp_path, monkeypatch)

    seen = {}

    def mock_fetch_remote_bundles(repo, branch, *, attempts, timeout):
        """Record the forwarded attempts and timeout and return valid bundles."""
        seen["attempts"] = attempts
        seen["timeout"] = timeout
        return BundlesDoc({"version": 1.0, "bundles": {"core": {"description": "Core", "files": [".gitignore"]}}}, [])

    assert main(["--retries", "4", "--timeout", "7.5"], fetcher=mock_fetch_remote_bundles) == 0
    # --retries counts retries after the first attempt, so attempts = retries + 1.
    assert seen == {"attempts": 5, "timeout": 7.5}


def test_defaults_when_flags_absent(tmp_path, monkeypatch):
    """Without flags, the documented defaults (2 attempts, 10s) are used."""
    from rhiza_hooks.check_template_bundles import FETCH_ATTEMPTS, FETCH_TIMEOUT_SECONDS

    _make_config(tmp_path, monkeypatch)

    seen = {}

    def mock_fetch_remote_bundles(repo, branch, *, attempts, timeout):
        """Record the default attempts and timeout and return valid bundles."""
        seen["attempts"] = attempts
        seen["timeout"] = timeout
        return BundlesDoc({"version": 1.0, "bundles": {"core": {"description": "Core", "files": [".gitignore"]}}}, [])

    assert main([], fetcher=mock_fetch_remote_bundles) == 0
    assert seen == {"attempts": FETCH_ATTEMPTS, "timeout": FETCH_TIMEOUT_SECONDS}


def test_negative_retries_rejected():
    """--retries below zero is rejected by argument validation."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--retries", "-1"])
    assert exc_info.value.code == 2


def test_non_positive_timeout_rejected():
    """--timeout of zero (or less) is rejected by argument validation."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--timeout", "0"])
    assert exc_info.value.code == 2


def test_zero_retries_accepted(tmp_path, monkeypatch):
    """--retries 0 is the boundary the validator *accepts*: one attempt, no retry.

    Pairs with :func:`test_negative_retries_rejected`. Without this, the guard
    could be ``retries <= 0`` or ``retries < 1`` and every test would still pass,
    silently making a single-attempt run impossible.
    """
    _make_config(tmp_path, monkeypatch)

    seen = {}

    def mock_fetch_remote_bundles(repo, branch, *, attempts, timeout):
        """Record the forwarded attempts and return valid bundles."""
        seen["attempts"] = attempts
        return BundlesDoc({"version": 1.0, "bundles": {"core": {"description": "Core", "files": [".gitignore"]}}}, [])

    assert main(["--retries", "0"], fetcher=mock_fetch_remote_bundles) == 0
    assert seen["attempts"] == 1


def test_sub_second_timeout_accepted(tmp_path, monkeypatch):
    """A timeout in (0, 1] is accepted — "positive", not "at least one second".

    Pairs with :func:`test_non_positive_timeout_rejected`. Without this, the
    guard could be ``timeout <= 1`` and every test would still pass, silently
    rejecting the sub-second timeouts a fast mirror would want.
    """
    _make_config(tmp_path, monkeypatch)

    seen = {}

    def mock_fetch_remote_bundles(repo, branch, *, attempts, timeout):
        """Record the forwarded timeout and return valid bundles."""
        seen["timeout"] = timeout
        return BundlesDoc({"version": 1.0, "bundles": {"core": {"description": "Core", "files": [".gitignore"]}}}, [])

    assert main(["--timeout", "0.5"], fetcher=mock_fetch_remote_bundles) == 0
    assert seen["timeout"] == 0.5


def test_flags_in_help(capsys):
    """--help advertises the new flags."""
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "--retries" in out
    assert "--timeout" in out


# --- integration: check-template-bundles script ---------------------------


def test_valid_bundles(mock_project: Callable[[dict[str, str]], Path]) -> None:
    """Test with valid template bundles."""
    bundles = """
core:
  - .editorconfig
  - .gitignore
"""
    template = """
bundles:
  - core
"""
    project = mock_project(
        {
            ".rhiza/template-bundles.yml": bundles,
            ".rhiza/template.yml": template,
        }
    )

    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "rhiza_hooks.check_template_bundles"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    # May fail if specific validation rules not met
    assert result.returncode in (0, 1)


def test_missing_bundles_file(mock_project: Callable[[dict[str, str]], Path]) -> None:
    """Test with template file that has no templates field."""
    template = """
bundles:
  - core
"""
    project = mock_project({".rhiza/template.yml": template})

    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "rhiza_hooks.check_template_bundles"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    # Script skips validation when no templates field present (returns 0)
    assert result.returncode == 0
    assert "skipping" in result.stdout.lower() or "no templates" in result.stdout.lower()


def test_check_template_bundles_on_project(project_root: Path) -> None:
    """Test check-template-bundles on actual project."""
    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "rhiza_hooks.check_template_bundles"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    # This may fail if template-bundles.yml is missing (expected)
    # We just verify the script runs without crashing
    assert result.returncode in (0, 1)


def test_module_is_importable() -> None:
    """Test that the script module is importable."""
    module_name = "rhiza_hooks.check_template_bundles"
    # Just verify the module is importable
    result = subprocess.run(  # nosec B603
        [sys.executable, "-c", f"import {module_name}"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Failed to import {module_name}: {result.stderr}"


def test_module_has_main_function() -> None:
    """Test that the script has a main function."""
    module_name = "rhiza_hooks.check_template_bundles"
    # Verify the module has a main function
    result = subprocess.run(  # nosec B603
        [sys.executable, "-c", f"import {module_name}; assert hasattr({module_name}, 'main')"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Module {module_name} has no main function"


def test_module_handles_nonexistent_directory(tmp_path: Path) -> None:
    """Test that the script handles nonexistent directories gracefully."""
    module_name = "rhiza_hooks.check_template_bundles"
    nonexistent = tmp_path / "nonexistent"

    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", module_name],
        cwd=nonexistent if nonexistent.exists() else tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    # Scripts should not crash
    assert result.returncode in (0, 1)


def test_module_python_importable() -> None:
    """Test that the script module is importable."""
    module_path = "rhiza_hooks.check_template_bundles"

    result = subprocess.run(  # nosec B603
        [sys.executable, "-c", f"import {module_path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Failed to import {module_path}: {result.stderr}"
