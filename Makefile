## Makefile (repo-owned)
# Keep this file small. It can be edited without breaking template sync.

DEFAULT_AI_MODEL=claude-sonnet-4.6
LOGO_FILE=.rhiza/assets/rhiza-logo.svg
GH_AW_ENGINE ?= copilot  # Default AI engine for gh-aw workflows (copilot, claude, or codex)

# Override template default: include the mkdocstrings plugin for API docs and
# install this project (src-layout `rhiza_hooks`) into the isolated book-build
# env so `::: rhiza_hooks.*` autodoc blocks can resolve the package.
MKDOCS_EXTRA_PACKAGES = --with 'mkdocstrings[python]' --with .

# Always include the Rhiza API (template-managed)
include .rhiza/rhiza.mk

# Optional: developer-local extensions (not committed)
-include local.mk
