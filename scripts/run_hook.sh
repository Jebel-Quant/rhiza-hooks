#!/usr/bin/env bash
#
# Run one of this repo's own console scripts from the working tree, for the
# `repo: local` hooks in .pre-commit-config.yaml.
#
# Why a wrapper rather than an inline entry:
#
#   * `entry: uv run …` breaks in CI. The rhiza Makefile installs uv into
#     ./bin (INSTALL_DIR in .rhiza/rhiza.mk) and invokes it by absolute path,
#     so uv is never on PATH there and pre-commit reports
#     "Executable `uv` not found".
#   * `language: python` with `additional_dependencies: ['.']` cannot work:
#     pre-commit installs from a placeholder package directory inside its own
#     cache, so '.' resolves there instead of to this repo.
#
# So resolve uv the same way the Makefile does — PATH first, then ./bin — and
# let `uv run` supply the project environment (rhiza_hooks needs pyyaml).
# Running through uv is what keeps the hooks pointed at the working tree
# rather than at a cached snapshot of some earlier release.
#
# Usage: scripts/run_hook.sh <console-script> [args...]

set -euo pipefail

if command -v uv >/dev/null 2>&1; then
    uv_bin=uv
elif [ -x "./bin/uv" ]; then
    uv_bin="./bin/uv"
else
    printf 'error: uv not found on PATH or at ./bin/uv\n' >&2
    printf 'hint: run `make install-uv`\n' >&2
    exit 1
fi

exec "$uv_bin" run --quiet --frozen "$@"
