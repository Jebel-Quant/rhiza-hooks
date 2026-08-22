r"""Every text-mode file access in the shipped code names its encoding and line endings.

A hook runs on other people's machines, so both halves of text-mode decoding have to be
stated rather than inherited from the platform.

**``encoding=``.** When ``open()``/``read_text()``/``write_text()`` is called without it,
Python uses the platform default — UTF-8 on Linux and macOS, cp1252 on a stock Windows
install. A ``Makefile``, ``README.md`` or ``go.mod`` holding one accented word or em dash
then raises ``UnicodeDecodeError``, and the hook crashes mid-commit instead of reporting
a result. That is a bug the developer's own machine cannot reproduce.

Issue #312 fixed seven such calls by hand, found with
``grep -rn 'read_text(\\|write_text(' src/rhiza_hooks/*.py``. That grep missed
``open()`` entirely (three calls in ``check_workflow_names.py``) and never looked at
``scripts/`` — where ``check_test_layout.py`` read every test file in the repo with the
platform default and broke the Windows CI job the moment a test file contained an em
dash. This test replaces the grep with an AST walk so the invariant holds by
construction rather than by having remembered to re-run a one-off command. (That module
now lives in the package as ``rhiza_hooks.check_test_layout``, so it is covered by the
``src/`` walk; the story is kept because it is why the walk exists.)

**``newline=`` on writes.** A text-mode write with the default ``newline=None``
translates every ``\n`` to ``os.linesep``. Since content reaches a write already
LF-normalised — universal-newline reads and ``subprocess(text=True)`` both hand back
``\n`` — that turns an auto-fixing hook's one-line edit into a whole-file CRLF diff on
Windows, against the ``end_of_line = lf`` this repo declares in ``.editorconfig``.
Pinning ``newline=""`` makes a hook's output a function of its input alone: identical
bytes on every platform. Issue #320; the two write sites it names are
``check_workflow_names._rewrite_workflow_name`` and
``update_readme_help.update_readme_with_help``.

Reads are exempt from the ``newline=`` rule on purpose. A universal-newline read
*normalises* to ``\n``, which is what the parsing code downstream wants; it is only the
write side where the translation is unwanted.

This static check is the platform-independent half of #320. Its runtime counterparts
(``test_lf_line_endings_survive_the_rewrite`` in ``test_check_workflow_names`` and
``test_update_readme_help``) assert on real bytes but can only fail on the Windows CI
leg, since ``os.linesep`` is already ``\n`` elsewhere — so a regression on a
contributor's Mac would be invisible without the walk below.

**Scope: ``src/``** — the code that ships. Tests
are excluded deliberately: they write ASCII fixtures into ``tmp_path`` and read them
back through the same default, so the two cancel out, and holding ~100 fixture writes
to the rule would obscure the calls that actually matter. A test that *does* care about
encoding or line endings says so explicitly (see ``write_bytes`` in ``test__makefile.py``
and the two byte-level tests named above).

Binary mode is exempt from both rules — ``open(p, "rb")`` has no encoding to name and
performs no newline translation, and passing either keyword is a ``TypeError``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Directories holding code that runs on a machine we do not control. ``scripts/`` was
# here until check_test_layout.py moved into the package (#328) and left it with no
# Python at all; a scanned directory that holds nothing contributes nothing but the
# appearance of coverage, which is what the per-directory guard below now catches.
_SCANNED_DIRS = ("src",)

# Call names that open a file. ``open`` is the builtin; the other two are the
# ``pathlib.Path`` conveniences. All three take ``encoding=`` in text mode.
_TEXT_IO_NAMES = frozenset({"open", "read_text", "write_text"})

# Mode characters that create, extend or truncate a file. ``+`` counts: ``r+`` is a
# read-write handle, so a ``\n`` written through it is translated like any other.
_WRITE_MODE_CHARS = frozenset("wax+")


def _called_name(node: ast.Call) -> str | None:
    """Return the bare name a call resolves to: ``f(...)`` or ``x.f(...)`` alike."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _mode(node: ast.Call) -> str | None:
    """Return the mode an ``open`` call names, or ``None`` when it names none.

    Which positional holds the mode depends on which ``open`` is in play: the builtin
    takes the path first and the mode second, while ``Path.open`` takes the mode first.
    The two are told apart by the call's shape — ``open(...)`` parses to a ``Name`` and
    ``p.open(...)`` to an ``Attribute``. Scanning "whichever positional happens to be a
    string literal" instead would read the *filename* of ``open("f", "w")`` as its mode.

    Only ``open`` is consulted. ``read_text``/``write_text`` take no mode, and *their*
    first positional is the payload — so ``write_text("debug")`` would otherwise look
    like it named binary mode and be quietly exempted from both rules.
    """
    func = node.func
    if isinstance(func, ast.Name) and func.id == "open":
        index = 1  # open(path, mode)
    elif isinstance(func, ast.Attribute) and func.attr == "open":
        index = 0  # path.open(mode)
    else:
        return None

    if len(node.args) > index:
        arg = node.args[index]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def _is_binary_mode(node: ast.Call) -> bool:
    """Report whether the call opens in binary mode, where the keywords are invalid."""
    mode = _mode(node)
    return mode is not None and "b" in mode


def _is_write(node: ast.Call) -> bool:
    """Report whether the call opens a file for writing.

    ``write_text`` always writes. An ``open`` writes when its mode names one of
    ``w``/``a``/``x``/``+``; naming no mode at all means the ``"r"`` default, a read.
    """
    if _called_name(node) == "write_text":
        return True
    mode = _mode(node)
    return mode is not None and bool(_WRITE_MODE_CHARS & set(mode))


def _names(node: ast.Call, keyword: str) -> bool:
    """Report whether the call passes *keyword* — or forwards ``**kwargs`` that may."""
    return any(kw.arg == keyword or kw.arg is None for kw in node.keywords)


def _text_io_calls(path: Path) -> list[ast.Call]:
    """Return every text-mode file-access call in *path*."""
    tree = ast.parse(path.read_bytes(), filename=str(path))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _called_name(node) in _TEXT_IO_NAMES and not _is_binary_mode(node)
    ]


def _offences(path: Path) -> list[int]:
    """Return the line of every text-mode call in *path* that omits an encoding."""
    return [call.lineno for call in _text_io_calls(path) if not _names(call, "encoding")]


def _newline_offences(path: Path) -> list[int]:
    """Return the line of every text-mode write in *path* that omits ``newline=``."""
    return [call.lineno for call in _text_io_calls(path) if _is_write(call) and not _names(call, "newline")]


def _python_sources() -> list[Path]:
    """Return every ``.py`` file under the scanned directories."""
    return sorted(p for directory in _SCANNED_DIRS for p in (_REPO_ROOT / directory).rglob("*.py"))


@pytest.mark.parametrize("directory", _SCANNED_DIRS)
def test_scanned_dir_is_populated(directory: str) -> None:
    """Guard the guard: an empty file list would make the invariant vacuously true.

    Parametrized per directory rather than asserting on the total. A single
    ``len(_python_sources()) > 1`` is satisfied by whichever entry is largest, so
    ``src/``'s two dozen modules masked ``scripts/`` going empty (#363) — the exact
    vacuous-scope failure this test exists to prevent, one level up. Anything added
    to ``_SCANNED_DIRS`` that does not exist, or holds no Python, now fails here.
    """
    assert list((_REPO_ROOT / directory).rglob("*.py")), f"{directory}/ holds no Python"


def test_no_text_io_without_encoding() -> None:
    """No shipped call opens a file in text mode without naming its encoding."""
    offences = [
        f"{path.relative_to(_REPO_ROOT).as_posix()}:{line}" for path in _python_sources() for line in _offences(path)
    ]
    assert offences == [], "text-mode file access without encoding=: " + ", ".join(offences)


def test_no_text_write_without_newline() -> None:
    """No shipped call writes a file in text mode without pinning its line endings."""
    offences = [
        f"{path.relative_to(_REPO_ROOT).as_posix()}:{line}"
        for path in _python_sources()
        for line in _newline_offences(path)
    ]
    assert offences == [], 'text-mode write without newline="": ' + ", ".join(offences)


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
        # The data argument of a write_text is not a mode: a payload containing "b" must
        # not exempt the call the way open(p, "rb") legitimately is.
        ('p.write_text("debug")', 1),
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


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # Writes that leave the translation to the platform.
        ('open("f", "w", encoding="utf-8")', 1),
        ('open("f", "a", encoding="utf-8")', 1),
        ('open("f", "r+", encoding="utf-8")', 1),
        ('open("f", mode="w", encoding="utf-8")', 1),
        ('p.open("w", encoding="utf-8")', 1),
        ('p.write_text(x, encoding="utf-8")', 1),
        # Writes that pin it.
        ('open("f", "w", encoding="utf-8", newline="")', 0),
        ('p.write_text(x, encoding="utf-8", newline="")', 0),
        ("p.write_text(x, **kwargs)", 0),
        # Reads: a universal-newline read normalises to \n, which is wanted.
        ('open("f", encoding="utf-8")', 0),
        ('open("f", "r", encoding="utf-8")', 0),
        ("p.read_text()", 0),
        # Binary mode translates nothing, and newline= would be a TypeError.
        ('open("f", "wb")', 0),
        ('p.open("ab")', 0),
        # Not file access at all.
        ('other("f", "w")', 0),
    ],
)
def test_newline_detector_classifies_each_write_shape(tmp_path: Path, source: str, expected: int) -> None:
    """The write detector flags exactly the text-mode writes that omit ``newline=``."""
    module = tmp_path / "sample.py"
    module.write_text(source + "\n", encoding="utf-8")
    assert len(_newline_offences(module)) == expected
