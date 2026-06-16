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
`.bandit`, `.editorconfig`, `.gitignore`, `.pre-commit-config.yaml`,
`.python-version`, `cliff.toml`, `LICENSE`, `Makefile`, `SECURITY.md`,
`pytest.ini`, `ruff.toml`

### `.claude/`
`commands/rhiza_book.md`, `commands/rhiza_quality.md`, `commands/rhiza_update.md`

### `.github/`
- Workflows: `rhiza_benchmark.yml`, `rhiza_book.yml`, `rhiza_ci.yml`,
  `rhiza_codeql.yml`, `rhiza_marimo.yml`, `rhiza_release.yml`, `rhiza_sync.yml`,
  `rhiza_weekly.yml`, `rhiza_fuzzing.yml`, `rhiza_scorecard.yml`,
  `rhiza_mutation.yml` (opt-in mutation gate — `MUTATION_ENABLED`)
- `CONFIG.md`, `dependabot.yml`, `release.yml`, `secret_scanning.yml`,
  `pull_request_template.md`
- `DISCUSSION_TEMPLATE/`, `ISSUE_TEMPLATE/`

> This snapshot reflects the files synced at the pinned `ref:` (currently
> `v0.19.3`); the `files:` block of `.rhiza/template.lock` is always
> authoritative. Note that `.github/rulesets/*` is **not** shipped by the rhiza
> template at this `ref:` — if branch-protection rulesets are needed here,
> manage them separately (they are not synced).

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

### Excluded from sync (locally owned, see `exclude:` in `template.yml`)

These template tests do not apply to this repo and are intentionally excluded:
`.rhiza/tests/api/test_gh_aw_targets.py`,
`.rhiza/tests/api/test_github_targets.py`,
`.rhiza/tests/integration/test_lfs.py`.

## Locally owned (safe to edit)

Everything **not** listed above — notably `pyproject.toml`, `README.md`, `uv.lock`,
`src/rhiza_hooks/`, your own `tests/`, project-specific docs, and
`.rhiza/template.yml`. Project-specific Make hooks (`pre-install::`,
`post-install::`, …) go in the thin root `Makefile` above the `include` line.
