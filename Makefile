## Makefile (repo-owned)
# Keep this file small. It can be edited without breaking template sync.

LOGO_FILE=.rhiza/assets/rhiza-logo.svg

# Override template default: include the mkdocstrings plugin for API docs and
# install this project (src-layout `rhiza_hooks`) into the isolated book-build
# env so `::: rhiza_hooks.*` autodoc blocks can resolve the package.
MKDOCS_EXTRA_PACKAGES = --with 'mkdocstrings[python]' --with .

# Coverage gate: the suite is at 100% line+branch — keep it there. The template
# default is 90 (`COVERAGE_FAIL_UNDER ?= 90` in .rhiza/make.d/test.mk), which
# silently overrode the `fail_under = 100` this repo already declares in
# pyproject.toml, because the make target passes --cov-fail-under explicitly and
# nothing runs a bare `coverage report`.
#
# Must stay above the include: `?=` only takes effect if nothing has set the
# variable yet, so assigning after test.mk is read would be a no-op. `?=` (rather
# than `=`) keeps a CLI override winning, per the template customization contract.
COVERAGE_FAIL_UNDER ?= 100

# Always include the Rhiza API (template-managed)
include .rhiza/rhiza.mk

# Test-layout parity: run the canonical checker (scripts/check_test_layout.py)
# which enforces strict 1:1 source/test mirroring and reads opt-outs from
# [tool.check_test_layout] in pyproject.toml.  The meta/ subtree (which holds
# the checker's own tests) is exempt via exempt_dirs = ["meta"].
# Chained onto `test` (a double-colon rule) so a drift fails CI, not just review.
.PHONY: test-layout
test-layout: ## check source/test layout parity with the canonical checker
	@printf "${BLUE}[INFO] Checking test-layout parity${RESET}\n"
	@$(UV_BIN) run python scripts/check_test_layout.py

test:: test-layout

# Optional: developer-local extensions (not committed)
-include local.mk
