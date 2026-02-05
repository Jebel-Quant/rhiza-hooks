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

Embeds the output of `make help` into README.md between marker comments (`<!-- MAKE_HELP_START -->` and `<!-- MAKE_HELP_END -->`).

<!-- MAKE_HELP_START -->
```
  ____  _     _
 |  _ \| |__ (_)______ _
 | |_) | '_ \| |_  / _\`|
 |  _ <| | | | |/ / (_| |
 |_| \_\_| |_|_/___\__,_|

Usage:
  make <target>

Targets:

Rhiza Workflows
  sync                  sync with template repository as defined in .rhiza/template.yml
  summarise-sync        summarise differences created by sync with template repository
  validate              validate project structure against template repository as defined in .rhiza/template.yml
  readme                update README.md with current Makefile help output

Bootstrap
  install-uv            ensure uv/uvx is installed
  install               install
  clean                 Clean project artifacts and stale local branches

Quality and Formatting
  deptry                Run deptry
  fmt                   check the pre-commit hooks and the linting
  mypy                  run mypy analysis

Releasing and Versioning
  bump                  bump version
  release               create tag and push to remote with prompts

Meta
  help                  Display this help message
  version-matrix        Emit the list of supported Python versions from pyproject.toml

Development and Testing
  test                  run all tests
  typecheck             run mypy type checking
  security              run security scans (pip-audit and bandit)
  benchmark             run performance benchmarks
  docs-coverage         check documentation coverage with interrogate

Book
  book                  compile the companion book

Marimo Notebooks
  marimo-validate       validate all Marimo notebooks can run
  marimo                fire up Marimo server
  marimushka            export Marimo notebooks to HTML

Presentation
  presentation          generate presentation slides from PRESENTATION.md using Marp
  presentation-pdf      generate PDF presentation from PRESENTATION.md using Marp
  presentation-serve    serve presentation interactively with Marp

GitHub Helpers
  gh-install            check for gh cli existence and install extensions
  view-prs              list open pull requests
  view-issues           list open issues
  failed-workflows      list recent failing workflow runs
  whoami                check github auth status

Agentic Workflows
  copilot               open interactive prompt for copilot
  claude                open interactive prompt for claude code
  analyse-repo          run the analyser agent to update REPOSITORY_ANALYSIS.md
  summarise-changes     summarise changes since the most recent release/tag
  install-copilot       checks for copilot and prompts to install
  install-claude        checks for claude and prompts to install

Docker
  docker-build          build Docker image
  docker-run            run the Docker container
  docker-clean          remove Docker image

Documentation
  docs                  create documentation with pdoc

Custom Tasks
  hello-rhiza           a custom greeting task
  post-install          run custom logic after core install

```
<!-- MAKE_HELP_END -->

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
