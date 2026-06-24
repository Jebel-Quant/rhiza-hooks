#!/bin/bash -eu
# ClusterFuzzLite build script — installs rhiza_hooks and compiles each Python
# harness in tests/fuzz/ via OSS-Fuzz's compile_python_fuzzer helper.

cd "$SRC/rhiza-hooks"

# Install the package and its runtime dependencies (e.g. PyYAML) into the build
# environment so PyInstaller can discover and bundle rhiza_hooks into each
# frozen fuzzer binary. Without this, the harness would fail to import
# rhiza_hooks at runtime inside the ClusterFuzzLite runner.
pip3 install .

for fuzzer in tests/fuzz/fuzz_*.py; do
  compile_python_fuzzer "$fuzzer"
done
