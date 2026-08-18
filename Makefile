## Makefile (repo-owned)
# Keep this file small. It can be edited without breaking template sync.

# Override template default: include the mkdocstrings plugin for API docs and
# install this project (src-layout `rhiza_hooks`) into the isolated book-build
# env so `::: rhiza_hooks.*` autodoc blocks can resolve the package.
MKDOCS_EXTRA_PACKAGES = --with 'mkdocstrings[python]' --with .

# prek (https://github.com/j178/prek) replaces pre-commit as the hook runner: a
# single Rust binary, no Python env to bootstrap, and it reads the very same
# .pre-commit-config.yaml and .pre-commit-hooks.yaml. Measured on this repo:
# 1.6s warm / 14.8s cold, against pre-commit's 11.5s warm — all 28 hooks pass
# identically, including the `language: fail`/`system`/`script` local blocks.
#
# Pinned rather than floating so a prek regression cannot break `make fmt` for
# everyone at once; bump deliberately.
#
# NOTE the config stays strictly pre-commit-compatible (no prek.toml). This repo
# publishes .pre-commit-hooks.yaml to ~26 downstream pre-commit consumers, and
# tests/meta/test_pre_commit_template_parity.py diffs hook ids against the
# template's YAML. prek here is a local runner swap, not a format migration.
PREK_VERSION ?= 0.4.12

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

# Run the hooks with prek instead of pre-commit.
#
# This deliberately overrides `fmt` from .rhiza/make.d/quality.mk, which is
# Rhiza-owned and cannot be edited here. The override must sit BELOW the include
# (make takes the last recipe defined for a target), which is the mirror image of
# the COVERAGE_FAIL_UNDER note above: variables need `?=` before, recipes need to
# come after. Cost of doing it this way: make prints one
#   warning: overriding recipe for target 'fmt'
# on every invocation. That is the price of a local-only switch; it disappears
# once quality.mk itself moves to prek upstream in jebel-quant/rhiza.
#
# `${UVX_BIN}` rather than a bare `uvx` for the reason scripts/run_hook.sh
# documents: the rhiza Makefile installs uv into ./bin and never puts it on PATH.
#
# No `##` help text on purpose: `make help` awks over every file in
# MAKEFILE_LIST, so a second annotated `fmt:` would list the target twice. The
# entry under "Quality and Formatting" (quality.mk's) is the one that shows.
.PHONY: fmt
fmt: install-uv
	@printf "${BLUE}[INFO] Running hooks with prek ${PREK_VERSION}${RESET}\n"
	@${UVX_BIN} prek@${PREK_VERSION} run --all-files

# Point the installed git hook at prek too.
#
# `make install` (python.mk, Rhiza-owned) runs `pre-commit install` and only then
# calls `$(MAKE) post-install`, so this double-colon hook lands last and its
# .git/hooks/pre-commit wins. Using the sanctioned extension point rather than a
# second override keeps this half warning-free.
post-install::
	@if [ -z "$$(git config --get core.hooksPath 2>/dev/null)" ]; then \
	  printf "${BLUE}[INFO] Installing git hooks with prek ${PREK_VERSION}${RESET}\n"; \
	  ${UVX_BIN} prek@${PREK_VERSION} install --force \
	    || printf "${YELLOW}[WARN] Failed to install prek hooks${RESET}\n"; \
	fi

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
