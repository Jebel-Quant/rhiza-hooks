"""Fuzz the template-bundles parser and validator against arbitrary YAML text.

The ``check-template-bundles`` hook ingests untrusted YAML (a project's
``.rhiza/template.yml`` and the template repository's published bundles), so the
loader and structural validators must never crash on malformed input — they are
contracted to return error strings, not raise. This harness exercises that
contract with coverage-guided input.

Run locally:
    pip install atheris pyyaml
    python tests/fuzz/fuzz_bundles_validate.py -atheris_runs=20000

Run in ClusterFuzzLite: this file is built by .clusterfuzzlite/build.sh.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import atheris

with atheris.instrument_imports():
    from rhiza_hooks._bundles_config import _get_config_data, _get_templates_from_config
    from rhiza_hooks._bundles_validate import validate_template_bundles


def test_one_input(data: bytes) -> None:
    """Exercise the YAML loader, config readers and structural validators."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "template-bundles.yml"
        path.write_bytes(data)

        # Config readers (operate on .rhiza/template.yml-shaped input).
        _get_config_data(path)
        templates = _get_templates_from_config(path)

        # Full validation, both code paths: validate-all and validate-subset.
        # Reuse any template names the input declared so the subset path sees
        # realistic values; fall back to a fixed name otherwise.
        validate_template_bundles(path, None)
        validate_template_bundles(path, templates or {"core"})


def main() -> None:
    """Run the Atheris fuzz loop."""
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
