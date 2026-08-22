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
3. Bump `ref:` in [`.rhiza/template.yml`](.rhiza/template.yml) here and run the sync:
   **`/rhiza:update`** in Claude Code (it bumps the ref, syncs, and opens a PR
   containing only template-owned paths), or **`rhiza sync`** if you have `rhiza-cli`
   installed.

   There is **no `make sync` target** — the Makefile and its includes provide none, so
   `make help` will not list one. This step used to name it, which meant the documented
   route did not exist.

The authoritative, machine-generated list is the `files:` block of
[`.rhiza/template.lock`](.rhiza/template.lock), refreshed on every sync. Current
snapshot:

### Root
`.bandit`, `.editorconfig`, `.gitignore`, `.python-version`, `cliff.toml`,
`LICENSE`, `SECURITY.md`, `pytest.ini`, `ruff.toml`

(`.pre-commit-config.yaml` **used to be** on this list and is now excluded — see
[Excluded from sync](#excluded-from-sync). The root `Makefile` was on it until
**v1.4.0**; it is now repo-owned — see [The task runner replaced the make
layer](#the-task-runner-replaced-the-make-layer).)

> **`SECURITY.md` is managed but not verbatim.** It carries ~51 lines this repo wrote
> and the template does not ship: an `## SBOM Retrieval` section plus its summary
> bullet, added in #139, with `gh release download` and `curl` examples hard-coded to
> `Jebel-Quant/rhiza-hooks`. It survives because `.rhiza/template.lock` records
> `strategy: merge`, which has preserved it across the v0.19.3 (#197) and v1.2.0 (#263)
> syncs.
>
> Nothing enforces that. `check-managed-files` diffs *staged changes* against `HEAD`, so
> it blocks a new edit but cannot see divergence that is already committed — this
> arrangement is invisible to every gate, which is why it is written down here.
> **Check the section is still present after the next sync** (`grep -c 'SBOM Retrieval'
> SECURITY.md`), and if merge ever drops it, the fix suggested in #368 is to move
> `SECURITY.md` into `exclude:` and own it outright, as this repo does for
> `.github/CONFIG.md` — but **verify such an entry actually bites before relying on it.**
> The sync matches `exclude:` against a file's *source* path inside the template clone,
> and this file is bundle-sourced (`bundles/legal/SECURITY.md`), so source != destination.
> `.github/CONFIG.md` is bundle-sourced too (`bundles/github/.github/CONFIG.md`), so it
> is not by itself evidence that the mechanism works on a file upstream is actively
> editing.
>
> **The stale ClusterFuzzLite bullet is gone**, forward-ported out rather than waiting on
> a ref bump: upstream #1568 deleted it on 2026-08-20, and no rhiza release past `v1.4.2`
> (2026-08-19) carries that change yet. This file is now upstream `main` plus the local
> SBOM lines above, so the eventual bump is a no-op on that line. It was committed with a
> one-off `SKIP=check-managed-files`; since that hook diffs *staged* changes against
> `HEAD`, the committed state needs no waiver and CI is unaffected. Prefer that to a
> `--allow` entry, which would waive the file indefinitely. Tracked in #368.

### `.claude/`
Nothing. The template no longer syncs `.claude/` at the pinned `ref:` — the lock's
`files:` block lists no path under it, and the only file here is the untracked,
developer-local `settings.local.json`. The `commands/rhiza_*.md` files this section used
to list are gone; that functionality now lives in the `rhiza-claude` plugin as skills
(`/rhiza:update`, `/rhiza:quality`, `/rhiza:book`), which are installed per-developer
rather than synced into the repo.

### `.github/`
- Workflows: `rhiza_benchmark.yml`, `rhiza_book.yml`, `rhiza_ci.yml`,
  `rhiza_codeql.yml`, `rhiza_marimo.yml`, `rhiza_release.yml`,
  `rhiza_weekly.yml`, `rhiza_scorecard.yml`
  (`rhiza_mutation.yml` and `rhiza_fuzzing.yml` are excluded — see the `exclude:`
  block in [`.rhiza/template.yml`](.rhiza/template.yml))
- `dependabot.yml`, `release.yml`, `secret_scanning.yml`
- `rulesets/`

(`CONFIG.md`, `DISCUSSION_TEMPLATE/` and `ISSUE_TEMPLATE/` **used to be** on this
list and are now excluded — see [Excluded from sync](#excluded-from-sync).)

> This snapshot reflects the files synced at the pinned `ref:` (currently
> `v1.4.2`); the `files:` block of `.rhiza/template.lock` is the authoritative
> list, and it *is* what is on disk. The excluded paths are not in it — the
> lock records them under its own top-level `exclude:` key instead — so a path's
> absence from `files:` does not by itself mean the template never offered it.
> Cross-check `exclude:` in [`.rhiza/template.yml`](.rhiza/template.yml).

### `.rhiza/` (the sync engine — treat the whole directory as managed)
- `semgrep.yml`
- `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`
- **Owned by you:** `.rhiza/template.yml` (and `.rhiza/template.lock`, which the
  tool regenerates).

That is the whole directory — five files, three of them managed. `ls .rhiza/` is the
quickest way to check this section has not gone stale again.

(`.env` and `.gitignore` **used to be** on this list and are now excluded — see
[Excluded from sync](#excluded-from-sync).)

`rhiza.mk` and `make.d/*.mk` were on this list until the **v1.4.0** sync deleted the
whole synced make layer — see [The task runner replaced the make
layer](#the-task-runner-replaced-the-make-layer).

`tests/**` (the synced template test-suite), `assets/` and `completions/` were on
this list until the **v1.3.4** sync deleted all three — see [The rhiza checks are a
dependency, not a directory](#the-rhiza-checks-are-a-dependency-not-a-directory).

### `docs/`
`docs/assets/rhiza-logo.svg`, `docs/development/MARIMO.md`,
`docs/development/TESTS.md`, `docs/index.md`, `docs/mkdocs-base.yml`

### Excluded from sync

`.rhiza/template.yml` excludes eight paths. If another synced file needs to be
dropped locally, add it under `exclude:` there and re-sync.

**`.github/workflows/rhiza_mutation.yml`** — mutation testing is not used here
(the gate enforces a 100% mutation score, unreachable without suppressing
equivalent mutants).

**`.github/workflows/rhiza_fuzzing.yml`** — ClusterFuzzLite was retired here: the
`.clusterfuzzlite/` config it drives is gone, and the reusable workflow needs both
that directory and an opt-in variable, so the stub could only ever skip while still
costing a queued job on every PR.

**`.pre-commit-config.yaml`** — this repo *is* rhiza-hooks. The template's copy
consumes the hooks through a published `rev:`, which is right for the ~26
downstream consumers but wrong here on two counts: at the moment a release is
cut the pinned tag does not exist yet, so a release PR could never go green,
and the pin silently drifts on every release (it sat at `v0.7.0` through
`v0.8.0`). The local copy uses `repo: local` instead — no rev, and the hooks
run against the working tree rather than the last release. **Consequence: this
file is now yours.** Upstream improvements to the shared hook list (ruff,
bandit, markdownlint, …) no longer arrive by sync and must be ported by hand.

**`.rhiza/.env`** — it set only `SOURCE_FOLDER=src` and
`MARIMO_FOLDER=docs/notebooks`, which were exactly the `?=` defaults in the
then-synced `.rhiza/rhiza.mk`. Its sole effect was that a makefile assignment
outranks an exported environment variable, so the two values could not be
overridden except on the `make` command line.

Since v1.4.0 the file has a different job — it is **layer 2 of rhiza-task's
resolution order** (defaults → `.rhiza/.env` → `pyproject.toml` → `RHIZA_*`
environment), so it is now outranked by `[tool.rhiza-task]` in `pyproject.toml`
rather than the reverse. Because this repo excludes it, that table is the only
override layer available here — which is why it carries every setting that differs
from a CLI default. Re-add `.env` only to set something `pyproject.toml` cannot,
and note it would be git-ignored (see the next entry).

**`.rhiza/.gitignore`** — a single `!.env` rule, there only to re-include
`.rhiza/.env` against the root `.gitignore`'s `.env` line. With `.env` gone it
carried nothing. Consequence: a future `.rhiza/.env` would be git-ignored, so
anyone re-adding one must `git add -f` it or restore this file.

**`.github/DISCUSSION_TEMPLATE/` and `.github/ISSUE_TEMPLATE/`** — excluded *and
deleted*. The generic forms ask for a project version and a reproduction script,
which is the wrong intake for a hook provider (what matters is the hook id, the
pinned `rev:` and whether it ran under pre-commit or prek), and a hand-ported second
copy was not worth maintaining. GitHub now falls back to a free-text issue body and
unstructured discussions. The `exclude:` entries are what keeps them deleted —
remove them and the next sync restores the template's forms.

**`.github/CONFIG.md`** — repo metadata recording which secrets and variables CI
wants; excluded so this repo owns the wording.

`tests/meta/test_pre_commit_template_parity.py` enforces that port: it fetches the
template's `.pre-commit-config.yaml` **at the `ref:` this repo pins** and fails when a
hook id declared there is missing here. It compares ids, not `rev:` pins (renovate bumps
those per repo), and allows extra local hooks, so the intended `repo: local`-versus-`rev:`
difference never fires. A hook that genuinely cannot apply here goes in that file's
`_WAIVED` map with its reason, and the waiver's premise is itself re-checked. When the
check was added it immediately found `shellcheck` missing. See #293, #299.

Hook entries mirror `.pre-commit-hooks.yaml`, so a new hook must be added in both — plus
a console script in `[project.scripts]`, which `tests/meta/test_pre_commit_manifest.py`
checks in both directions.

Note that the `mutation` task (now from `rhiza-task`, not the deleted
`.rhiza/make.d/test.mk`) and the mutation section of `docs/development/TESTS.md`
still exist. The task ships inside the pinned CLI and the doc is Rhiza-owned, so
neither can be excluded here — removing them would require an upstream change in
`jebel-quant/rhiza`. Only the *workflow* is excluded.

> Tests owned by bundles this repo does **not** select (e.g. `gh-aw`, `lfs`)
> are never synced in the first place, so they need no `exclude:` entry.

## The task runner replaced the make layer

Up to **v1.3.x** the template synced a makefile layer: `.rhiza/rhiza.mk` plus ten
fragments under `.rhiza/make.d/`, ~1023 lines, and a template-owned root `Makefile` that
included them. **v1.4.0 deleted all of it.** The gates now come from the
[`rhiza-task`](https://pypi.org/project/rhiza-task/) CLI, and the root `Makefile` is a
repo-owned shim that `uvx rhiza-task shim > Makefile` emits.

`make` is still the front door — every target this file and the README document works
unchanged — but it no longer *contains* anything. A catch-all `%:` rule forwards each
target to `uvx $(RHIZA_TASK) $@`, and `RHIZA_TASK ?= rhiza-task@0.3.1` in the Makefile is
the entire version contract, in place of a template ref plus eleven synced `.mk` files.

**Consequences worth knowing before you go looking for something:**

- **`.rhiza/` holds no build machinery at all** — five files, listed above. If a
  document tells you to read `rhiza.mk` or a `make.d/*.mk` fragment, that document is
  stale (this one was; see #361).
- **Settings live in `[tool.rhiza-task]` in `pyproject.toml`.** Resolution order is
  defaults → `.rhiza/.env` → `pyproject.toml` → `RHIZA_*` environment. This repo excludes
  `.rhiza/.env`, so that table is the only override layer, and every key in it is
  annotated with why it differs from the CLI default. `uvx rhiza-task print <setting>`
  shows what one resolves to.
- **`make help` is not a static list.** It runs `uvx rhiza-task list`, so it reports what
  the pinned CLI actually defines — roughly 45 tasks across sections, far more than the
  old makefile exposed. Read it rather than guessing a target name.
- **Two probes that used to work now mislead.** `test -f .rhiza/rhiza.mk` is no longer a
  test of whether the repo is synced — it always fails, on every v1.4.x repo — and
  `make -n <target>` always succeeds, because the catch-all resolves any name. Neither
  tells you anything. Use `.rhiza/template.lock` for the first and `make help` for the
  second. (`/rhiza:quality` 0.9.0 gets both wrong: Jebel-Quant/rhiza-claude#212, #213.)
- **`make <typo>` is forwarded, not caught.** The CLI's "unknown task" error is the
  backstop, so a mistyped target fails there rather than at make.

## The rhiza checks are a dependency, not a directory

Up to **v1.3.3** the template synced its own test-suite into `.rhiza/tests/` — seven
files (`conftest.py`, `test_pyproject.py`, `test_readme.py`, `test_readme_validation.py`,
`test_docstrings.py`, `test_release_tags.py`, `README.md`) that `make rhiza-test` pointed
pytest at. **v1.3.4 deleted all seven** (upstream #1540). The same checks now ship as the
**`pytest-rhiza`** package on PyPI, and the sync also dropped `.rhiza/completions/`,
`.rhiza/make.d/completions.mk`, `.rhiza/assets/rhiza-logo.svg` (`docs/assets/rhiza-logo.svg`
is untouched) and `.github/pull_request_template.md`.

`make rhiza-test` now runs module names rather than paths. The five checks were
assembled by a `RHIZA_CHECKS` accumulator across `quality.mk`, `python.mk` and `test.mk`
until **v1.4.0 deleted all three** — the task now lives in `rhiza-task` and resolves the
same five internally:

```
pytest_rhiza.checks.test_readme      pytest_rhiza.checks.test_release_tags
pytest_rhiza.checks.test_pyproject   pytest_rhiza.checks.test_docstrings
pytest_rhiza.checks.test_readme_validation
```

Run `make rhiza-test` and read the echoed command line to see the current set — the task
prints the full `uv run --with 'pytest-rhiza @ …' pytest --pyargs …` invocation, which is
authoritative in a way this list cannot be.

- **Nothing to add to `pyproject.toml`'s dependencies.** The pin is provisioned on the
  fly, which is also why there is no `.rhiza/tests` carve-out for deptry — there is no
  longer a folder for deptry to resolve against the manifest.
- **The version is pinned by you, in `[tool.rhiza-task]`.** It was
  `RHIZA_CHECKS_VERSION ?= 0.2.1` in the managed `quality.mk`; it is now the
  `pytest-rhiza` key in `pyproject.toml`, which this repo sets to `v0.2.1` because the
  CLI's own default is older and a bare migration would have *downgraded* the checks.
  Change it there — that table is the only override layer this repo has, since
  `.rhiza/.env` is excluded.
- **A leftover `.rhiza/tests/` directory is inert but noisy.** `rhiza-test` checks for it
  and prints a WARN telling you to `git rm -r .rhiza/tests`; nothing runs whatever is in
  there. A local checkout that predates the v1.3.4 sync keeps the directory alive through
  its `__pycache__`, which git never tracked and therefore the sync never deleted —
  `rm -rf .rhiza/tests` clears the warning.
- **`tests/test_rhiza_packaging.py` is template-owned** despite living in your `tests/`.
  It is in the lock's `files:` list (it was before v1.3.4 too), so `check-managed-files`
  rejects a commit that edits it. Deliberately fixture-free, so it does not depend on
  anything `pytest-rhiza` contributes.

## Locally owned (safe to edit)

Everything **not** listed above — notably `pyproject.toml`, `README.md`, `uv.lock`,
`src/rhiza_hooks/`, your own `tests/`, project-specific docs, and
`.rhiza/template.yml`. Since v1.4.0 the root `Makefile` is repo-owned too — it is the
shim `uvx rhiza-task shim > Makefile` emits. Repo-specific targets go in `local.mk`,
which the shim `-include`s and which wins over its catch-all rule; that is where a
fragment under `.rhiza/make.d/` would have to move to.

## Local-dev gotcha: `TestGitTagVersion` and template-remote tags

`pytest_rhiza.checks.test_pyproject::TestGitTagVersion`, run by `make rhiza-test`,
asserts that the **highest version-sorted `v*` git tag** equals `[project].version`.
(Before v1.3.4 this was the synced file `.rhiza/tests/test_pyproject.py` — same
assertion, same trap; only the location moved. See [The rhiza checks are a dependency,
not a directory](#the-rhiza-checks-are-a-dependency-not-a-directory).) It passes in CI,
where a clean checkout only ever sees this repo's own tags, whose highest matches
`pyproject.toml`.

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

## Local-dev gotcha: a new `src/` module must be `git add`ed before `make test`

`tests/meta/test_pre_commit_manifest.py::test_manifest_hooks_run_through_pre_commit_try_repo`
fails when you add a module under `src/rhiza_hooks/` and have not staged it yet —
even though the module is on disk and every other test passes.

`pre-commit try-repo` builds its shadow repo from **git**, not from the working
tree, so an untracked file is absent from the package pre-commit installs into the
hook environment. Any hook importing it dies with
`ModuleNotFoundError: No module named 'rhiza_hooks._your_new_module'`, while the
rest of the suite — which imports from the working tree — is perfectly happy. The
failure therefore points at the hook rather than at the staging area.

```sh
git add src/rhiza_hooks/_your_new_module.py
```

CI never hits this: it checks out a commit, where nothing is untracked by
definition. It bites during a local refactor that extracts a helper module — see
#324/#326, where the split of `check_bumpversion_config.py` hit it. The test now
detects the combination and names the untracked files in its failure message, so
you should not have to rediscover this; the section stays as the explanation of
*why* staging is what fixes it.
