"""Tests for the bumpversion config readers.

Covers ``rhiza_hooks._bumpversion_config`` — the lenient TOML/INI loaders, the
candidate search order bump-my-version itself uses, and the normalisation of both
on-disk formats into a single :class:`BumpversionConfig`. Judging that result
(discoverability, version agreement, target rewritability) is tested in
``test_check_bumpversion_config.py``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from rhiza_hooks._bumpversion_config import (
    INI_CANDIDATES,
    SEARCHED_FILENAMES,
    TOML_CANDIDATES,
    BumpversionConfig,
    BumpversionTarget,
    _load_ini,
    find_config,
    load_toml,
)


def _write(root: Path, name: str, body: str) -> Path:
    """Write *body* to ``root/name``, creating parent directories."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


PYPROJECT = '[project]\nname = "demo"\nversion = "1.2.3"\n'
BUMP_TABLE = "\n[tool.bumpversion]\nallow_dirty = false\n"


# ---------------------------------------------------------------------------
# load_toml / _load_ini
# ---------------------------------------------------------------------------
def test_loads_a_well_formed_toml_file(tmp_path: Path) -> None:
    """A parseable file is returned as its mapping."""
    _write(tmp_path, "pyproject.toml", PYPROJECT)
    assert load_toml(tmp_path / "pyproject.toml") == {"project": {"name": "demo", "version": "1.2.3"}}


def test_missing_toml_reads_none(tmp_path: Path) -> None:
    """A missing TOML file yields None from the loader."""
    assert load_toml(tmp_path / "pyproject.toml") is None


def test_malformed_toml_loads_none(tmp_path: Path) -> None:
    """Malformed TOML is treated as absent, not raised."""
    _write(tmp_path, "pyproject.toml", "[project\nversion =")
    assert load_toml(tmp_path / "pyproject.toml") is None


def test_unreadable_toml_reads_none(tmp_path: Path) -> None:
    """An OSError while opening is treated as absent."""
    _write(tmp_path, "pyproject.toml", PYPROJECT)
    with patch("pathlib.Path.open", side_effect=OSError("boom")):
        assert load_toml(tmp_path / "pyproject.toml") is None


def test_binary_toml_reads_none(tmp_path: Path) -> None:
    """A file that is not valid UTF-8 is treated as absent, not a traceback.

    tomllib decodes the byte stream itself, so invalid UTF-8 arrives as
    UnicodeDecodeError rather than TOMLDecodeError.
    """
    (tmp_path / "pyproject.toml").write_bytes(b"\xff\xfe\x00[project]")
    assert load_toml(tmp_path / "pyproject.toml") is None


def test_missing_ini_reads_none(tmp_path: Path) -> None:
    """A missing INI file yields None from the loader."""
    assert _load_ini(tmp_path / "setup.cfg") is None


def test_unreadable_ini_reads_none(tmp_path: Path) -> None:
    """An OSError while reading an INI file is treated as absent."""
    _write(tmp_path, "setup.cfg", "[bumpversion]\n")
    with patch("configparser.ConfigParser.read", side_effect=OSError("boom")):
        assert _load_ini(tmp_path / "setup.cfg") is None


def test_searched_filenames_list_toml_before_ini() -> None:
    """The advertised search order matches bump-my-version's own: TOML, then INI."""
    assert (*TOML_CANDIDATES, *INI_CANDIDATES) == SEARCHED_FILENAMES


# ---------------------------------------------------------------------------
# BumpversionTarget
# ---------------------------------------------------------------------------
class TestBumpversionTarget:
    """Normalisation of a single file entry, in both on-disk formats."""

    def test_toml_entry_defaults_to_no_search_and_no_regex(self, tmp_path: Path) -> None:
        """An entry giving only a filename leaves search unset for the caller to default."""
        _write(tmp_path, "pyproject.toml", PYPROJECT + BUMP_TABLE + '\n[[tool.bumpversion.files]]\nfilename = "R.md"\n')
        config = find_config(tmp_path)
        assert config is not None
        assert config.targets == [BumpversionTarget(filename="R.md", search=None, regex=False)]

    def test_toml_entry_keeps_an_explicit_search_and_regex_flag(self, tmp_path: Path) -> None:
        """Explicit search/regex values survive normalisation verbatim."""
        _write(
            tmp_path,
            "pyproject.toml",
            PYPROJECT + BUMP_TABLE + '\n[[tool.bumpversion.files]]\nfilename = "R.md"\nsearch = "v"\nregex = true\n',
        )
        config = find_config(tmp_path)
        assert config is not None
        assert config.targets == [BumpversionTarget(filename="R.md", search="v", regex=True)]

    def test_non_string_search_normalises_to_none(self, tmp_path: Path) -> None:
        """A non-string search is dropped rather than coerced, restoring the tool's default."""
        _write(
            tmp_path,
            "pyproject.toml",
            PYPROJECT + BUMP_TABLE + '\n[[tool.bumpversion.files]]\nfilename = "R.md"\nsearch = 42\n',
        )
        config = find_config(tmp_path)
        assert config is not None
        assert config.targets == [BumpversionTarget(filename="R.md", search=None, regex=False)]

    def test_ini_entry_takes_its_filename_from_the_section_name(self, tmp_path: Path) -> None:
        """The INI format encodes the path in the section name, not in a key."""
        _write(
            tmp_path,
            "setup.cfg",
            "[bumpversion]\ncurrent_version = 1.2.3\n\n[bumpversion:file:README.md]\nsearch = v{current_version}\n",
        )
        config = find_config(tmp_path)
        assert config is not None
        assert config.targets == [BumpversionTarget(filename="README.md", search="v{current_version}", regex=False)]

    def test_ini_non_file_sections_are_not_targets(self, tmp_path: Path) -> None:
        """Only ``bumpversion:file:`` sections are targets; part-configs and the like are not."""
        _write(
            tmp_path,
            "setup.cfg",
            "[bumpversion]\ncurrent_version = 1.2.3\n\n[bumpversion:part:release]\nvalues = dev\n",
        )
        config = find_config(tmp_path)
        assert config is not None
        assert config.targets == []

    def test_unusable_toml_entries_are_dropped(self, tmp_path: Path) -> None:
        """Entries that are not tables, or carry no string filename, have nothing checkable."""
        _write(
            tmp_path,
            "pyproject.toml",
            PYPROJECT + BUMP_TABLE + '\nfiles = [42, {search = "no filename"}, {filename = "ok.md"}]\n',
        )
        config = find_config(tmp_path)
        assert config is not None
        assert config.targets == [BumpversionTarget(filename="ok.md", search=None, regex=False)]

    def test_a_files_value_that_is_not_a_list_yields_no_targets(self, tmp_path: Path) -> None:
        """``files`` must be an array of tables; anything else reads as no entries."""
        _write(tmp_path, "pyproject.toml", PYPROJECT + BUMP_TABLE + '\nfiles = "not a list"\n')
        config = find_config(tmp_path)
        assert config is not None
        assert config.targets == []


# ---------------------------------------------------------------------------
# BumpversionConfig / find_config
# ---------------------------------------------------------------------------
class TestBumpversionConfig:
    """The candidate search, in bump-my-version's own order, across both formats."""

    def test_finds_pyproject_tool_table(self, tmp_path: Path) -> None:
        """[tool.bumpversion] in pyproject.toml is discoverable."""
        _write(tmp_path, "pyproject.toml", PYPROJECT + BUMP_TABLE)
        assert find_config(tmp_path) == BumpversionConfig("pyproject.toml", None, [])

    def test_finds_declared_current_version(self, tmp_path: Path) -> None:
        """A declared current_version is carried on the result."""
        _write(tmp_path, "pyproject.toml", PYPROJECT + BUMP_TABLE + 'current_version = "1.2.3"\n')
        assert find_config(tmp_path) == BumpversionConfig("pyproject.toml", "1.2.3", [])

    def test_non_string_current_version_reads_none(self, tmp_path: Path) -> None:
        """A non-string current_version is reported as absent."""
        _write(tmp_path, "pyproject.toml", PYPROJECT + BUMP_TABLE + "current_version = 123\n")
        assert find_config(tmp_path) == BumpversionConfig("pyproject.toml", None, [])

    def test_bumpversion_toml_wins_over_pyproject(self, tmp_path: Path) -> None:
        """.bumpversion.toml is searched before pyproject.toml."""
        _write(tmp_path, "pyproject.toml", PYPROJECT + BUMP_TABLE + 'current_version = "9.9.9"\n')
        _write(tmp_path, ".bumpversion.toml", '[tool.bumpversion]\ncurrent_version = "1.2.3"\n')
        assert find_config(tmp_path) == BumpversionConfig(".bumpversion.toml", "1.2.3", [])

    def test_toml_wins_over_ini(self, tmp_path: Path) -> None:
        """Every TOML candidate is searched before any INI one."""
        _write(tmp_path, "pyproject.toml", PYPROJECT + BUMP_TABLE + 'current_version = "1.2.3"\n')
        _write(tmp_path, "setup.cfg", "[bumpversion]\ncurrent_version = 9.9.9\n")
        assert find_config(tmp_path) == BumpversionConfig("pyproject.toml", "1.2.3", [])

    def test_top_level_bumpversion_section(self, tmp_path: Path) -> None:
        """A top-level [bumpversion] table (not nested under [tool]) is accepted."""
        _write(tmp_path, ".bumpversion.toml", '[bumpversion]\ncurrent_version = "1.2.3"\n')
        assert find_config(tmp_path) == BumpversionConfig(".bumpversion.toml", "1.2.3", [])

    def test_tool_table_without_bumpversion_is_skipped(self, tmp_path: Path) -> None:
        """A [tool] table lacking a bumpversion section does not count as a config."""
        _write(tmp_path, "pyproject.toml", PYPROJECT + "\n[tool.ruff]\nline-length = 100\n")
        assert find_config(tmp_path) is None

    def test_tool_not_a_table_is_skipped(self, tmp_path: Path) -> None:
        """A [tool] key that is not a table does not crash the search."""
        _write(tmp_path, "pyproject.toml", 'tool = "oops"\n')
        assert find_config(tmp_path) is None

    def test_bumpversion_section_not_a_table_is_skipped(self, tmp_path: Path) -> None:
        """A bumpversion key that is not a table is not a usable config."""
        _write(tmp_path, "pyproject.toml", '[tool]\nbumpversion = "oops"\n')
        assert find_config(tmp_path) is None

    def test_finds_setup_cfg_section(self, tmp_path: Path) -> None:
        """A [bumpversion] section in setup.cfg is discoverable."""
        _write(tmp_path, "setup.cfg", "[bumpversion]\ncurrent_version = 1.2.3\n")
        assert find_config(tmp_path) == BumpversionConfig("setup.cfg", "1.2.3", [])

    def test_bumpversion_cfg_wins_over_setup_cfg(self, tmp_path: Path) -> None:
        """.bumpversion.cfg is searched before setup.cfg."""
        _write(tmp_path, ".bumpversion.cfg", "[bumpversion]\ncurrent_version = 1.2.3\n")
        _write(tmp_path, "setup.cfg", "[bumpversion]\ncurrent_version = 9.9.9\n")
        assert find_config(tmp_path) == BumpversionConfig(".bumpversion.cfg", "1.2.3", [])

    def test_ini_config_without_current_version(self, tmp_path: Path) -> None:
        """An INI config lacking current_version reports None for it."""
        _write(tmp_path, ".bumpversion.cfg", "[bumpversion]\ntag = True\n")
        assert find_config(tmp_path) == BumpversionConfig(".bumpversion.cfg", None, [])

    def test_setup_cfg_without_bumpversion_section_is_skipped(self, tmp_path: Path) -> None:
        """An unrelated setup.cfg does not count as a bumpversion config."""
        _write(tmp_path, "setup.cfg", "[metadata]\nname = demo\n")
        assert find_config(tmp_path) is None

    def test_malformed_ini_is_skipped(self, tmp_path: Path) -> None:
        """Malformed INI is treated as absent, not raised."""
        _write(tmp_path, "setup.cfg", "not an ini at all\n= = =\n")
        assert find_config(tmp_path) is None

    def test_no_config_anywhere(self, tmp_path: Path) -> None:
        """An empty tree has no discoverable config."""
        assert find_config(tmp_path) is None
