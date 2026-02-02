# 🪝 Rhiza Hooks

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Custom [pre-commit](https://pre-commit.com/) hooks for projects using [Rhiza](https://github.com/Jebel-Quant/rhiza) templates.

This repository extracts rhiza's local hooks into a standalone package, allowing rhiza and downstream projects to use them as an external hook repository.

## 🚀 Quick Start

Add to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/Jebel-Quant/rhiza-hooks
    rev: v0.1.0  # Use the latest release
    hooks:
      # Migrated from rhiza
      - id: check-rhiza-workflow-names
      - id: update-readme-help
      # Additional utility hooks
      - id: check-rhiza-config
      - id: check-makefile-targets
      - id: check-python-version-consistency
```

Then install the hooks:

```bash
pre-commit install
```

## 📋 Available Hooks

### Migrated from Rhiza

#### `check-rhiza-workflow-names`

Ensures GitHub Actions workflow names have the `(RHIZA)` prefix in uppercase. Automatically fixes files that don't conform.

**Files:** `.github/workflows/rhiza_*.yml`

**Usage:**

```yaml
- id: check-rhiza-workflow-names
```

#### `update-readme-help`

Embeds the output of `make help` into README.md between marker comments (`<!-- MAKE_HELP_START -->
```
[36m  ____  _     _
 |  _ \| |__ (_)______ _
 | |_) | '_ \| |_  / _\`|
 |  _ <| | | | |/ / (_| |
 |_| \_\_| |_|_/___\__,_|
[0m
[1mUsage:[0m
  make [36m<target>[0m

[1mTargets:[0m

[1mRhiza Workflows[0m
  [36msync                [0m  sync with template repository as defined in .rhiza/template.yml
  [36msummarise-sync      [0m  summarise differences created by sync with template repository
  [36mvalidate            [0m  validate project structure against template repository as defined in .rhiza/template.yml
  [36mreadme              [0m  update README.md with current Makefile help output

[1mBootstrap[0m
  [36minstall-uv          [0m  ensure uv/uvx is installed
  [36minstall             [0m  install
  [36mclean               [0m  Clean project artifacts and stale local branches

[1mQuality and Formatting[0m
  [36mdeptry              [0m  Run deptry
  [36mfmt                 [0m  check the pre-commit hooks and the linting
  [36mmypy                [0m  run mypy analysis

[1mReleasing and Versioning[0m
  [36mbump                [0m  bump version
  [36mrelease             [0m  create tag and push to remote with prompts

[1mMeta[0m
  [36mhelp                [0m  Display this help message
  [36mversion-matrix      [0m  Emit the list of supported Python versions from pyproject.toml

[1mDevelopment and Testing[0m
  [36mtest                [0m  run all tests
  [36mtypecheck           [0m  run mypy type checking
  [36msecurity            [0m  run security scans (pip-audit and bandit)
  [36mmutate              [0m  run mutation testing with mutmut (slow, for CI or thorough testing)
  [36mbenchmark           [0m  run performance benchmarks
  [36mdocs-coverage       [0m  check documentation coverage with interrogate

[1mDocumentation[0m
  [36mdocs                [0m  create documentation with pdoc
  [36mbook                [0m  compile the companion book

[1mMarimo Notebooks[0m
  [36mmarimo-validate     [0m  validate all Marimo notebooks can run
  [36mmarimo              [0m  fire up Marimo server
  [36mmarimushka          [0m  export Marimo notebooks to HTML

[1mCustom Tasks[0m
  [36mhello-rhiza         [0m  a custom greeting task
  [36mpost-install        [0m  run custom logic after core install

```
<!-- MAKE_HELP_END -->`).

**Triggers on:** Changes to `Makefile`

**Usage:**

```yaml
- id: update-readme-help
```

### Additional Utility Hooks

#### `check-rhiza-config`

Validates the `.rhiza/template.yml` configuration file to ensure:

- All required keys are present (`template-repository`, `template-branch`, `include`)
- The `template-repository` is in the correct `owner/repo` format
- No unknown keys are present
- The `include` list is not empty

**Usage:**

```yaml
- id: check-rhiza-config
```

#### `check-makefile-targets`

Checks that your Makefile contains recommended targets for rhiza-based projects:

- `install` - Install dependencies
- `test` - Run tests
- `fmt` - Format code
- `help` - Show available targets

By default, this hook only warns about missing targets. Use `--strict` to fail on missing targets.

**Usage:**

```yaml
- id: check-makefile-targets
  args: [--strict]  # Optional: fail if targets are missing
```

#### `check-python-version-consistency`

Ensures Python version is consistent between `.python-version` and `pyproject.toml`'s `requires-python`.

**Usage:**

```yaml
- id: check-python-version-consistency
```

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

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Rhiza](https://github.com/Jebel-Quant/rhiza) - The template system these hooks are designed for
- [pre-commit](https://pre-commit.com/) - The framework that makes this possible
