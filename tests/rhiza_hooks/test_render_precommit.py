"""Tests for :mod:`rhiza_hooks.render_precommit`.

The engine is a *textual* merger — it splices comment-plus-body blocks rather than
round-tripping through a YAML emitter, precisely so the reasoning attached to a hook
survives into the rendered file. That makes the interesting assertions here about
layout and comment placement as much as about the resulting data, so most tests render
a chain and inspect the text, with :func:`yaml.safe_load` used to confirm the text is
still a valid config rather than as the primary assertion.
"""

from __future__ import annotations

import runpy
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from rhiza_hooks import render_precommit as rp
from rhiza_hooks.render_precommit import (
    DEFAULT_FRAGMENT_DIR,
    Block,
    Fragment,
    FragmentError,
    Hook,
    Layout,
    Repo,
    chain,
    deployable,
    header,
    main,
    merge,
    parse_fragment,
    plan,
    render,
    resolve,
)

BASE = """\
# File header, separated from the first key by a blank line.

# Pin node so the npm hooks get a compatible runtime.
default_language_version:
  node: "24.12.0"

repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: check-toml
      - id: check-yaml
        args: ['--unsafe']

  - repo: local
    hooks:
      - id: no-rej-files
        name: Reject .rej files
        entry: "false"
        language: system
"""

PYTHON = """\
# Python layer fragment.

extends: [base.yaml]
output: rendered/python.yaml

repos:
  # No rev: -- the pin is base.yaml's.
  - repo: https://github.com/pre-commit/pre-commit-hooks
    hooks:
      - id: check-yaml
        args: ['--unsafe']
        exclude: ^recipe/meta\\.yaml$

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.16.1
    hooks:
      - id: ruff
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Create a repository with a base fragment and a Python layer extending it."""
    (tmp_path / ".git").mkdir()
    fragments = tmp_path / DEFAULT_FRAGMENT_DIR
    fragments.mkdir()
    (fragments / "base.yaml").write_text(BASE, encoding="utf-8")
    (fragments / "python.yaml").write_text(PYTHON, encoding="utf-8")
    return tmp_path


@pytest.fixture
def layout(repo: Path) -> Layout:
    """A layout rooted at the fixture repository."""
    return Layout.discover(repo_root=repo)


def render_chain(layout: Layout, *references: str, **kwargs: set[str]) -> str:
    """Resolve a chain of fragment references and render it."""
    return render(chain(list(references), layout.fragment_dir, layout), layout, **kwargs)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
class TestLayout:
    """The path context a run reads fragments from and writes configs to."""

    def test_discover_defaults_the_fragment_directory_under_the_root(self, repo: Path) -> None:
        """An unqualified fragment directory hangs off the repository root."""
        assert Layout.discover(repo_root=repo).fragment_dir == repo / DEFAULT_FRAGMENT_DIR

    def test_discover_accepts_an_absolute_fragment_directory(self, repo: Path, tmp_path: Path) -> None:
        """An absolute --fragment-dir is taken as given, not joined onto the root."""
        elsewhere = tmp_path / "elsewhere"
        assert Layout.discover(repo_root=repo, fragment_dir=str(elsewhere)).fragment_dir == elsewhere

    def test_discover_finds_the_root_from_the_working_directory(self, repo: Path, monkeypatch) -> None:
        """With no explicit root, the enclosing git repository is located.

        This is the case that broke when the engine was a script inside the repository
        it rendered: deriving the root from ``__file__`` puts it in site-packages once
        the code is installed.
        """
        nested = repo / "deep" / "nested"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)
        assert Layout.discover().repo_root == repo.resolve()

    def test_display_shortens_paths_inside_the_repository(self, layout: Layout, repo: Path) -> None:
        """Paths under the root are reported relative to it."""
        assert layout.display(repo / "pre-commit" / "base.yaml") == "pre-commit/base.yaml"

    def test_display_leaves_outside_paths_absolute(self, layout: Layout, tmp_path: Path) -> None:
        """A path outside the repository has no useful relative form."""
        outside = (tmp_path.parent / "somewhere-else").resolve()
        assert layout.display(outside) == outside.as_posix()

    def test_display_always_uses_forward_slashes(self, layout: Layout, repo: Path) -> None:
        """The property that keeps rendered output byte-identical across platforms.

        ``display`` output is embedded in the generated file's header, so a backslash
        here would make Windows and Linux render different bytes from the same
        fragments — and the drift check would then fail on whichever platform did not
        render last.
        """
        nested = repo / DEFAULT_FRAGMENT_DIR / "nested" / "frag.yaml"
        assert "\\" not in layout.display(nested)
        assert layout.display(nested) == f"{DEFAULT_FRAGMENT_DIR}/nested/frag.yaml"


class TestBlock:
    """A comment run plus the body lines it documents."""

    def test_renders_comments_before_the_body(self) -> None:
        """Comments lead, which is what puts them above the thing they explain."""
        assert Block(comments=["# why"], body=["  - repo: local"]).render() == ["# why", "  - repo: local"]

    def test_a_comment_only_block_renders_just_the_comment(self) -> None:
        """How a commented-out hook survives the merge with its reasoning attached."""
        assert Block(comments=["# - id: disabled"]).render() == ["# - id: disabled"]


class TestHook:
    """One ``- id: <name>`` item, the unit the merge deduplicates on."""

    def test_carries_its_id_and_block(self) -> None:
        """The id is the merge key; the block is what gets spliced."""
        hook = Hook("ruff", Block(body=["      - id: ruff"]))
        assert (hook.hook_id, hook.block.render()) == ("ruff", ["      - id: ruff"])


class TestRepo:
    """One ``- repo:`` entry of the ``repos:`` list."""

    def test_rev_reads_the_pin(self) -> None:
        """The pin is parsed out of the meta lines rather than stored separately."""
        assert Repo("u", Block(), meta=["    rev: v1"]).rev == "v1"

    def test_rev_ignores_a_trailing_comment(self) -> None:
        """``rev: v1  # note`` is pinned to v1, not to ``v1  # note``."""
        assert Repo("u", Block(), meta=["    rev: v1  # keep"]).rev == "v1"

    def test_rev_skips_meta_lines_before_the_pin(self) -> None:
        """``rev:`` need not be the first line under ``- repo:``."""
        assert Repo("u", Block(), meta=["    # note", "    rev: v2"]).rev == "v2"

    def test_rev_is_none_without_a_pin(self) -> None:
        """``repo: local`` has no rev, and an inheriting entry omits one."""
        assert Repo("local", Block()).rev is None

    def test_copy_is_independent(self) -> None:
        """Merging must never mutate a parsed fragment."""
        original = Repo("u", Block(), meta=["    rev: v1"], hooks=[Hook("a", Block())])
        clone = original.copy()
        clone.hooks.append(Hook("b", Block()))
        assert [hook.hook_id for hook in original.hooks] == ["a"]

    def test_renders_bare_when_it_has_no_hooks(self) -> None:
        """Stops before emitting a ``hooks:`` key with nothing under it."""
        assert Repo("local", Block(body=["  - repo: local"])).render() == ["  - repo: local"]

    def test_separates_spaced_hooks_with_a_blank_line(self) -> None:
        """The grouping the fragments used is preserved, not normalised away."""
        entry = Repo(
            "local",
            Block(body=["  - repo: local"]),
            hooks=[
                Hook("a", Block(body=["      - id: a"])),
                Hook("b", Block(body=["      - id: b"], spaced=True)),
            ],
        )
        assert entry.render() == ["  - repo: local", "    hooks:", "      - id: a", "", "      - id: b"]


class TestFragment:
    """A parsed fragment: meta keys, preamble blocks and repositories."""

    def test_defaults_to_an_empty_mixin(self) -> None:
        """Everything is optional except the path it was read from."""
        fragment = Fragment(path=Path("x.yaml"))
        assert (fragment.output, fragment.extends, fragment.repos, fragment.preamble) == (None, [], {}, {})


class TestFragmentError:
    """The single error type the engine raises."""

    def test_is_a_runtime_error(self) -> None:
        """Callers catch it alongside OSError; subclassing keeps that broad catch honest."""
        assert issubclass(FragmentError, RuntimeError)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def test_reads_meta_keys_and_strips_them_from_the_preamble(repo: Path) -> None:
    """``extends`` and ``output`` are meta, not config."""
    fragment = parse_fragment(repo / DEFAULT_FRAGMENT_DIR / "python.yaml")
    assert fragment.extends == ["base.yaml"]
    assert fragment.output == "rendered/python.yaml"
    assert "extends" not in fragment.preamble
    assert "output" not in fragment.preamble


def test_a_mixin_declares_no_output(repo: Path) -> None:
    """A fragment with no ``output`` is only ever pulled in via ``extends``."""
    assert parse_fragment(repo / DEFAULT_FRAGMENT_DIR / "base.yaml").output is None


def test_keeps_non_repos_top_level_keys_as_preamble(repo: Path) -> None:
    """``default_language_version`` survives into the rendered config."""
    fragment = parse_fragment(repo / DEFAULT_FRAGMENT_DIR / "base.yaml")
    assert "default_language_version" in fragment.preamble


def test_the_file_header_is_dropped_but_a_key_comment_is_kept(repo: Path) -> None:
    """A blank line separates the file header from the first key's own comment."""
    fragment = parse_fragment(repo / DEFAULT_FRAGMENT_DIR / "base.yaml")
    comments = fragment.preamble["default_language_version"].comments
    assert any("Pin node" in line for line in comments)
    assert not any("File header" in line for line in comments)


def test_a_leading_key_with_no_blank_line_above_it_keeps_no_comments(repo: Path) -> None:
    """With no blank line, the whole run above the first key is file header."""
    path = repo / "headerless.yaml"
    path.write_text("# All header, no blank line.\nrepos:\n  - repo: local\n    hooks:\n      - id: x\n")
    assert parse_fragment(path).preamble == {}


def test_rejects_a_file_with_no_top_level_keys(repo: Path) -> None:
    """A comment-only file is not a fragment."""
    path = repo / "empty.yaml"
    path.write_text("# nothing but a comment\n")
    with pytest.raises(FragmentError, match="no top-level keys"):
        parse_fragment(path)


def test_rejects_a_repo_entry_with_no_url(repo: Path) -> None:
    """``- repo:`` with nothing after it names no repository."""
    path = repo / "nourl.yaml"
    path.write_text("repos:\n  - repo:\n    hooks:\n      - id: x\n")
    with pytest.raises(FragmentError, match="repo entry with no URL"):
        parse_fragment(path)


def test_rejects_a_hook_with_an_empty_id(repo: Path) -> None:
    """A hook is identified by its id; without one it cannot be merged."""
    path = repo / "noid.yaml"
    path.write_text("repos:\n  - repo: local\n    hooks:\n      - id:\n")
    with pytest.raises(FragmentError, match="hook with an empty id"):
        parse_fragment(path)


def test_rejects_a_repo_declaring_hooks_twice(repo: Path) -> None:
    """Two ``hooks:`` keys in one entry is ambiguous rather than additive."""
    path = repo / "twice.yaml"
    path.write_text("repos:\n  - repo: local\n    hooks:\n      - id: a\n    hooks:\n      - id: b\n")
    with pytest.raises(FragmentError, match="declares hooks: more than once"):
        parse_fragment(path)


def test_a_repo_entry_without_hooks_keeps_its_trailing_lines_as_meta(repo: Path) -> None:
    """Everything between ``- repo:`` and a missing ``hooks:`` is meta."""
    path = repo / "nohooks.yaml"
    path.write_text("repos:\n  - repo: https://example.com/x\n    rev: v1\n")
    assert parse_fragment(path).repos["https://example.com/x"].rev == "v1"


def test_collapses_repeated_local_entries_in_one_fragment(repo: Path) -> None:
    """``repo: local`` may appear several times; the hooks concatenate."""
    path = repo / "twolocal.yaml"
    path.write_text("repos:\n  - repo: local\n    hooks:\n      - id: a\n  - repo: local\n    hooks:\n      - id: b\n")
    hooks = parse_fragment(path).repos["local"].hooks
    assert [hook.hook_id for hook in hooks] == ["a", "b"]


def test_a_trailing_comment_attaches_to_the_last_repo(repo: Path) -> None:
    """A commented-out hook at the end of the file is kept, not dropped."""
    path = repo / "trailing.yaml"
    path.write_text("repos:\n  - repo: local\n    hooks:\n      - id: a\n      # - id: disabled-on-purpose\n")
    trailing = parse_fragment(path).repos["local"].trailing
    assert any("disabled-on-purpose" in line for block in trailing for line in block.comments)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("output: [not, a, string]\nrepos:\n  - repo: local\n", "output: must be a path string"),
        ("extends: notalist\nrepos:\n  - repo: local\n", "extends: must be a list"),
        ("extends: [1, 2]\nrepos:\n  - repo: local\n", "extends: must be a list"),
        ("remove: [a]\nrepos:\n  - repo: local\n", "remove: must be a mapping"),
        ("remove:\n  bogus: [a]\nrepos:\n  - repo: local\n", "remove: must be a mapping"),
    ],
)
def test_rejects_a_malformed_meta_key(repo: Path, body: str, expected: str) -> None:
    """Each meta key has one shape; anything else is refused with its name."""
    path = repo / "bad.yaml"
    path.write_text(body)
    with pytest.raises(FragmentError, match=expected):
        parse_fragment(path)


def test_rejects_unparseable_yaml_in_a_meta_key(repo: Path) -> None:
    """The meta block is the one place the engine really does parse YAML."""
    path = repo / "badyaml.yaml"
    path.write_text('extends: ["unclosed\nrepos:\n  - repo: local\n')
    with pytest.raises(FragmentError, match="cannot parse"):
        parse_fragment(path)


def test_a_valueless_remove_is_rejected(repo: Path) -> None:
    """A bare ``remove:`` is an unfinished edit, not an empty removal list.

    It parses to ``None``, which is not the mapping the key requires, so it is
    refused rather than silently read as "remove nothing".
    """
    path = repo / "scalar.yaml"
    path.write_text("remove:\nrepos:\n  - repo: local\n    hooks:\n      - id: a\n")
    with pytest.raises(FragmentError, match="remove: must be a mapping"):
        parse_fragment(path)


def test_an_empty_removal_list_is_accepted(repo: Path) -> None:
    """``hooks:`` with no entries is a well-formed declaration of nothing."""
    path = repo / "emptyremove.yaml"
    path.write_text("remove:\n  hooks:\nrepos:\n  - repo: local\n    hooks:\n      - id: a\n")
    assert parse_fragment(path).remove_hooks == set()


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------
def test_a_bare_name_resolves_inside_the_fragment_directory(layout: Layout) -> None:
    """``python`` finds ``pre-commit/python.yaml`` without the extension."""
    assert resolve("python", layout.repo_root, layout).name == "python.yaml"


def test_a_yml_extension_is_honoured(repo: Path, layout: Layout) -> None:
    """Both spellings of the extension are accepted as given."""
    (layout.fragment_dir / "other.yml").write_text("repos:\n  - repo: local\n    hooks:\n      - id: a\n")
    assert resolve("other.yml", layout.repo_root, layout).name == "other.yml"


def test_an_absolute_path_is_used_directly(layout: Layout) -> None:
    """An absolute reference bypasses the search order entirely."""
    target = layout.fragment_dir / "base.yaml"
    assert resolve(str(target), layout.repo_root, layout) == target


def test_a_relative_reference_resolves_against_the_referring_fragment(repo: Path, layout: Layout) -> None:
    """A project's own fragment can live outside the fragment directory."""
    (repo / "local-frag.yaml").write_text("repos:\n  - repo: local\n    hooks:\n      - id: a\n")
    assert resolve("local-frag.yaml", repo, layout) == repo / "local-frag.yaml"


def test_reports_every_candidate_when_nothing_matches(layout: Layout) -> None:
    """The error names where it looked, deduplicated but in search order."""
    with pytest.raises(FragmentError) as excinfo:
        resolve("ghost", layout.repo_root, layout)
    message = str(excinfo.value)
    assert "ghost.yaml" in message
    assert f"{DEFAULT_FRAGMENT_DIR}/ghost.yaml" in message
    # The root and the referring directory coincide here; the list must not say so twice.
    assert message.count("tried: ghost.yaml,") == 1


def test_dependencies_come_first(layout: Layout) -> None:
    """``extends`` is merged before the fragment that declares it."""
    names = [fragment.path.name for fragment in chain(["python.yaml"], layout.fragment_dir, layout)]
    assert names == ["base.yaml", "python.yaml"]


def test_a_shared_base_appears_once(repo: Path, layout: Layout) -> None:
    """Two layers extending one base do not merge it twice."""
    (layout.fragment_dir / "other.yaml").write_text("extends: [base.yaml]\noutput: rendered/other.yaml\n")
    names = [f.path.name for f in chain(["python.yaml", "other.yaml"], layout.fragment_dir, layout)]
    assert names == ["base.yaml", "python.yaml", "other.yaml"]


def test_a_cycle_terminates(repo: Path, layout: Layout) -> None:
    """Mutual ``extends`` is deduplicated rather than recursing forever."""
    (layout.fragment_dir / "a.yaml").write_text(
        "extends: [b.yaml]\nrepos:\n  - repo: local\n    hooks:\n      - id: a\n"
    )
    (layout.fragment_dir / "b.yaml").write_text(
        "extends: [a.yaml]\nrepos:\n  - repo: local\n    hooks:\n      - id: b\n"
    )
    names = [f.path.name for f in chain(["a.yaml"], layout.fragment_dir, layout)]
    assert names == ["b.yaml", "a.yaml"]


# ---------------------------------------------------------------------------
# Merging and rendering
# ---------------------------------------------------------------------------
def test_renders_a_valid_config(layout: Layout) -> None:
    """The headline case: base + layer produces a loadable config."""
    data = yaml.safe_load(render_chain(layout, "python.yaml"))
    assert [repo["repo"] for repo in data["repos"]] == [
        "https://github.com/pre-commit/pre-commit-hooks",
        "local",
        "https://github.com/astral-sh/ruff-pre-commit",
    ]


def test_the_header_names_the_chain(layout: Layout) -> None:
    """Whoever opens the generated file is sent to the fragments to edit it."""
    text = render_chain(layout, "python.yaml")
    assert "GENERATED FILE" in text
    assert f"{DEFAULT_FRAGMENT_DIR}/base.yaml, {DEFAULT_FRAGMENT_DIR}/python.yaml" in text


def test_a_later_hook_replaces_an_earlier_one_with_the_same_id(layout: Layout) -> None:
    """This is how a layer narrows a neutral hook."""
    data = yaml.safe_load(render_chain(layout, "python.yaml"))
    hooks = next(r for r in data["repos"] if r["repo"].endswith("pre-commit-hooks"))["hooks"]
    check_yaml = [hook for hook in hooks if hook["id"] == "check-yaml"]
    assert len(check_yaml) == 1
    assert check_yaml[0]["exclude"] == "^recipe/meta\\.yaml$"


def test_an_entry_without_a_rev_inherits_the_pin(layout: Layout) -> None:
    """A fragment overrides a hook without restating the version."""
    data = yaml.safe_load(render_chain(layout, "python.yaml"))
    shared = next(r for r in data["repos"] if r["repo"].endswith("pre-commit-hooks"))
    assert shared["rev"] == "v6.0.0"


def test_preamble_keys_survive_and_the_later_value_wins(repo: Path, layout: Layout) -> None:
    """Top-level keys merge by name."""
    (layout.fragment_dir / "over.yaml").write_text(
        'extends: [base.yaml]\noutput: rendered/over.yaml\n\ndefault_language_version:\n  node: "22.0.0"\n'
    )
    data = yaml.safe_load(render_chain(layout, "over.yaml"))
    assert data["default_language_version"]["node"] == "22.0.0"


def test_hook_comments_survive_the_merge(layout: Layout) -> None:
    """The whole reason the merge is textual rather than a YAML round-trip."""
    assert "# Reject .rej files" not in render_chain(layout, "python.yaml")  # a name:, not a comment
    assert "# Pin node so the npm hooks get a compatible runtime." in render_chain(layout, "python.yaml")


def test_the_entry_comment_of_a_merged_repo_is_dropped(layout: Layout) -> None:
    """Only the fragment that *introduces* a repository comments its entry.

    A later fragment's ``- repo:`` comment is fragment-local reasoning — python.yaml
    explains why it omits ``rev:`` — which would be untrue in the rendered file,
    where the inherited pin is present. Hook-level comments are unaffected; see
    :func:`~rhiza_hooks.render_precommit._absorb`.
    """
    assert "# No rev: -- the pin is base.yaml's." not in render_chain(layout, "python.yaml")


def test_a_hook_comment_from_a_later_fragment_survives(repo: Path, layout: Layout) -> None:
    """The comment that documents a *hook* is kept when the hook is spliced in."""
    (layout.fragment_dir / "annotated.yaml").write_text(
        "extends: [base.yaml]\noutput: rendered/annotated.yaml\n\n"
        "repos:\n  - repo: local\n    hooks:\n"
        "      # Why this hook exists at all.\n      - id: extra\n        name: Extra\n"
        '        entry: "true"\n        language: system\n'
    )
    assert "# Why this hook exists at all." in render_chain(layout, "annotated.yaml")


def test_meta_keys_never_reach_the_output(layout: Layout) -> None:
    """pre-commit rejects unknown top-level keys."""
    data = yaml.safe_load(render_chain(layout, "python.yaml"))
    assert not {"extends", "output", "remove"} & set(data)


def test_conflicting_revs_are_an_error(repo: Path, layout: Layout) -> None:
    """Shipping the wrong pin is worse than failing."""
    (layout.fragment_dir / "clash.yaml").write_text(
        "extends: [base.yaml]\noutput: rendered/clash.yaml\n\n"
        "repos:\n  - repo: https://github.com/pre-commit/pre-commit-hooks\n"
        "    rev: v5.0.0\n    hooks:\n      - id: check-toml\n"
    )
    with pytest.raises(FragmentError, match=r"pinned to .* but to .* by an earlier fragment"):
        render_chain(layout, "clash.yaml")


def test_a_first_rev_is_adopted_when_the_base_had_none(repo: Path, layout: Layout) -> None:
    """An unpinned entry takes the pin a later fragment supplies."""
    (layout.fragment_dir / "pin.yaml").write_text(
        "repos:\n  - repo: https://example.com/x\n    hooks:\n      - id: a\n"
        "  - repo: https://example.com/x\n    rev: v9\n    hooks:\n      - id: b\n"
    )
    assert parse_fragment(layout.fragment_dir / "pin.yaml").repos["https://example.com/x"].rev == "v9"


def test_a_rev_with_a_trailing_comment_compares_on_the_value(repo: Path, layout: Layout) -> None:
    """``rev: v1  # note`` is pinned to v1, not to ``v1  # note``."""
    (layout.fragment_dir / "commented.yaml").write_text(
        "repos:\n  - repo: https://example.com/x\n    rev: v1  # keep current\n    hooks:\n      - id: a\n"
    )
    assert parse_fragment(layout.fragment_dir / "commented.yaml").repos["https://example.com/x"].rev == "v1"


def test_a_fragment_can_remove_an_inherited_hook(repo: Path, layout: Layout) -> None:
    """``remove: hooks:`` is how a project keeps the base minus one hook."""
    (layout.fragment_dir / "drop.yaml").write_text(
        "extends: [base.yaml]\noutput: rendered/drop.yaml\n\nremove:\n  hooks: [check-toml]\n"
    )
    data = yaml.safe_load(render_chain(layout, "drop.yaml"))
    assert "check-toml" not in {h["id"] for r in data["repos"] for h in r["hooks"]}


def test_a_fragment_can_remove_an_inherited_repository(repo: Path, layout: Layout) -> None:
    """``remove: repos:`` drops the entry and everything under it."""
    (layout.fragment_dir / "droprepo.yaml").write_text(
        "extends: [base.yaml]\noutput: rendered/droprepo.yaml\n\nremove:\n  repos: [local]\n"
    )
    data = yaml.safe_load(render_chain(layout, "droprepo.yaml"))
    assert "local" not in {r["repo"] for r in data["repos"]}


def test_removing_every_hook_drops_the_repository(layout: Layout) -> None:
    """pre-commit rejects an entry with an empty ``hooks:`` list."""
    data = yaml.safe_load(render_chain(layout, "base.yaml", extra_hooks={"no-rej-files"}))
    assert "local" not in {r["repo"] for r in data["repos"]}


def test_command_line_exclusions_apply_on_top(layout: Layout) -> None:
    """``--exclude-hook`` composes with whatever the fragments declare."""
    data = yaml.safe_load(render_chain(layout, "base.yaml", extra_hooks={"check-toml"}))
    assert "check-toml" not in {h["id"] for r in data["repos"] for h in r["hooks"]}


def test_excluding_an_absent_repository_is_not_an_error(layout: Layout) -> None:
    """Removal is declarative: naming something already gone is a no-op."""
    data = yaml.safe_load(render_chain(layout, "base.yaml", extra_repos={"https://example.com/never"}))
    assert data["repos"]


def test_rejects_a_chain_that_renders_no_repos(repo: Path, layout: Layout) -> None:
    """A config with nothing in it is not worth writing."""
    (layout.fragment_dir / "bare.yaml").write_text(
        "output: rendered/bare.yaml\n\ndefault_language_version:\n  node: '1'\n"
    )
    with pytest.raises(FragmentError, match="declares no repos"):
        render_chain(layout, "bare.yaml")


def test_rejects_a_duplicate_hook_id_across_repositories(repo: Path, layout: Layout) -> None:
    """Merging by id within a repo cannot catch a collision between two."""
    (layout.fragment_dir / "dup.yaml").write_text(
        "output: rendered/dup.yaml\n\nrepos:\n"
        "  - repo: https://example.com/a\n    rev: v1\n    hooks:\n      - id: same\n"
        "  - repo: https://example.com/b\n    rev: v1\n    hooks:\n      - id: same\n"
    )
    with pytest.raises(FragmentError, match="is defined twice"):
        render_chain(layout, "dup.yaml")


def test_rejects_output_that_is_not_valid_yaml(repo: Path, layout: Layout) -> None:
    """A misindented fragment must fail here rather than render silently wrong."""
    (layout.fragment_dir / "broken.yaml").write_text(
        'output: rendered/broken.yaml\n\nrepos:\n  - repo: local\n    hooks:\n      - id: "unclosed\n'
    )
    with pytest.raises(FragmentError, match="not valid YAML"):
        render_chain(layout, "broken.yaml")


def test_rejects_a_rendered_repo_with_no_hooks(layout: Layout) -> None:
    """Assembled directly, a hookless entry must still be refused."""
    fragment = Fragment(path=layout.fragment_dir / "synthetic.yaml", output="rendered/x.yaml")
    fragment.repos["local"] = Repo(url="local", block=Block(body=["  - repo: local"]))
    with pytest.raises(FragmentError, match="declares no repos"):
        render([fragment], layout)


def test_rejects_a_meta_key_that_leaks_into_the_output(layout: Layout) -> None:
    """Defence in depth: the stripping happens at parse time, checked at render."""
    fragment = Fragment(path=layout.fragment_dir / "leak.yaml")
    fragment.preamble["output"] = Block(body=["output: rendered/leak.yaml"])
    fragment.repos["local"] = Repo(
        url="local",
        block=Block(body=["  - repo: local"]),
        hooks=[Hook("a", Block(body=["      - id: a"]))],
    )
    with pytest.raises(FragmentError, match="leaked into the rendered config"):
        render([fragment], layout)


# ---------------------------------------------------------------------------
# Discovery and planning
# ---------------------------------------------------------------------------
def test_lists_only_fragments_declaring_an_output(layout: Layout) -> None:
    """The base is a mixin and must not be rendered on its own."""
    assert [path.name for path in deployable(layout)] == ["python.yaml"]


def test_a_missing_fragment_directory_is_an_error(tmp_path: Path) -> None:
    """Said plainly, with the path, rather than rendering nothing."""
    (tmp_path / ".git").mkdir()
    with pytest.raises(FragmentError, match="no fragment directory"):
        deployable(Layout.discover(repo_root=tmp_path))


def test_resolves_the_output_relative_to_the_repository_root(layout: Layout, repo: Path) -> None:
    """``output:`` is repo-relative, not relative to the working directory."""
    [(path, _)] = plan([["python.yaml"]], None, set(), set(), layout)
    assert path == (repo / "rendered" / "python.yaml").resolve()


def test_an_explicit_out_overrides_the_declared_output(layout: Layout, repo: Path) -> None:
    """``--out`` is what makes an ad-hoc chain renderable."""
    [(path, _)] = plan([["python.yaml"]], "custom.yaml", set(), set(), layout)
    assert path == (repo / "custom.yaml").resolve()


def test_rendering_onto_an_input_fragment_is_refused(repo: Path, layout: Layout) -> None:
    """The output must not be one of its own sources.

    The merge would be idempotent, so this fails no test on its own — it is refused
    because it is one-way: the first render absorbs the other fragments into the base,
    after which deleting a fragment no longer removes its hooks.
    """
    with pytest.raises(FragmentError, match="both the output and an input fragment"):
        plan([["base.yaml", "python.yaml"]], f"{DEFAULT_FRAGMENT_DIR}/base.yaml", set(), set(), layout)


def test_a_fragment_whose_own_output_points_at_itself_is_refused(repo: Path, layout: Layout) -> None:
    """Same guard via ``output:`` rather than ``--out`` — neither route is special."""
    (layout.fragment_dir / "selfref.yaml").write_text(
        f"output: {DEFAULT_FRAGMENT_DIR}/selfref.yaml\n\nrepos:\n  - repo: local\n    hooks:\n      - id: a\n",
        encoding="utf-8",
    )
    with pytest.raises(FragmentError, match="both the output and an input fragment"):
        plan([["selfref.yaml"]], None, set(), set(), layout)


def test_rendering_beside_an_input_fragment_is_allowed(repo: Path, layout: Layout) -> None:
    """The guard is about identity, not about sharing a directory."""
    [(path, _)] = plan([["python.yaml"]], f"{DEFAULT_FRAGMENT_DIR}/rendered.yaml", set(), set(), layout)
    assert path == (repo / DEFAULT_FRAGMENT_DIR / "rendered.yaml").resolve()


def test_the_self_reference_guard_reports_through_the_cli(repo: Path, monkeypatch, capsys) -> None:
    """It reaches the user as an error message and exit 1, not a traceback."""
    monkeypatch.chdir(repo)
    assert main(["base.yaml", "--out", f"{DEFAULT_FRAGMENT_DIR}/base.yaml", "--write"]) == 1
    assert "both the output and an input fragment" in capsys.readouterr().err


def test_a_chain_with_no_destination_is_an_error(layout: Layout) -> None:
    """A mixin rendered on its own has nowhere to go."""
    with pytest.raises(FragmentError, match="declares no output"):
        plan([["base.yaml"]], None, set(), set(), layout)


def test_a_rev_after_another_meta_line_is_still_found(repo: Path) -> None:
    """``rev:`` need not be the first line under ``- repo:``."""
    path = repo / "revlate.yaml"
    path.write_text("repos:\n  - repo: https://example.com/x\n    # note\n    rev: v3\n    hooks:\n      - id: a\n")
    assert parse_fragment(path).repos["https://example.com/x"].rev == "v3"


def test_an_entry_with_neither_hooks_nor_trailing_renders_bare(layout: Layout) -> None:
    """``Repo.render`` stops before emitting an empty ``hooks:`` key."""
    entry = Repo(url="local", block=Block(body=["  - repo: local"]))
    assert entry.render() == ["  - repo: local"]


def test_a_blank_line_before_the_first_item_is_absorbed(repo: Path) -> None:
    """Leading blank lines belong to no item and must not crash the splitter."""
    path = repo / "leadblank.yaml"
    path.write_text("repos:\n\n  - repo: local\n    hooks:\n      - id: a\n")
    assert list(parse_fragment(path).repos) == ["local"]


def test_a_stray_line_before_the_first_item_is_discarded(repo: Path) -> None:
    """A non-comment line under ``repos:`` but above any entry belongs to nothing."""
    path = repo / "stray.yaml"
    path.write_text("repos:\n  stray: value\n  - repo: local\n    hooks:\n      - id: a\n")
    assert list(parse_fragment(path).repos) == ["local"]


def test_a_repos_key_with_no_entries_yields_nothing(repo: Path) -> None:
    """An empty ``repos:`` parses to no entries rather than erroring here."""
    path = repo / "norepos.yaml"
    path.write_text("output: out.yaml\nrepos:\n")
    assert parse_fragment(path).repos == {}


def test_identical_revs_in_two_fragments_are_not_a_conflict(repo: Path) -> None:
    """Only a *contradiction* is refused; agreeing pins merge quietly."""
    path = repo / "agree.yaml"
    path.write_text(
        "repos:\n  - repo: https://example.com/x\n    rev: v1\n    hooks:\n      - id: a\n"
        "  - repo: https://example.com/x\n    rev: v1\n    hooks:\n      - id: b\n"
    )
    entry = parse_fragment(path).repos["https://example.com/x"]
    assert entry.rev == "v1"
    assert [hook.hook_id for hook in entry.hooks] == ["a", "b"]


def test_validate_rejects_a_repo_whose_hooks_key_is_empty() -> None:
    """The guard against a bad merge, exercised directly.

    ``merge`` drops a hookless entry before this runs, so the only way to reach the
    check is to hand it the text such a bug would produce — which is the point of
    keeping it: it is a backstop, not a user-facing error.
    """
    with pytest.raises(FragmentError, match="has no hooks"):
        rp._validate("repos:\n  - repo: local\n    hooks:\n", Path("synthetic.yaml"))


def test_merge_is_pure(layout: Layout) -> None:
    """Merging twice yields the same result: fragments are copied, not mutated."""
    fragments = chain(["python.yaml"], layout.fragment_dir, layout)
    first = merge(fragments, set(), set())[1]["https://github.com/pre-commit/pre-commit-hooks"].hooks
    second = merge(fragments, set(), set())[1]["https://github.com/pre-commit/pre-commit-hooks"].hooks
    assert [hook.hook_id for hook in first] == [hook.hook_id for hook in second]


def test_header_names_a_fragment_outside_the_repository(layout: Layout, tmp_path: Path) -> None:
    """An out-of-tree fragment is named in full rather than crashing.

    ``as_posix()``, not ``str()``: there is no repo-relative form to shorten to, but the
    header still spells it with forward slashes so the rendered bytes do not depend on
    the platform that produced them.
    """
    outside = (tmp_path.parent / "outside.yaml").resolve()
    assert outside.as_posix() in "\n".join(header([Fragment(path=outside)], layout))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def test_checking_is_the_default_and_writes_nothing(repo: Path, monkeypatch, capsys) -> None:
    """The property that makes this safe to publish as a pre-commit hook."""
    monkeypatch.chdir(repo)
    assert main([]) == 1
    assert not (repo / "rendered").exists()
    assert "STALE" in capsys.readouterr().err


def test_write_renders_the_declared_outputs(repo: Path, monkeypatch, capsys) -> None:
    """``--write`` creates the file and any missing parent directories."""
    monkeypatch.chdir(repo)
    assert main(["--write"]) == 0
    assert (repo / "rendered" / "python.yaml").is_file()
    assert "written" in capsys.readouterr().out


def test_a_second_check_after_writing_is_clean(repo: Path, monkeypatch, capsys) -> None:
    """Render then check is the round trip a CI drift guard depends on."""
    monkeypatch.chdir(repo)
    main(["--write"])
    capsys.readouterr()
    assert main([]) == 0
    assert "ok" in capsys.readouterr().out


def test_reports_a_diff_for_a_stale_file(repo: Path, monkeypatch, capsys) -> None:
    """Drift is shown, not merely announced."""
    monkeypatch.chdir(repo)
    main(["--write"])
    (repo / "rendered" / "python.yaml").write_text("repos: []\n", encoding="utf-8")
    capsys.readouterr()
    assert main([]) == 1
    err = capsys.readouterr().err
    assert "--- rendered/python.yaml (on disk)" in err
    assert "out of date" in err


def test_an_explicit_chain_with_out(repo: Path, monkeypatch) -> None:
    """Composing a chain ad hoc, without giving it a fragment of its own."""
    monkeypatch.chdir(repo)
    assert main(["base.yaml", "python.yaml", "--out", "adhoc.yaml", "--write"]) == 0
    assert (repo / "adhoc.yaml").is_file()


def test_exclusions_reach_the_render(repo: Path, monkeypatch) -> None:
    """``--exclude-hook`` and ``--exclude-repo`` are plumbed through."""
    monkeypatch.chdir(repo)
    main(["python.yaml", "--out", "x.yaml", "--exclude-hook", "ruff", "--write"])
    data = yaml.safe_load((repo / "x.yaml").read_text(encoding="utf-8"))
    assert "ruff" not in {hook["id"] for entry in data["repos"] for hook in entry["hooks"]}


def test_a_fragment_error_is_reported_not_raised(repo: Path, monkeypatch, capsys) -> None:
    """The CLI turns engine errors into an exit code and a message."""
    monkeypatch.chdir(repo)
    assert main(["ghost.yaml"]) == 1
    assert "error: no fragment" in capsys.readouterr().err


def test_an_empty_fragment_directory_is_reported(tmp_path: Path, monkeypatch, capsys) -> None:
    """No fragment declaring an output means there is nothing to do, loudly."""
    (tmp_path / ".git").mkdir()
    (tmp_path / DEFAULT_FRAGMENT_DIR).mkdir()
    monkeypatch.chdir(tmp_path)
    assert main([]) == 1
    assert "declares an output" in capsys.readouterr().err


def test_an_unreadable_fragment_is_reported(repo: Path, monkeypatch, capsys) -> None:
    """OSError is caught alongside FragmentError; a directory stands in."""
    monkeypatch.chdir(repo)
    (repo / DEFAULT_FRAGMENT_DIR / "dir.yaml").mkdir()
    assert main([]) == 1
    assert "error:" in capsys.readouterr().err


def test_module_executes_main(repo: Path, monkeypatch) -> None:
    """``python -m rhiza_hooks.render_precommit`` runs the same entry point."""
    monkeypatch.chdir(repo)
    monkeypatch.setattr(rp.sys, "argv", ["render_precommit", "--write"])
    # Already imported at module scope, so runpy warns about sys.modules; filter that
    # one warning rather than mutating sys.modules, which would break module identity.
    with (
        patch("rhiza_hooks.render_precommit.sys.exit") as mock_exit,
        warnings.catch_warnings(),
    ):
        warnings.filterwarnings("ignore", message=r".*found in sys\.modules.*", category=RuntimeWarning)
        runpy.run_module("rhiza_hooks.render_precommit", run_name="__main__")
    mock_exit.assert_called_once_with(0)


def test_a_repo_with_no_fragment_directory_passes(tmp_path: Path, monkeypatch, capsys) -> None:
    """A repo that renders nothing is reported, not failed.

    Most repositories have no ``pre-commit/`` directory, and a shared build step or CI
    job may call this across all of them; for those there is nothing to check and the
    run must say so and succeed rather than failing on a missing directory.
    """
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    assert main([]) == 0
    assert "nothing to render" in capsys.readouterr().out


def test_an_explicit_missing_fragment_directory_still_fails(tmp_path: Path, monkeypatch, capsys) -> None:
    """``--fragment-dir`` asserts fragments live there; a missing one is an error."""
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    assert main(["--fragment-dir", "nowhere"]) == 1
    assert "no fragment directory" in capsys.readouterr().err


def test_fragment_dir_option_is_honoured(tmp_path: Path, monkeypatch) -> None:
    """A project may keep its fragments somewhere other than pre-commit/."""
    (tmp_path / ".git").mkdir()
    elsewhere = tmp_path / "config" / "fragments"
    elsewhere.mkdir(parents=True)
    (elsewhere / "solo.yaml").write_text(
        "output: out.yaml\n\nrepos:\n  - repo: local\n    hooks:\n      - id: a\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    assert main(["--fragment-dir", "config/fragments", "--write"]) == 0
    assert (tmp_path / "out.yaml").is_file()
