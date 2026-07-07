#!/usr/bin/env python3
"""Shared helper for loading a YAML file into a top-level mapping.

Every rhiza-hooks entry point that reads a YAML config — the template-bundles
loader (:mod:`rhiza_hooks._bundles_fetch`), the ``.rhiza/template.yml`` reader
(:mod:`rhiza_hooks._bundles_config`), and the rhiza-config checker
(:mod:`rhiza_hooks.check_rhiza_config`) — shares the same open →
``yaml.safe_load`` → "is it a non-empty mapping?" sequence. Only the wording of
their error messages differs. This module centralises that sequence and reports
the failure mode as a small enum so each caller phrases its own message (or,
like :func:`rhiza_hooks._bundles_config._get_config_data`, ignores the reason
and simply treats any failure as "absent").
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class YamlError(Enum):
    """Why a YAML file could not be loaded into a mapping."""

    NOT_FOUND = "not_found"
    INVALID = "invalid"
    EMPTY = "empty"
    NOT_MAPPING = "not_mapping"


@dataclass(frozen=True)
class YamlFailure:
    """A failed :func:`load_yaml_mapping`.

    ``kind`` is the failure mode; ``detail`` carries the parser exception text
    when ``kind`` is :attr:`YamlError.INVALID` (empty otherwise).
    """

    kind: YamlError
    detail: str = ""


def load_yaml_mapping(path: Path) -> dict[Any, Any] | YamlFailure:
    """Load *path* and return its top-level YAML mapping.

    Args:
        path: File to read.

    Returns:
        The parsed mapping on success, or a :class:`YamlFailure` describing why
        the file is missing, unreadable, invalid, empty, or not a mapping.
        Callers ``isinstance``-check the result, which narrows both branches for
        the type checker.
    """
    if not path.exists():
        return YamlFailure(YamlError.NOT_FOUND)
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        return YamlFailure(YamlError.INVALID, str(exc))
    if data is None:
        return YamlFailure(YamlError.EMPTY)
    if not isinstance(data, dict):
        return YamlFailure(YamlError.NOT_MAPPING)
    return data
