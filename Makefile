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

# Test-layout parity: this repo keeps tests flat under tests/ by *concern* rather
# than mirroring src/rhiza_hooks/ 1:1, so scripts/check_test_layout.py enforces
# the property that actually matters here — every source module is covered by at
# least one test file, and every tests/test_*.py traces back to a package module
# or is an allowed repository meta-test.
#
# The checker is vendored deliberately (the same pattern basanos uses): the
# template does not ship one, so a repo that wants this as a gate keeps its own
# tailored copy. It has 6 tests of its own in tests/test_check_test_layout.py.
# Chained onto `test` (a double-colon rule) so a drift fails CI, not just review —
# previously nothing invoked it at all.
.PHONY: test-layout
test-layout: ## check source modules are tested and tests trace back to code
	@printf "${BLUE}[INFO] Checking test-layout parity${RESET}\n"
	@$(UV_BIN) run python scripts/check_test_layout.py

test:: test-layout

# Optional: developer-local extensions (not committed)
-include local.mk
