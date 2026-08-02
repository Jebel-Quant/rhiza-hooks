# 🪝 Rhiza Hooks

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://github.com/jebel-quant/rhiza-hooks)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CodeFactor](https://www.codefactor.io/repository/github/jebel-quant/rhiza-hooks/badge/main)](https://www.codefactor.io/repository/github/jebel-quant/rhiza-hooks/overview/main)
[![Rhiza](https://img.shields.io/badge/dynamic/yaml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fjebel-quant%2Frhiza-hooks%2Fmain%2F.rhiza%2Ftemplate.yml&query=%24.ref&label=rhiza)](https://github.com/jebel-quant/rhiza)
[![Coverage](https://jebel-quant.github.io/rhiza-hooks/coverage-badge.svg)](https://jebel-quant.github.io/rhiza-hooks/reports/html-coverage/)
[![Mutation Score](https://img.shields.io/badge/mutation%20score-100%25-brightgreen)](docs/development/TESTS.md#mutation-testing)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/Jebel-Quant/rhiza-hooks/badge)](https://scorecard.dev/viewer/?uri=github.com/Jebel-Quant/rhiza-hooks)

Custom [pre-commit](https://pre-commit.com/) hooks for projects using [Rhiza](https://github.com/Jebel-Quant/rhiza) templates.

This repository extracts rhiza's local hooks into a standalone package, allowing rhiza and downstream projects to use them as an external hook repository.

## 🚀 Quick Start

Add to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/Jebel-Quant/rhiza-hooks
    rev: v0.7.0  # Use the latest release
    hooks:
      # Migrated from rhiza
      - id: check-rhiza-workflow-names
      - id: update-readme-help
      # Additional utility hooks
      - id: check-rhiza-config
      - id: check-makefile-targets
      - id: check-python-version-consistency
      - id: check-rust-version-consistency
      - id: check-go-version-consistency
      - id: check-bumpversion-config
      - id: check-template-bundles
```

Then install the hooks:

```bash
pre-commit install
```

## 📋 Available Hooks

| Hook | Triggers on | Autofixes? | Exit code |
| --- | --- | --- | --- |
| `check-rhiza-workflow-names` | `.github/workflows/rhiza_*.yml` | ✅ rewrites a wrong `name:` | `1` if any file was changed or has an error, else `0` |
| `update-readme-help` | `Makefile` | ✅ rewrites `README.md` between markers | `1` if `README.md` was changed, else `0` (never fails when `make help` is unavailable) |
| `check-rhiza-config` | `.rhiza/template.yml` | ❌ validates only | `1` if invalid, else `0` |
| `check-makefile-targets` | `Makefile`, `.rhiza/*.mk` | ❌ warns only | `0` by default (warn-only); `1` on missing targets **only** with `--strict` |
| `check-python-version-consistency` | `.python-version`, `pyproject.toml` | ❌ validates only | `1` on mismatch, else `0` |
| `check-rust-version-consistency` | `rust-toolchain`, `rust-toolchain.toml`, `Cargo.toml` | ❌ validates only | `1` on mismatch, else `0` |
| `check-go-version-consistency` | `.go-version`, `go.mod` | ❌ validates only | `1` on mismatch, else `0` |
| `check-bumpversion-config` | `pyproject.toml`, `.bumpversion.toml`, `.bumpversion.cfg`, `setup.cfg`, `.rhiza/.cfg.toml` | ❌ validates only | `1` if no discoverable config or a drifted `current_version`, else `0` |
| `check-template-bundles` | `.rhiza/template.yml` | ❌ validates only (network) | `1` on validation failure, else `0`; `0` when `--offline` |

Details for each hook follow.

### Migrated from Rhiza

#### `check-rhiza-workflow-names`

Ensures GitHub Actions workflow names have the `(RHIZA)` prefix in uppercase. Automatically fixes files that don't conform.

**Files:** `.github/workflows/rhiza_*.yml`

**Usage:**

```yaml
- id: check-rhiza-workflow-names
```

**Troubleshooting:**

- The hook only scans `.github/workflows/rhiza_*.yml`; if nothing happens, confirm your workflow filename matches that pattern.
- A hook failure after edits is expected when it auto-fixes `name:` values—re-stage the workflow file and re-run.

#### `update-readme-help`

Embeds the output of `make help` into README.md between marker comments.

**Triggers on:** Changes to `Makefile`

**Usage:**

```yaml
- id: update-readme-help
```

**Troubleshooting:**

- If `make` (or `make help`) is unavailable, this hook exits successfully and skips updates by design.

### Additional Utility Hooks

#### `check-rhiza-config`

Validates the `.rhiza/template.yml` configuration file to ensure:

- All required keys are present (`template-repository`, `template-branch`)
- At least one of `include` or `templates` (or alias `profiles`) is present
- The `template-repository` is in the correct `owner/repo` format
- No unknown keys are present
- The `include` list (if present) is not empty
- The `templates` list (or alias `profiles`, if present) is not empty

**Usage:**

```yaml
- id: check-rhiza-config
```

**Troubleshooting:**

- Validate that `.rhiza/template.yml` contains `template-repository` and `template-branch`, plus at least one of `include`, `templates`, or `profiles`.
- If you see unknown-key errors, compare your keys to the documented schema and remove unsupported entries.

#### `check-makefile-targets`

Checks that your Makefile contains recommended targets for rhiza-based projects:

- `install` - Install dependencies
- `test` - Run tests
- `fmt` - Format code
- `help` - Show available targets

By default, this hook only warns about missing targets. Use `--strict` to fail on missing targets.

The expected set can be customised:

- `--target NAME` (repeatable) **replaces** the default set with exactly the targets you list.
- `--extend-target NAME` (repeatable) **adds** to the active set (defaults, or whatever `--target` selected).

**Usage:**

```yaml
- id: check-makefile-targets
  args: [--strict]  # Optional: fail if targets are missing

# Require a custom set instead of the defaults:
- id: check-makefile-targets
  args: [--target, build, --target, lint]

# Keep the defaults and also require `deploy`:
- id: check-makefile-targets
  args: [--extend-target, deploy]
```

**Troubleshooting:**

- Default mode is warn-only, so missing targets do not fail commits unless you pass `--strict`.
- If a required target is intentionally different, use `--target`/`--extend-target` to align checks with your Makefile.

#### `check-python-version-consistency`

Ensures Python version is consistent between `.python-version` and `pyproject.toml`'s `requires-python`.

**Usage:**

```yaml
- id: check-python-version-consistency
```

**Troubleshooting:**

- Keep `.python-version` aligned with `project.requires-python` in `pyproject.toml`.
- If ranges are used (for example `>=3.11`), ensure the `.python-version` value satisfies that range exactly.

#### `check-rust-version-consistency`

Ensures the Rust version a project pins agrees with the version it declares it supports. A Rust project states this in up to three places:

- `rust-toolchain.toml` — `[toolchain] channel`, the toolchain rustup installs for the checkout
- `rust-toolchain` — the legacy form of the same file, either TOML or a bare channel name on one line
- `Cargo.toml` — `rust-version` under `[package]` and/or `[workspace.package]`, the crate's minimum supported Rust version (MSRV)

The hook enforces three relationships:

1. The two toolchain files pin the same channel (when both are present).
2. `[package] rust-version` and `[workspace.package] rust-version` declare the same MSRV (when both are present).
3. The pinned toolchain is **not older** than the declared MSRV — a pin below the MSRV cannot build the crate.

Named channels (`stable`, `beta`, `nightly`, `nightly-2024-01-01`) carry no version number and are accepted without comparison. Trailing zeros are insignificant, so `1.75` and `1.75.0` are the same version. A repository with none of these files passes, so the hook is harmless in a polyglot monorepo.

**Triggers on:** Changes to `rust-toolchain`, `rust-toolchain.toml`, or `Cargo.toml`

**Usage:**

```yaml
- id: check-rust-version-consistency
```

**Troubleshooting:**

- "the pinned toolchain must be at least the MSRV" means your `rust-toolchain*` channel is older than `rust-version` in `Cargo.toml`; raise the pin or lower the MSRV.
- If you keep both `rust-toolchain` and `rust-toolchain.toml`, delete one — rustup only reads the `.toml` form, so the other silently drifts.
- The hook only reads the repository-root `Cargo.toml`; MSRVs declared by individual workspace members are not compared.

#### `check-go-version-consistency`

Ensures the Go version a project pins agrees with the version its module requires. A Go project states this in up to three places:

- `go.mod` — the `go` directive, the minimum language version the module requires
- `go.mod` — the optional `toolchain` directive, the toolchain the `go` command switches to
- `.go-version` — the toolchain pin honoured by goenv and `actions/setup-go`

The hook enforces three relationships:

1. The `toolchain` directive is not below the `go` directive (the `go` command itself rejects that).
2. `.go-version` is not below the `go` directive — the pinned toolchain could not build the module.
3. `.go-version` names the same version as the `toolchain` directive (when both are present).

A leading `go` prefix is stripped before comparison, so `go1.22.5` and `1.22.5` are the same pin, as are `1.22` and `1.22.0`. Non-numeric values (`toolchain default`, `toolchain local`) carry no version and are accepted without comparison. Contents of parenthesised `require (…)` blocks are skipped, so a dependency such as `go.uber.org/zap` is never mistaken for the `go` directive. A repository with none of these files passes.

**Triggers on:** Changes to `.go-version` or `go.mod`

**Usage:**

```yaml
- id: check-go-version-consistency
```

**Troubleshooting:**

- "which is below the go.mod go directive" means the pinned toolchain is older than the module's minimum; raise `.go-version`/`toolchain`, or lower the `go` directive.
- If `.go-version` and `toolchain` disagree, decide which one is authoritative — CI (`actions/setup-go`) reads the former while local `go build` obeys the latter, so a skew builds different code in the two places.
- The hook reads only `go.mod`; `go.work` directives in a multi-module workspace are not compared.

#### `check-bumpversion-config`

Ensures `bump-my-version` can actually find this project's version configuration.

`bump-my-version` reads its config from a fixed set of filenames — `.bumpversion.toml`, `pyproject.toml`, `.bumpversion.cfg`, `setup.cfg` — and nothing else. When it finds none it does **not** fail: it falls back to `git describe` and reports the last reachable tag as the current version. Release tooling then computes bump candidates from that number rather than the project's own, which can offer a version that has already been published.

The hook enforces two relationships for any project with a static `[project].version`:

1. A bumpversion section exists in one of the searched files.
2. If that section declares `current_version`, it equals `[project].version` — a stale value bumps from the wrong number and then fails to match the file it is meant to rewrite.

The motivating case is rhiza-specific: rhiza syncs a fully-formed `[tool.bumpversion]` block into `.rhiza/.cfg.toml`, which is not a searched filename and so never takes effect. When the hook finds that file and no discoverable config, it names it directly rather than just reporting an absence. See [jebel-quant/rhiza#1453](https://github.com/Jebel-Quant/rhiza/issues/1453).

Projects with no `pyproject.toml`, or with `dynamic = ["version"]`, are out of scope and pass — their version does not live in a file `bump-my-version` would rewrite. Declaring `current_version` is optional: with a `[tool.bumpversion]` table present in `pyproject.toml`, `bump-my-version` reads and rewrites PEP 621 `[project].version` natively, so omitting it keeps a single source of truth.

**Triggers on:** Changes to `pyproject.toml`, `.bumpversion.toml`, `.bumpversion.cfg`, `setup.cfg` or `.rhiza/.cfg.toml`

**Usage:**

```yaml
- id: check-bumpversion-config
```

**Troubleshooting:**

- "no bumpversion config was found" means releases are computing versions from git tags. Add a `[tool.bumpversion]` table to `pyproject.toml`; it needs no other keys.
- If the error names `.rhiza/.cfg.toml`, that block is inert — it is synced from the template but never read. Do not edit it; add the table to `pyproject.toml` instead.
- A `current_version` mismatch usually means a bump was reverted or hand-edited. Reconcile the two values before releasing.

#### `check-template-bundles`

Validates templates specified in `.rhiza/template.yml` against the `template-bundles.yml` file from the template repository. This hook:

- Fetches `template-bundles.yml` from the remote template repository specified in your config
- Ensures all templates listed in your `.rhiza/template.yml` exist in the remote bundles
- Validates bundle structure (each bundle has `description` and `files`)
- Checks that bundle dependencies are valid

**Triggers on:** Changes to `.rhiza/template.yml`

This hook reaches the network on every run. Transient failures are retried with a short linear backoff, and each failed attempt is logged so CI failures are diagnosable. The retry count and per-request timeout are configurable, and `--offline` skips the remote fetch entirely (the hook then passes without validating), which is useful for offline commits.

**Options:**

| Flag | Default | Effect |
| --- | --- | --- |
| `--offline` | off | Skip the remote fetch and pass without validating |
| `--retries N` | `1` | Retries after the first attempt on transient network errors (`0` disables retrying) |
| `--timeout S` | `10.0` | Per-request network timeout, in seconds |

**Usage:**

```yaml
- id: check-template-bundles
  # args: [--offline]              # Optional: skip the network fetch and pass
  # args: [--retries, "3", --timeout, "20"]  # Optional: tune flaky-network behaviour
```

**Troubleshooting:**

- This hook normally fetches `template-bundles.yml` from the configured template repository and retries on transient network errors; raise `--retries`/`--timeout` if your network is slow or flaky, and read the per-attempt log lines to see what failed.
- Use `--offline` when committing without network access; it skips the fetch and exits successfully without remote validation.

## 🛠️ Development

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Setup

```bash
# Clone the repository
git clone https://github.com/Jebel-Quant/rhiza-hooks.git
cd rhiza-hooks

# Install dependencies
make install

# Install pre-commit hooks
pre-commit install
```

### Common Commands

```bash
make install    # Install dependencies
make test       # Run tests with coverage
make fmt        # Format and lint code
make deptry     # Check for unused/missing dependencies
make help       # Show all available targets
```

### Testing hooks locally

Use `pre-commit try-repo` to test hooks without committing:

```bash
# Test all hooks against your current project
pre-commit try-repo . --all-files

# Test a specific hook
pre-commit try-repo . check-rhiza-config --files .rhiza/template.yml
```

### Tests, coverage & mutation testing

This project enforces **100% line/branch coverage** and a **100% mutation score** (via [`mutmut`](https://github.com/boxed/mutmut)). Both gates run in CI, but you can reproduce them locally before opening a PR:

```bash
make test       # Run the suite with coverage (fails under 100%)
make mutation   # Run mutation testing (fails on any surviving mutant)
```

`make mutation` writes an HTML report to `_tests/mutation/html/index.html` — open it to see exactly which mutants survived and which test should have caught each one. `mutmut results` lists survivors on the command line.

Coverage proves a line ran; mutation testing proves a wrong result would be *caught*. When a mutant survives, the fix is almost always a stronger assertion (pin the exact value/message rather than asserting "truthy").

The project test suite **mirrors `src/rhiza_hooks/` 1:1** under `tests/rhiza_hooks/`: each module `src/rhiza_hooks/<module>.py` has a matching `tests/rhiza_hooks/test_<module>.py` (including unit, integration and property-based tests for that module). Repository meta-tests that are not tied to a single package module — such as `tests/test_check_test_layout.py` — stay at the top level of `tests/`. This layout is enforced by `scripts/check_test_layout.py`, which verifies that every module in `src/rhiza_hooks/` is covered by at least one test file that imports it and that every `tests/test_*.py` file maps to a package module (or is an allowed meta-test); it runs as part of the suite via `tests/test_check_test_layout.py`.

#### Equivalent mutants

Occasionally a mutant is genuinely **equivalent** — it changes the code without changing any observable behaviour, so no test can kill it (e.g. swapping a boolean initializer that is only ever read in a truthiness check between `False` and `None`). Mark only these with a `# pragma: no mutate` comment that states *why* it is equivalent, e.g.:

```python +RHIZA_SKIP
failed = False  # pragma: no mutate  # equivalent: only ever read via `if failed`
```

Reach for the pragma sparingly and only after confirming no assertion can distinguish the mutant — a real, killable mutant should be killed with a test, not suppressed.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 💬 Getting help

- Ask questions and get support in [GitHub Discussions](https://github.com/Jebel-Quant/rhiza-hooks/discussions) using the [Q&A template](.github/DISCUSSION_TEMPLATE/q-and-a.yml).
- Report bugs or request features using the [issue templates](https://github.com/Jebel-Quant/rhiza-hooks/issues/new/choose).

## 🙏 Acknowledgments

- [Rhiza](https://github.com/Jebel-Quant/rhiza) - The template system these hooks are designed for
- [pre-commit](https://pre-commit.com/) - The framework that makes this possible
