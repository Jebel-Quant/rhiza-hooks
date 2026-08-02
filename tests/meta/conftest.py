"""Pytest configuration for the ``meta`` test tree.

The scripts under ``scripts/`` are standalone utilities, not an installed
package, so this conftest adds that directory to ``sys.path`` to make
``import check_test_layout`` available within the ``meta/`` test subtree.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
