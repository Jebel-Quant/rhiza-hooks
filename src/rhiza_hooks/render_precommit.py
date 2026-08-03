#!/usr/bin/env python3
r"""Render a ``.pre-commit-config.yaml`` by concatenating and deduplicating fragments.

pre-commit hard-codes the config filename, so a template repository that ships several
language layers (``python-core``, ``rust-core``, ``go-core``) has them all claim the
same path: the layers are alternatives rather than files that coexist. The neutral
hooks -- markdownlint, actionlint, schema validation, secret scanning, the rhiza hooks
-- are therefore duplicated across every layer, and that duplication is maintained by
hand.

This module inverts it. One fragment holds the neutral hooks once, each other fragment
holds only what it adds, and a deployed config is *rendered* from a chain of fragments.
A rev bump in the base reaches every layer through one edit.

It lives in ``rhiza-hooks`` rather than in the template repository so that the
capability travels: the fragment format supports a project keeping its own fragment
anywhere and extending the shipped ones, which is worth nothing if the renderer is only
present in the template's own checkout. Installed here it is versioned, pinnable, and
reachable from any consuming repo.

Composition is declared by the fragments themselves -- there is no separate manifest,
and nothing about the set of fragments is hard-coded here. A fragment may set three
meta keys, all stripped from the rendered output (none of them is a real pre-commit
key, so a fragment stays readable as a config):

``extends``
    Fragment names or paths merged *before* this one, resolved recursively and
    deduplicated. A bare name resolves inside the fragment directory, so a project can
    keep its own fragment anywhere and still extend the shipped ones.
``output``
    Where the rendered config is written, relative to the repository root. A fragment
    with no ``output`` is a mixin: it is never rendered on its own, only pulled in by
    something that extends it. That is what makes a base fragment a base.
``remove``
    ``hooks:`` and/or ``repos:`` lists naming what to drop from what came before --
    how a project keeps the shared base but opts out of one of its hooks. Removals
    apply after the whole chain has merged, so a fragment can remove a hook that a
    later fragment in the chain would otherwise reintroduce.

Merge rules, in the order the merge applies them:

* Top-level keys other than ``repos`` (e.g. ``default_language_version``) merge by key
  name; the later fragment's value wins.
* ``repos`` entries merge by repository URL, keeping the earlier order and appending
  each fragment's new repositories. ``repo: local`` collapses to a single entry.
* Within a shared repository, hooks merge by ``id``; a later hook with an id an
  earlier fragment also defines replaces it, which is how a fragment narrows a
  neutral hook. A later entry may omit ``rev:`` to inherit the pin, and a ``rev:``
  that contradicts an earlier one is an error rather than a silent pick -- shipping
  the wrong pin is worse than failing.

The merge is textual, splicing comment-plus-body blocks rather than round-tripping
through a YAML parser, because the explanatory comments on these hooks carry as much
of the reasoning as the hooks do and no YAML emitter preserves them faithfully. The
rendered result is parsed and checked for duplicate hook ids before it is written.

**This is a console script, not a pre-commit hook**, and deliberately so. pre-commit
reads ``.pre-commit-config.yaml`` once, before any hook executes, so a hook that
rendered it could only ever affect the *next* invocation while changing the file under
the current one. Rendering belongs in the build step that runs *ahead* of pre-commit —
which is where the ordering can actually be guaranteed.

**Checking is the default; rendering requires ``--write``.** A tool invoked in a
repository should not rewrite tracked files unless it was asked to: the check mode is
the one safe to run anywhere, including from a CI drift guard, and ``--write`` is the
explicit request. It also means a bare invocation in the wrong directory reports rather
than edits.

Exit codes:
  0 - every rendered config matches what is on disk (or was written, with --write)
  1 - drift found under the default check, or a fragment could not be merged
"""

from __future__ import annotations

import argparse
import difflib
import sys
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from rhiza_hooks._repo import find_repo_root

#: Where fragments live, relative to the repository root, unless --fragment-dir says
#: otherwise. A directory rather than a manifest: the fragments declare their own
#: composition, so the only thing left to locate is the fragments themselves.
DEFAULT_FRAGMENT_DIR = "pre-commit"

#: Meta keys a fragment may set. Stripped from the rendered config: none of them is a
#: pre-commit key, and pre-commit rejects unknown top-level keys.
META_KEYS = ("extends", "output", "remove")

#: The indentation the fragments use, fixed rather than inferred so a misindented
#: fragment fails loudly here instead of rendering a subtly wrong config.
REPO_MARKER = "  - repo:"
REV_KEY = "    rev:"
HOOKS_KEY = "    hooks:"
HOOK_MARKER = "      - id:"


class FragmentError(RuntimeError):
    """A fragment could not be parsed, or two fragments disagree irreconcilably."""


@dataclass(frozen=True)
class Layout:
    """Where a run reads fragments from and writes rendered configs to.

    Bundling the two paths keeps them out of module-level state. The renderer used to
    derive both from its own ``__file__``, which is right for a script vendored into
    the repository it renders and wrong for an installed console script, where
    ``__file__`` points into site-packages.

    Attributes:
        repo_root: Repository root. ``output:`` paths resolve against it.
        fragment_dir: Directory holding the fragments.
    """

    repo_root: Path
    fragment_dir: Path

    @classmethod
    def discover(cls, repo_root: Path | None = None, fragment_dir: str = DEFAULT_FRAGMENT_DIR) -> Layout:
        """Build a layout, locating the repository root when it is not given.

        Args:
            repo_root: Repository root; discovered from the working directory when None.
            fragment_dir: Fragment directory, absolute or relative to the root.

        Returns:
            The resolved layout.
        """
        root = (repo_root or find_repo_root()).resolve()
        directory = Path(fragment_dir)
        return cls(repo_root=root, fragment_dir=directory if directory.is_absolute() else root / directory)

    def display(self, path: Path) -> str:
        """Return a path for display, repo-relative where possible, always POSIX.

        Forward slashes are not cosmetic here. :func:`header` embeds these strings *in
        the rendered file*, so returning the platform form would make the same
        fragments render different bytes on Windows and on Linux -- and the drift check
        would then fail on whichever platform did not render last. Same reasoning as
        pinning ``newline=""`` on the write: output must be a function of its input
        alone.

        Args:
            path: The path to shorten.

        Returns:
            The repo-relative POSIX path, or the full POSIX path if it lies outside
            the repository.
        """
        relative = path.relative_to(self.repo_root) if path.is_relative_to(self.repo_root) else path
        return relative.as_posix()


@dataclass
class Block:
    """A run of comment lines followed by the body lines they document.

    Attributes:
        comments: Comment lines preceding the body, verbatim.
        body: The body lines, verbatim. Empty for a comment-only block, which is how
            a commented-out hook survives the merge.
        spaced: Whether the source separated this block from the previous one by a
            blank line. Preserved so the rendered file keeps the fragments' own
            grouping instead of a uniform spacing this repo does not use.
    """

    comments: list[str] = field(default_factory=list)
    body: list[str] = field(default_factory=list)
    spaced: bool = False

    def render(self) -> list[str]:
        """Return the block's lines, comments first.

        Returns:
            The comment lines followed by the body lines.
        """
        return [*self.comments, *self.body]


@dataclass
class Hook:
    """One ``- id: <name>`` item inside a repository's ``hooks:`` list.

    Attributes:
        hook_id: The hook's ``id`` -- the key the merge deduplicates on.
        block: The hook's comments and body lines.
    """

    hook_id: str
    block: Block


@dataclass
class Repo:
    """One ``- repo: <url>`` entry of the ``repos:`` list.

    Attributes:
        url: The repository URL, or ``local``. The key the merge deduplicates on.
        block: The entry's leading comments and the ``- repo:`` line itself.
        meta: The lines between ``- repo:`` and ``hooks:`` -- ``rev:`` and any comment
            attached to it. Empty for ``repo: local``.
        hooks: The repository's hooks, in merge order.
        trailing: Comment-only blocks after the last hook, e.g. a hook deliberately
            commented out with the reasoning kept beside it.
    """

    url: str
    block: Block
    meta: list[str] = field(default_factory=list)
    hooks: list[Hook] = field(default_factory=list)
    trailing: list[Block] = field(default_factory=list)

    @property
    def rev(self) -> str | None:
        """The entry's pinned rev, ignoring any trailing comment on it.

        Returns:
            The rev, or None for ``repo: local`` and any entry that omits it.
        """
        for line in self.meta:
            if line.startswith(REV_KEY):
                return line.split(":", 1)[1].split("#", 1)[0].strip()
        return None

    def copy(self) -> Repo:
        """Copy the entry so merging never mutates a parsed fragment.

        Returns:
            A copy whose mutable members are independent of the original.
        """
        return Repo(self.url, self.block, list(self.meta), list(self.hooks), list(self.trailing))

    def render(self) -> list[str]:
        """Return the entry's lines, ready to append to a ``repos:`` list.

        Returns:
            The comments, ``- repo:`` line, ``rev:`` lines, ``hooks:`` key and every
            hook block, blank-separated exactly as the fragments were.
        """
        lines = [*self.block.render(), *self.meta]
        if not self.hooks and not self.trailing:
            return lines
        lines.append(HOOKS_KEY)
        for index, block in enumerate([hook.block for hook in self.hooks] + self.trailing):
            if block.spaced and index:
                lines.append("")
            lines.extend(block.render())
        return lines


@dataclass
class Fragment:
    """A parsed fragment.

    Attributes:
        path: Where the fragment was read from, used for error messages and to
            resolve its relative ``extends`` entries.
        preamble: Top-level blocks other than ``repos`` and the meta keys, keyed by
            key name so a later fragment can override one.
        repos: The ``repos:`` entries, keyed by URL, in source order.
        extends: Fragment references merged before this one.
        output: Where this fragment's rendered config is deployed, or None if it is
            a mixin.
        remove_hooks: Hook ids to drop from the merged result.
        remove_repos: Repository URLs to drop from the merged result.
    """

    path: Path
    preamble: dict[str, Block] = field(default_factory=dict)
    repos: dict[str, Repo] = field(default_factory=dict)
    extends: list[str] = field(default_factory=list)
    output: str | None = None
    remove_hooks: set[str] = field(default_factory=set)
    remove_repos: set[str] = field(default_factory=set)


def _is_comment(line: str) -> bool:
    """Report whether a line is a comment or blank.

    Args:
        line: The line to classify.

    Returns:
        True for comment and blank lines, which attach to the block that follows.
    """
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


def _split_items(lines: list[str], marker: str) -> tuple[list[tuple[str, Block]], list[Block]]:
    """Split a YAML sequence into its items, keeping each item's comments with it.

    A comment run is ambiguous -- it may document the item above or the one below --
    so it is buffered until the next non-comment line decides: a new item claims it,
    anything else folds it back into the item in progress.

    A blank line is ambiguous the same way, and additionally may belong to a *nested*
    sequence: the blank line between two hooks reaches this function while it is
    splitting repositories, one level up. So a blank line is kept in the item in
    progress -- where a recursive call can still see it -- and only recognised as a
    separator when the next item at this level starts, which is when it is stripped.

    Args:
        lines: The sequence's lines, i.e. everything under its key.
        marker: The line prefix that starts an item (``  - repo:`` or ``      - id:``).

    Returns:
        A ``(items, trailing)`` pair. Each item is a ``(value, block)`` pair, where
        the value is the text after the marker's colon. ``trailing`` holds a
        comment-only block that closed the sequence.
    """
    items: list[tuple[str, Block]] = []
    pending: list[str] = []
    spaced = False
    for line in lines:
        if line.startswith(marker):
            if items:
                items[-1][1].body[:] = _rstrip(items[-1][1].body)
            items.append((line.split(":", 1)[1].strip(), Block(pending, [line], spaced)))
            pending, spaced = [], False
        elif not line.strip():
            if items and not pending:
                items[-1][1].body.append(line)
            spaced = True
        elif line.strip().startswith("#"):
            pending.append(line)
        else:
            if items:
                items[-1][1].body.extend([*pending, line])
            pending, spaced = [], False
    if items:
        items[-1][1].body[:] = _rstrip(items[-1][1].body)
    trailing = [Block(comments=pending, spaced=spaced)] if pending else []
    return items, trailing


def _rstrip(lines: list[str]) -> list[str]:
    """Drop trailing blank lines from a block of lines.

    Args:
        lines: The lines to trim.

    Returns:
        The lines without their trailing blanks. Blank lines *inside* the block are
        kept: they carry the fragment's grouping, which the rendered file preserves.
    """
    end = len(lines)
    while end and not lines[end - 1].strip():
        end -= 1
    return lines[:end]


def _key_comments(lines: list[str], start: int, previous: int) -> list[str]:
    """Collect the comment lines that document a top-level key.

    A comment run directly above a key belongs to it. The exception is the first key:
    the run above it opens the file, and part of it is the file header, which the
    rendered config replaces with a generated one. A blank line separates the two --
    everything after the last blank line before the first key documents that key, and
    a run with no blank line in it is all header.

    Args:
        lines: The fragment's lines.
        start: The index of the key's line.
        previous: The index of the previous key's line, or 0 for the first key.

    Returns:
        The comment lines belonging to the key, verbatim.
    """
    head = lines[previous:start]
    if not previous:
        blanks = [index for index, line in enumerate(head) if not line.strip()]
        head = head[blanks[-1] + 1 :] if blanks else []
    return [line for line in head if line.strip().startswith("#")]


def _parse_repo(value: str, block: Block, path: Path) -> Repo:
    """Build a repository entry from its raw block.

    Args:
        value: The text after ``- repo:`` -- the URL, or ``local``.
        block: The entry's comments and lines.
        path: The fragment being parsed, for error messages.

    Returns:
        The parsed entry.

    Raises:
        FragmentError: If the entry names no repository or declares ``hooks:`` twice.
    """
    if not value:
        msg = f"{path}: repo entry with no URL: {block.body[0]!r}"
        raise FragmentError(msg)
    repo = Repo(url=value, block=Block(block.comments, block.body[:1], block.spaced))
    rest = block.body[1:]
    if HOOKS_KEY not in rest:
        repo.meta = rest
        return repo
    split = rest.index(HOOKS_KEY)
    if HOOKS_KEY in rest[split + 1 :]:
        msg = f"{path}: repo {value} declares hooks: more than once"
        raise FragmentError(msg)
    repo.meta = rest[:split]
    hooks, repo.trailing = _split_items(rest[split + 1 :], HOOK_MARKER)
    for hook_id, hook_block in hooks:
        if not hook_id:
            msg = f"{path}: hook with an empty id in {value}"
            raise FragmentError(msg)
        repo.hooks.append(Hook(hook_id, hook_block))
    return repo


def _parse_repos(lines: list[str], path: Path) -> dict[str, Repo]:
    """Parse the body of the top-level ``repos:`` key.

    Args:
        lines: The lines under ``repos:``.
        path: The fragment being parsed, for error messages.

    Returns:
        The entries keyed by URL, in source order. Several ``repo: local`` entries in
        one fragment collapse into a single entry with their hooks concatenated.

    Raises:
        FragmentError: If an entry is malformed or two entries for one URL disagree
            on their ``rev:``.
    """
    items, trailing = _split_items(lines, REPO_MARKER)
    repos: dict[str, Repo] = {}
    for value, block in items:
        repo = _parse_repo(value, block, path)
        if repo.url in repos:
            _absorb(repos[repo.url], repo, path)
        else:
            repos[repo.url] = repo
    if trailing and repos:
        list(repos.values())[-1].trailing.extend(trailing)
    return repos


def _absorb(target: Repo, extra: Repo, path: Path) -> None:
    """Merge one repository entry into an earlier entry for the same URL.

    Args:
        target: The entry to keep, mutated in place.
        extra: The entry folded in. Its hooks override ``target``'s on an id
            collision; a missing ``rev:`` inherits target's, which is how a fragment
            overrides a hook without restating the pin.
        path: The fragment being merged, for error messages.

    Raises:
        FragmentError: If both entries pin a ``rev:`` and the pins differ.

    Note:
        ``extra``'s *entry-level* comments are dropped -- only the first fragment to
        introduce a repository contributes the comment above its ``- repo:`` line.
        Hook-level comments always survive. This is deliberate rather than an
        oversight: an entry that merges into an existing one typically carries
        fragment-local reasoning ("no rev: here, the pin is the base's"), which is
        false in the rendered file, where the inherited pin is present.
    """
    if (extra_rev := extra.rev) is not None:
        if (target_rev := target.rev) is None:
            target.meta = extra.meta
        elif target_rev != extra_rev:
            msg = (
                f"{path}: {target.url} is pinned to {extra_rev} here but to {target_rev} "
                f"by an earlier fragment. Bump the pin in one place, or drop the rev: "
                f"to inherit it."
            )
            raise FragmentError(msg)
    by_id = {hook.hook_id: index for index, hook in enumerate(target.hooks)}
    for hook in extra.hooks:
        block = hook.block
        if (index := by_id.get(hook.hook_id)) is not None:
            # An override keeps the layout of the hook it replaces, so narrowing a
            # hook does not reshuffle the file around it.
            target.hooks[index] = Hook(
                hook.hook_id, Block(block.comments, block.body, target.hooks[index].block.spaced)
            )
        else:
            # A blank line marks where another fragment's hooks were spliced in --
            # the rendered file is read by humans, and two fragments' hooks run
            # together read as one group otherwise.
            target.hooks.append(Hook(hook.hook_id, Block(block.comments, block.body, spaced=True)))
    target.trailing.extend(extra.trailing)


def _meta(block: Block, path: Path) -> object:
    """Parse a meta key's block back into Python data.

    Args:
        block: The block holding the key and its value.
        path: The fragment being parsed, for error messages.

    Returns:
        The key's value.

    Raises:
        FragmentError: If the block is not valid YAML.
    """
    try:
        loaded = yaml.safe_load("\n".join(block.body))
    except yaml.YAMLError as exc:
        msg = f"{path}: cannot parse {block.body[0]!r}: {exc}"
        raise FragmentError(msg) from exc
    if not isinstance(loaded, dict):  # pragma: no cover - a block always opens with `<key>:`
        return None
    return next(iter(loaded.values()))


def parse_fragment(path: Path) -> Fragment:
    """Parse a fragment file into its meta keys, preamble blocks and repositories.

    Args:
        path: The fragment to read.

    Returns:
        The parsed fragment.

    Raises:
        FragmentError: If the file has no top-level keys, or a meta key has the wrong
            shape.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [index for index, line in enumerate(lines) if line and not line[0].isspace() and not _is_comment(line)]
    if not starts:
        msg = f"{path}: no top-level keys found"
        raise FragmentError(msg)
    fragment = Fragment(path=path)
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        block = Block(
            comments=_key_comments(lines, start, starts[index - 1] if index else 0),
            body=_rstrip(lines[start:end]),
        )
        key = lines[start].split(":", 1)[0].strip()
        if key in META_KEYS:
            _apply_meta(fragment, key, _meta(block, path), path)
        elif key == "repos":
            fragment.repos = _parse_repos(block.body[1:], path)
        else:
            fragment.preamble[key] = block
    return fragment


def _apply_meta(fragment: Fragment, key: str, value: object, path: Path) -> None:
    """Store one meta key on a fragment, validating its shape.

    Args:
        fragment: The fragment being built, mutated in place.
        key: The meta key name, one of ``META_KEYS``.
        value: The key's parsed value.
        path: The fragment being parsed, for error messages.

    Raises:
        FragmentError: If the value has the wrong type, or ``remove`` names a section
            other than ``hooks``/``repos``.
    """
    if key == "output":
        if not isinstance(value, str):
            msg = f"{path}: output: must be a path string"
            raise FragmentError(msg)
        fragment.output = value
    elif key == "extends":
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            msg = f"{path}: extends: must be a list of fragment names or paths"
            raise FragmentError(msg)
        fragment.extends = value
    else:
        if not isinstance(value, dict) or set(value) - {"hooks", "repos"}:
            msg = f"{path}: remove: must be a mapping with keys hooks and/or repos"
            raise FragmentError(msg)
        fragment.remove_hooks = set(value.get("hooks") or [])
        fragment.remove_repos = set(value.get("repos") or [])


def resolve(reference: str, relative_to: Path, layout: Layout) -> Path:
    """Resolve a fragment reference to a path.

    Args:
        reference: A bare name (``python`` or ``python.yaml``), resolved inside the
            fragment directory, or a path, resolved against the referring fragment's
            directory and then the repository root.
        relative_to: The directory of the fragment doing the referring.
        layout: Where the repository root and fragment directory are.

    Returns:
        The resolved path.

    Raises:
        FragmentError: If no candidate exists.
    """
    name = reference if reference.endswith((".yaml", ".yml")) else f"{reference}.yaml"
    candidates = (
        [Path(name)]
        if Path(name).is_absolute()
        else [relative_to / name, layout.repo_root / name, layout.fragment_dir / name]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    # dict.fromkeys, not set(): the candidates collapse to one entry when the referring
    # fragment sits at the repository root, and the order they were tried in is the
    # useful part of the message.
    tried = ", ".join(dict.fromkeys(layout.display(candidate) for candidate in candidates))
    msg = f"no fragment {reference!r} (tried: {tried})"
    raise FragmentError(msg)


def chain(references: list[str], relative_to: Path, layout: Layout, seen: list[Path] | None = None) -> list[Fragment]:
    """Expand fragment references into the flat, deduplicated list to merge.

    Args:
        references: The fragment references, in merge order.
        relative_to: The directory references are resolved against first.
        layout: Where the repository root and fragment directory are.
        seen: Paths already in the chain, threaded through the recursion to
            deduplicate a shared base and to catch a cycle.

    Returns:
        The fragments in merge order, each appearing once, dependencies first.

    Raises:
        FragmentError: If a reference cannot be resolved or ``extends`` forms a cycle.
    """
    seen = [] if seen is None else seen
    result: list[Fragment] = []
    for reference in references:
        path = resolve(reference, relative_to, layout)
        if path in seen:
            continue
        seen.append(path)
        fragment = parse_fragment(path)
        result.extend(chain(fragment.extends, path.parent, layout, seen))
        result.append(fragment)
    return result


def merge(
    fragments: list[Fragment], extra_hooks: set[str], extra_repos: set[str]
) -> tuple[dict[str, Block], dict[str, Repo]]:
    """Merge a chain of fragments into one config's blocks.

    Args:
        fragments: The fragments, in merge order.
        extra_hooks: Hook ids to remove on top of what the fragments declare.
        extra_repos: Repository URLs to remove on top of what the fragments declare.

    Returns:
        A ``(preamble, repos)`` pair holding the merged blocks in output order, with
        every removal applied.

    Raises:
        FragmentError: If two fragments pin one repository to different revs.
    """
    preamble: dict[str, Block] = {}
    repos: dict[str, Repo] = {}
    drop_hooks = set(extra_hooks)
    drop_repos = set(extra_repos)
    for fragment in fragments:
        preamble.update(fragment.preamble)
        drop_hooks |= fragment.remove_hooks
        drop_repos |= fragment.remove_repos
        for url, repo in fragment.repos.items():
            if url in repos:
                _absorb(repos[url], repo, fragment.path)
            else:
                repos[url] = repo.copy()
    for url in drop_repos:
        repos.pop(url, None)
    for repo in repos.values():
        repo.hooks = [hook for hook in repo.hooks if hook.hook_id not in drop_hooks]
    # A repository whose every hook was removed would emit an entry with an empty
    # hooks: list, which pre-commit rejects.
    return preamble, {url: repo for url, repo in repos.items() if repo.hooks}


def header(fragments: list[Fragment], layout: Layout) -> list[str]:
    """Build the rendered file's header comment.

    Args:
        fragments: The chain the file was rendered from, in merge order.
        layout: Where the repository root is, so fragments are named relative to it.

    Returns:
        The header lines, naming the fragments so whoever opens the deployed config
        is sent to the right place to edit it.
    """
    names = ", ".join(layout.display(fragment.path) for fragment in fragments)
    return [
        "# GENERATED FILE - do not edit. Rendered by rhiza-hooks (render-precommit)",
        f"# from {names}.",
        "# Edit a fragment and re-render.",
        "#",
        "# pre-commit hard-codes this path, so the language layers that deploy it are",
        "# alternatives rather than files that could coexist.",
    ]


def render(
    fragments: list[Fragment],
    layout: Layout,
    # AbstractSet, not set: these are read-only here (merge copies them), and a
    # mutable default would be a shared-state bug waiting to happen.
    extra_hooks: AbstractSet[str] = frozenset(),
    extra_repos: AbstractSet[str] = frozenset(),
) -> str:
    """Render a chain of fragments into a complete ``.pre-commit-config.yaml``.

    Args:
        fragments: The fragments, in merge order.
        layout: Where the repository root is.
        extra_hooks: Hook ids to remove on top of what the fragments declare.
        extra_repos: Repository URLs to remove on top of what the fragments declare.

    Returns:
        The file's full text, newline-terminated.

    Raises:
        FragmentError: If the merge conflicts, or the result is not a valid config.
    """
    preamble, repos = merge(fragments, set(extra_hooks), set(extra_repos))
    lines = header(fragments, layout)
    for block in preamble.values():
        lines.extend(["", *block.render()])
    lines.extend(["", "repos:"])
    for index, repo in enumerate(repos.values()):
        if index:
            lines.append("")
        lines.extend(repo.render())
    text = "\n".join(lines) + "\n"
    _validate(text, fragments[-1].path)
    return text


def _validate(text: str, path: Path) -> None:
    """Check that rendered output is a usable pre-commit config.

    Args:
        text: The rendered file.
        path: The fragment the chain ends with, for error messages.

    Raises:
        FragmentError: If the text is not valid YAML, declares no ``repos``, or
            defines the same hook id twice -- the failure a bad merge would produce.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        msg = f"{path}: rendered config is not valid YAML: {exc}"
        raise FragmentError(msg) from exc
    if not isinstance(data, dict) or not data.get("repos"):
        msg = f"{path}: rendered config declares no repos"
        raise FragmentError(msg)
    if unknown := set(data) & set(META_KEYS):
        msg = f"{path}: meta key(s) {sorted(unknown)} leaked into the rendered config"
        raise FragmentError(msg)
    seen: dict[str, str] = {}
    for repo in data["repos"]:
        if not repo.get("hooks"):
            msg = f"{path}: rendered repo {repo['repo']} has no hooks"
            raise FragmentError(msg)
        for hook in repo["hooks"]:
            if (owner := seen.get(hook["id"])) is not None:
                msg = f"{path}: hook id {hook['id']!r} is defined twice, by {owner} and {repo['repo']}"
                raise FragmentError(msg)
            seen[hook["id"]] = repo["repo"]


def deployable(layout: Layout) -> list[Path]:
    """List the fragments that declare an output, i.e. those rendered by default.

    Args:
        layout: Where the fragment directory is.

    Returns:
        The fragment paths, sorted. A fragment with no ``output`` is a mixin and is
        skipped -- it is only ever pulled in via ``extends``.

    Raises:
        FragmentError: If the fragment directory is missing.
    """
    if not layout.fragment_dir.is_dir():
        msg = f"no fragment directory at {layout.display(layout.fragment_dir)}"
        raise FragmentError(msg)
    return sorted(path for path in layout.fragment_dir.glob("*.y*ml") if parse_fragment(path).output)


def plan(
    targets: list[list[str]], out: str | None, hooks: set[str], repos: set[str], layout: Layout
) -> list[tuple[Path, str]]:
    """Render every target chain, resolving where each result is deployed.

    Args:
        targets: Fragment reference lists, one per config to render.
        out: An explicit destination overriding the chain's ``output:``.
        hooks: Hook ids to remove on top of what the fragments declare.
        repos: Repository URLs to remove on top of what the fragments declare.
        layout: Where the repository root and fragment directory are.

    Returns:
        The ``(path, text)`` pairs to write, in target order.

    Raises:
        FragmentError: If a chain cannot be resolved or merged, or if it declares no
            destination and none was given.
    """
    rendered: list[tuple[Path, str]] = []
    for references in targets:
        fragments = chain(references, Path.cwd(), layout)
        destination = out or fragments[-1].output
        if not destination:
            msg = f"{layout.display(fragments[-1].path)} declares no output: -- pass --out"
            raise FragmentError(msg)
        rendered.append(((layout.repo_root / destination).resolve(), render(fragments, layout, hooks, repos)))
    return rendered


def _apply(path: Path, text: str, write: bool, layout: Layout) -> bool:
    """Write a rendered config, or report whether it differs from what is on disk.

    Args:
        path: Where the config is deployed.
        text: The rendered text.
        write: Write the file. When False, report drift and change nothing.
        layout: Where the repository root is, for display paths.

    Returns:
        True if the file on disk was (or would be) changed.
    """
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    relative = layout.display(path)
    if current == text:
        print(f"ok       {relative}")
        return False
    if not write:
        print(f"STALE    {relative}", file=sys.stderr)
        sys.stderr.writelines(
            difflib.unified_diff(
                current.splitlines(True), text.splitlines(True), f"{relative} (on disk)", f"{relative} (rendered)"
            )
        )
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="" so the bytes written are a function of the fragments alone: the default
    # would translate every \n to os.linesep and turn a re-render on Windows into a
    # whole-file CRLF diff against the `end_of_line = lf` this ecosystem declares.
    path.write_text(text, encoding="utf-8", newline="")
    print(f"written  {relative}")
    return True


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser.

    Returns:
        The parser, split out so the CLI surface can be tested without running it.
    """
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "fragments",
        nargs="*",
        help="fragments to merge, in order (default: every fragment declaring an output)",
    )
    parser.add_argument("--out", help="write here instead of the last fragment's output:")
    parser.add_argument(
        "--fragment-dir",
        default=DEFAULT_FRAGMENT_DIR,
        help=f"directory holding the fragments (default: {DEFAULT_FRAGMENT_DIR}/)",
    )
    parser.add_argument("--exclude-hook", action="append", default=[], metavar="ID", help="drop this hook id")
    parser.add_argument("--exclude-repo", action="append", default=[], metavar="URL", help="drop this repository")
    parser.add_argument(
        "--write",
        action="store_true",
        help="render the configs (default: check them and report drift without writing)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Render the requested configs, or check the deployed files for drift.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.

    Returns:
        A process exit status: 0 on success, 1 if a check found drift or a fragment
        could not be merged.
    """
    args = _build_parser().parse_args(argv)
    layout = Layout.discover(fragment_dir=args.fragment_dir)

    # A repository that renders nothing is the normal case, and a shared build step or CI
    # job may call this unconditionally across a fleet of them. So an absent *default*
    # fragment directory is "nothing to do", not an error. An explicit --fragment-dir is
    # an assertion that fragments live there, and a missing one still fails below.
    if not args.fragments and args.fragment_dir == DEFAULT_FRAGMENT_DIR and not layout.fragment_dir.is_dir():
        print(f"no {DEFAULT_FRAGMENT_DIR}/ directory - nothing to render")
        return 0

    try:
        targets = [args.fragments] if args.fragments else [[str(path)] for path in deployable(layout)]
        if not targets:
            print(f"error: no fragment in {layout.display(layout.fragment_dir)}/ declares an output:", file=sys.stderr)
            return 1
        rendered = plan(targets, args.out, set(args.exclude_hook), set(args.exclude_repo), layout)
    except (FragmentError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    changed = sum(_apply(path, text, args.write, layout) for path, text in rendered)
    if not args.write and changed:
        print(f"\n{changed} config(s) out of date. Re-render with --write.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
