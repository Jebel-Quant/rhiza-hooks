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
uv sync

# Install pre-commit hooks
pre-commit install
```

### Testing hooks locally

Use `pre-commit try-repo` to test hooks without committing:

```bash
# Test all hooks against your current project
pre-commit try-repo . --all-files

# Test a specific hook
pre-commit try-repo . check-rhiza-config --files .rhiza/template.yml
```

### Running tests

```bash
uv run pytest
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Rhiza](https://github.com/Jebel-Quant/rhiza) - The template system these hooks are designed for
- [pre-commit](https://pre-commit.com/) - The framework that makes this possible
