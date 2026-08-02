# CLAUDE.md

Guidance for Claude Code (and human contributors) working in this repository.

## What is this repo?

`rhiza-hooks` provides the **pre-commit hooks** used by Rhiza-managed projects —
most notably `check_template_bundles`, which validates a project's
`.rhiza/template.yml` against the bundles published by the template repository.
Its own development infrastructure is synced from Rhiza.

## Rhiza-managed files — do NOT edit directly

This project syncs its development infrastructure from the **Rhiza** template repo
(`jebel-quant/rhiza`) via `rhiza-cli`. The configuration lives in
[`.rhiza/template.yml`](.rhiza/template.yml) (profile `github-project` + the `legal`
template).

**The files below are owned by Rhiza. Do not edit them directly here** — any local
change is overwritten on the next sync. To change one of them:

1. Make the change **upstream** in `jebel-quant/rhiza` (the relevant
   `bundles/<bundle>/...` source).
2. Cut a new Rhiza release.
3. Bump `ref:` in [`.rhiza/template.yml`](.rhiza/template.yml) here and run
   **`make sync`** (which invokes `rhiza sync`).

The authoritative, machine-generated list is the `files:` block of
[`.rhiza/template.lock`](.rhiza/template.lock), refreshed on every sync. Current
snapshot:

### Root
`.bandit`, `.editorconfig`, `.gitignore`, `.python-version`, `cliff.toml`,
`LICENSE`, `Makefile`, `SECURITY.md`, `pytest.ini`, `ruff.toml`

(`.pre-commit-config.yaml` **used to be** on this list and is now excluded — see
[Excluded from sync](#excluded-from-sync).)

### `.claude/`
`commands/rhiza_book.md`, `commands/rhiza_quality.md`, `commands/rhiza_update.md`

### `.github/`
- Workflows: `rhiza_benchmark.yml`, `rhiza_book.yml`, `rhiza_ci.yml`,
  `rhiza_codeql.yml`, `rhiza_marimo.yml`, `rhiza_release.yml`, `rhiza_sync.yml`,
  `rhiza_weekly.yml`, `rhiza_fuzzing.yml`, `rhiza_scorecard.yml`
  (`rhiza_mutation.yml` is excluded — see the `exclude:` block in
  [`.rhiza/template.yml`](.rhiza/template.yml))
- `CONFIG.md`, `dependabot.yml`, `release.yml`, `secret_scanning.yml`,
  `pull_request_template.md`
- `DISCUSSION_TEMPLATE/`, `ISSUE_TEMPLATE/`

> This snapshot reflects the files synced at the pinned `ref:` (currently
> `v1.2.1`); the `files:` block of `.rhiza/template.lock` is always
> authoritative.

### `.rhiza/` (the sync engine — treat the whole directory as managed)
- `rhiza.mk`, `make.d/*.mk`, `requirements/*.txt`, `semgrep.yml`,
  `.cfg.toml`, `.env`, `.gitignore`, `.rhiza-version`
- `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `assets/`, `completions/`
- `tests/**` (the synced template test-suite), `utils/pip_audit_policy.py`,
  `utils/suppression_audit.py`
- **Owned by you:** `.rhiza/template.yml` (and `.rhiza/template.lock`, which the
  tool regenerates).

### `docs/`
`docs/assets/rhiza-logo.svg`, `docs/development/MARIMO.md`,
`docs/development/TESTS.md`, `docs/index.md`, `docs/mkdocs-base.yml`

### Excluded from sync

`.rhiza/template.yml` excludes two files. If another synced file needs to be
dropped locally, add it under `exclude:` there and re-sync.

**`.github/workflows/rhiza_mutation.yml`** — mutation testing is not used here
(the gate enforces a 100% mutation score, unreachable without suppressing
equivalent mutants).

**`.pre-commit-config.yaml`** — this repo *is* rhiza-hooks. The template's copy
consumes the hooks through a published `rev:`, which is right for the ~26
downstream consumers but wrong here on two counts: at the moment a release is
cut the pinned tag does not exist yet, so a release PR could never go green,
and the pin silently drifts on every release (it sat at `v0.7.0` through
`v0.8.0`). The local copy uses `repo: local` instead — no rev, and the hooks
run against the working tree rather than the last release. **Consequence: this
file is now yours.** Upstream improvements to the shared hook list (ruff,
bandit, markdownlint, …) no longer arrive by sync and must be ported by hand;
check it against the template's copy periodically. Hook entries mirror
`.pre-commit-hooks.yaml`, so a new hook must be added in both. See #293.

Note that `make mutation` (from the managed `.rhiza/make.d/test.mk`) and the
mutation section of `docs/development/TESTS.md` still exist — both are Rhiza-owned
files that cannot be excluded without losing unrelated content, so removing them
would require an upstream change in `jebel-quant/rhiza`.

> Tests owned by bundles this repo does **not** select (e.g. `gh-aw`, `lfs`)
> are never synced in the first place, so they need no `exclude:` entry.

## Locally owned (safe to edit)

Everything **not** listed above — notably `pyproject.toml`, `README.md`, `uv.lock`,
`src/rhiza_hooks/`, your own `tests/`, project-specific docs, and
`.rhiza/template.yml`. Project-specific Make hooks (`pre-install::`,
`post-install::`, …) go in the thin root `Makefile` above the `include` line.

## Local-dev gotcha: `TestGitTagVersion` and template-remote tags

`.rhiza/tests/structure/test_pyproject.py::TestGitTagVersion` asserts that the
**highest version-sorted `v*` git tag** equals `[project].version`. It passes in
CI (a clean checkout only ever sees this repo's own tags — highest `v0.7.0`,
matching `pyproject.toml`).

It can fail **locally** if you have added a git remote for the template repo
(e.g. `git remote add rhiza …jebel-quant/rhiza`): a plain `git fetch` pulls that
remote's release tags (`v0.18.x`, etc.) into your local tag namespace, where they
outrank this repo's tags and break the assertion. They are template tags, not
rhiza-hooks tags. To clean them up (reversible — `git fetch rhiza --tags`
restores them):

```sh
# delete every local tag that is NOT on origin (rhiza-hooks)
comm -23 <(git tag | sort -u) \
         <(git ls-remote --tags origin | sed 's#.*refs/tags/##' | grep -v '\^{}' | sort -u) \
  | xargs -r git tag -d
```

Prefer fetching the template with `git fetch rhiza --no-tags` to avoid the
pollution in the first place.
