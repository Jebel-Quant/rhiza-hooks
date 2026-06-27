## Makefile (repo-owned)
# Keep this file small. It can be edited without breaking template sync.

LOGO_FILE=.rhiza/assets/rhiza-logo.svg

# Override template default: include the mkdocstrings plugin for API docs and
# install this project (src-layout `rhiza_hooks`) into the isolated book-build
# env so `::: rhiza_hooks.*` autodoc blocks can resolve the package.
MKDOCS_EXTRA_PACKAGES = --with 'mkdocstrings[python]' --with .

# Always include the Rhiza API (template-managed)
include .rhiza/rhiza.mk

# Optional: developer-local extensions (not committed)
-include local.mk
