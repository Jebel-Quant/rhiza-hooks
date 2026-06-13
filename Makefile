## Makefile (repo-owned)
# Keep this file small. It can be edited without breaking template sync.

DEFAULT_AI_MODEL=claude-sonnet-4.6
LOGO_FILE=.rhiza/assets/rhiza-logo.svg
GH_AW_ENGINE ?= copilot  # Default AI engine for gh-aw workflows (copilot, claude, or codex)

# Override template default: fix quoting bug and typo (mkdocstring -> mkdocstrings)
MKDOCS_EXTRA_PACKAGES = --with-editable . --with 'mkdocstrings[python]'

# Override template default (90): this project maintains full coverage.
# Set before the include so the template's `COVERAGE_FAIL_UNDER ?= 90` is a no-op.
COVERAGE_FAIL_UNDER = 100

# Always include the Rhiza API (template-managed)
include .rhiza/rhiza.mk

# Optional: developer-local extensions (not committed)
-include local.mk
