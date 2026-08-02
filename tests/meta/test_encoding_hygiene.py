r"""Every text-mode file access in the shipped code names its encoding.

A hook runs on other people's machines. When ``open()``/``read_text()``/``write_text()``
is called without ``encoding=``, Python uses the platform default — UTF-8 on Linux and
macOS, cp1252 on a stock Windows install. A ``Makefile``, ``README.md`` or ``go.mod``
holding one accented word or em dash then raises ``UnicodeDecodeError``, and the hook
crashes mid-commit instead of reporting a result. That is a bug the developer's own
machine cannot reproduce.

Issue #312 fixed seven such calls by hand, found with
``grep -rn 'read_text(\\|write_text(' src/rhiza_hooks/*.py``. That grep missed
``open()`` entirely (three calls in ``check_workflow_names.py``) and never looked at
``scripts/`` — where ``check_test_layout.py`` read every test file in the repo with the
platform default and broke the Windows CI job the moment a test file contained an em
dash. This test replaces the grep with an AST walk so the invariant holds by
construction rather than by having remembered to re-run a one-off command.

**Scope: ``src/`` and ``scripts/``** — the code that ships and the code CI runs. Tests
are excluded deliberately: they write ASCII fixtures into ``tmp_path`` and read them
back through the same default, so the two cancel out, and holding ~100 fixture writes
to the rule would obscure the calls that actually matter. A test that *does* care about
encoding says so explicitly (see ``write_bytes`` in ``test__makefile.py``).

Binary mode is exempt — ``open(p, "rb")`` has no encoding to name, and passing one is a
``TypeError``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Directories holding code that runs on a machine we do not control.
_SCANNED_DIRS = ("src", "scripts")

# Call names that open a file. ``open`` is the builtin; the other two are the
# ``pathlib.Path`` conveniences. All three take ``encoding=`` in text mode.
_TEXT_IO_NAMES = frozenset({"open", "read_text", "write_text"})


def _called_name(node: ast.Call) -> str | None:
    """Return the bare name a call resolves to: ``f(...)`` or ``x.f(...)`` alike."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_binary_mode(node: ast.Call) -> bool:
    """Report whether the call opens in binary mode, where ``encoding=`` is invalid.

    The mode is the sole positional argument of ``Path.open`` and the second of the
    builtin ``open``; either way it is the first string literal among the positionals,
    so both spellings are covered without tracking which callable is in play.
    """
    literals = (arg.value for arg in node.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str))
    return any("b" in mode for mode in literals)


def _names_encoding(node: ast.Call) -> bool:
    """Report whether the call passes ``encoding=`` — or forwards ``**kwargs`` that may."""
    return any(kw.arg == "encoding" or kw.arg is None for kw in node.keywords)


def _offences(path: Path) -> list[int]:
    """Return the line of every text-mode call in *path* that omits an encoding."""
    tree = ast.parse(path.read_bytes(), filename=str(path))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _called_name(node) in _TEXT_IO_NAMES
        and not _is_binary_mode(node)
        and not _names_encoding(node)
    ]


def _python_sources() -> list[Path]:
    """Return every ``.py`` file under the scanned directories."""
    return sorted(p for directory in _SCANNED_DIRS for p in (_REPO_ROOT / directory).rglob("*.py"))


def test_scanned_dirs_are_populated() -> None:
    """Guard the guard: an empty file list would make the invariant vacuously true."""
    assert len(_python_sources()) > 1


def test_no_text_io_without_encoding() -> None:
    """No shipped call opens a file in text mode without naming its encoding."""
    offences = [
        f"{path.relative_to(_REPO_ROOT).as_posix()}:{line}" for path in _python_sources() for line in _offences(path)
    ]
    assert offences == [], "text-mode file access without encoding=: " + ", ".join(offences)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('open("f")', 1),
        ('open("f", "w")', 1),
        ("p.read_text()", 1),
        ("p.write_text(x)", 1),
        ('open("f", "rb")', 0),
        ('p.open("rb")', 0),
        ('open("f", encoding="utf-8")', 0),
        ('p.read_text(encoding="utf-8")', 0),
        ('open("f", **kwargs)', 0),
        ('other("f")', 0),
        ("obj.method()()", 0),
    ],
)
def test_detector_classifies_each_call_shape(tmp_path: Path, source: str, expected: int) -> None:
    """The detector flags exactly the text-mode calls that omit an encoding.

    ``obj.method()()`` covers a call whose ``func`` is neither a Name nor an Attribute,
    which has no resolvable name and must not be mistaken for file access.
    """
    module = tmp_path / "sample.py"
    module.write_text(source + "\n", encoding="utf-8")
    assert len(_offences(module)) == expected
