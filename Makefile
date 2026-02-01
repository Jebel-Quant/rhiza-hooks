## Makefile (repo-owned)
# Keep this file small. It can be edited without breaking template sync.

# Project-specific overrides (use override to ensure it takes precedence)
override SOURCE_FOLDER := rhiza_hooks

# Always include the Rhiza API (template-managed)
include .rhiza/rhiza.mk

# Optional: developer-local extensions (not committed)
-include local.mk
