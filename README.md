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
    rev: v0.6.2  # Use the latest release
    hooks:
      # Migrated from rhiza
      - id: check-rhiza-workflow-names
      - id: update-readme-help
      # Additional utility hooks
      - id: check-rhiza-config
      - id: check-makefile-targets
      - id: check-python-version-consistency
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
- If README is not updated, ensure it still contains `<!-- MAKE_HELP_START -->` and `<!-- MAKE_HELP_END -->` markers.

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

#### `check-template-bundles`

Validates templates specified in `.rhiza/template.yml` against the `template-bundles.yml` file from the template repository. This hook:

- Fetches `template-bundles.yml` from the remote template repository specified in your config
- Ensures all templates listed in your `.rhiza/template.yml` exist in the remote bundles
- Validates bundle structure (each bundle has `description` and `files`)
- Checks that bundle dependencies are valid

**Triggers on:** Changes to `.rhiza/template.yml`

This hook reaches the network on every run. A transient failure is retried once with a short backoff before giving up; pass `--offline` to skip the remote fetch entirely (the hook then passes without validating), which is useful for offline commits.

**Usage:**

```yaml
- id: check-template-bundles
  # args: [--offline]  # Optional: skip the network fetch and pass
```

**Troubleshooting:**

- This hook normally fetches `template-bundles.yml` from the configured template repository and retries once on transient network errors.
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
