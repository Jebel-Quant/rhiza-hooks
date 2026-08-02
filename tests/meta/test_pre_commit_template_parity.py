"""Guard the locally-owned ``.pre-commit-config.yaml`` against template drift (issue #299).

Every other rhiza-managed repo receives ``.pre-commit-config.yaml`` by sync. This one
excludes it (see ``exclude:`` in ``.rhiza/template.yml`` and #293): the template's copy
consumes these hooks through a published ``rev:``, which is right for the ~26 downstream
consumers but wrong here — at the moment a release is cut the pinned tag does not exist
yet, so a release PR could never go green, and the pin drifts on every release. The local
copy uses ``repo: local`` instead, so the hooks run against the working tree.

The cost of that exclusion is that improvements to the **shared** hook list — ruff,
bandit, markdownlint, shellcheck, … — no longer arrive by sync and must be ported by
hand. Until this file the only safeguard was a sentence in CLAUDE.md telling a human to
"check it against the template's copy periodically", so a hook the template added simply
stayed absent here. It had: at the ref pinned when this test was written the template
carried ``shellcheck``, and this repo did not.

What is compared, and what deliberately is not:

* **Hook ids, not pins.** Every hook id the template declares must appear here.
  ``rev:`` values are *not* compared: renovate and dependabot bump them per repository,
  so requiring equality would fail constantly and say nothing about the hook list.
* **Ids, not repo URLs.** This repo's own hooks live under ``repo: local`` while the
  template lists them under a ``rev:``-pinned ``rhiza-hooks`` entry. That difference is
  the entire point of the exclusion, so matching on id sidesteps it.
* **Extra local hooks are fine.** This repo dogfoods every hook it publishes, including
  ones the template has not adopted yet, so the assertion is one-directional:
  upstream ⊆ local.

The comparison is made at the ref this repo pins, not at the template's default branch.
That makes the answer deterministic — a fixed ref serves a fixed file — and it puts the
report exactly where it is actionable: when someone bumps ``ref:`` and re-syncs.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_OUR_CONFIG = _REPO_ROOT / ".pre-commit-config.yaml"
_TEMPLATE_YML = _REPO_ROOT / ".rhiza" / "template.yml"

_FETCH_TIMEOUT_SECONDS = 15.0

# Upstream hooks this repo deliberately does not run, each with the reason. A waiver is
# only legitimate when the hook cannot apply here — never merely because adopting it
# would be work. Keep `test_waivers_are_still_justified` in step with every entry.
_WAIVED: dict[str, str] = {
    "check-jsonschema": (
        "validates .rhiza/template-bundles.yml against .rhiza/template-bundles.schema.json. "
        "Only a template repository publishes a bundles document; this repo consumes one, so "
        "the hook would match no files here."
    ),
}


def _hook_ids(config: dict[str, Any]) -> set[str]:
    """Collect every hook id in a parsed pre-commit configuration, across all repos."""
    ids: set[str] = set()
    for repo in config.get("repos", []):
        if not isinstance(repo, dict):
            continue
        for hook in repo.get("hooks", []) or []:
            if isinstance(hook, dict) and isinstance(hook.get("id"), str):
                ids.add(hook["id"])
    return ids


def _pinned_template() -> tuple[str, str]:
    """Return the ``(repository, ref)`` this repo pins in ``.rhiza/template.yml``."""
    config = yaml.safe_load(_TEMPLATE_YML.read_text(encoding="utf-8"))
    repository = config.get("repository") or config.get("template-repository")
    ref = config.get("ref") or config.get("template-branch")
    assert isinstance(repository, str), f"no template repository in {_TEMPLATE_YML}"
    assert isinstance(ref, str), f"no pinned ref in {_TEMPLATE_YML}"
    return repository, ref


def _fetch_template_config(repository: str, ref: str) -> dict[str, Any]:
    """Fetch and parse the template's ``.pre-commit-config.yaml`` at ``ref``.

    Skips the test on a transport failure — an offline machine cannot tell a healthy
    repository from a broken one. An HTTP error is *not* skipped: a 404 means the pinned
    ref or the path is wrong, which is a real finding about this repo's configuration.
    """
    url = f"https://raw.githubusercontent.com/{repository}/{ref}/.pre-commit-config.yaml"
    # The scheme is fixed by the literal prefix above, but `repository` and `ref` are read
    # from a file, so bandit sees a computed URL and cannot rule out `file:` or a custom
    # scheme (B310). Re-assert it, as `rhiza_hooks._bundles_fetch` does for the same reason,
    # which is what makes the suppression below true rather than merely quiet.
    assert urlparse(url).scheme == "https", f"refusing to fetch a non-https URL: {url}"
    try:
        with urllib.request.urlopen(url, timeout=_FETCH_TIMEOUT_SECONDS) as response:  # nosec B310
            content = response.read()
    except urllib.error.HTTPError as exc:  # pragma: no cover - needs a bad pin to reach
        pytest.fail(f"HTTP {exc.code} fetching {url}: the pinned ref or the path is wrong")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        pytest.skip(f"cannot reach {url} ({exc}); network-dependent parity check skipped")

    parsed = yaml.safe_load(content)
    assert isinstance(parsed, dict), f"template config at {ref} is not a mapping"
    return parsed


@pytest.fixture(scope="module")
def template_hook_ids() -> set[str]:
    """The hook ids the template declares at the ref this repo pins."""
    repository, ref = _pinned_template()
    return _hook_ids(_fetch_template_config(repository, ref))


@pytest.fixture(scope="module")
def our_hook_ids() -> set[str]:
    """The hook ids this repo's own .pre-commit-config.yaml declares."""
    return _hook_ids(yaml.safe_load(_OUR_CONFIG.read_text(encoding="utf-8")))


def test_no_upstream_hook_is_missing(template_hook_ids: set[str], our_hook_ids: set[str]) -> None:
    """Every hook the template runs is also run here, waivers aside.

    This is the check the exclusion in `.rhiza/template.yml` owes the repo: without it a
    hook added upstream is absent here until a human happens to compare the two files.
    """
    missing = template_hook_ids - our_hook_ids - set(_WAIVED)
    repository, ref = _pinned_template()
    assert missing == set(), (
        f"hooks present in {repository}@{ref} but missing from {_OUR_CONFIG.name}: {sorted(missing)}. "
        "Port them (copy the repo/rev/args block from the template's copy), or add an entry to "
        "_WAIVED in this file with the reason the hook cannot apply here."
    )


def test_waivers_name_a_hook_the_template_actually_declares(template_hook_ids: set[str]) -> None:
    """A waiver for a hook the template no longer has is dead weight, so it is reported.

    Keeps the waiver list from accumulating entries that outlive the upstream hook they
    excuse — the same rot the sentence in CLAUDE.md suffered from.
    """
    stale = set(_WAIVED) - template_hook_ids
    assert stale == set(), f"waivers for hooks the template no longer declares: {sorted(stale)}"


def test_waivers_are_still_justified() -> None:
    """Each waiver's premise is re-checked, so it cannot silently outlive its reason."""
    # check-jsonschema is waived because only a template repository publishes a bundles
    # document. If one ever appears here, the waiver is wrong and the hook is wanted.
    assert not (_REPO_ROOT / ".rhiza" / "template-bundles.yml").exists(), (
        "this repo now has .rhiza/template-bundles.yml, so the check-jsonschema waiver "
        "no longer holds — adopt the hook and drop the _WAIVED entry"
    )


def test_local_block_covers_every_published_hook(our_hook_ids: set[str]) -> None:
    """This repo runs every hook it publishes — the dogfooding #298 established.

    Not template parity, but the same failure mode from the other side: a hook shipped in
    `.pre-commit-hooks.yaml` and never run here is untested against a real commit.
    """
    manifest = yaml.safe_load((_REPO_ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    published = {hook["id"] for hook in manifest}
    assert published - our_hook_ids == set(), (
        f"published hooks not dogfooded in {_OUR_CONFIG.name}: {sorted(published - our_hook_ids)}"
    )
