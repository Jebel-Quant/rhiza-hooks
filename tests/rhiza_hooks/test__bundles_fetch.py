"""Tests for the ``rhiza_hooks._bundles_fetch`` module."""

from __future__ import annotations

import dataclasses
import inspect
import time
from http.client import HTTPMessage
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import pytest

from rhiza_hooks import _bundles_fetch
from rhiza_hooks._bundles_fetch import BundlesDoc, fetch_remote_bundles, load_local_bundles

# The URL fetch_remote_bundles builds for repo 'test/repo' on branch 'main'.
_URL = "https://raw.githubusercontent.com/test/repo/main/.rhiza/template-bundles.yml"


def _response(content: bytes) -> MagicMock:
    """Build a context-manager response whose ``read()`` yields ``content``."""
    resp = MagicMock()
    resp.read.return_value = content
    resp.__enter__ = lambda self: self
    resp.__exit__ = lambda self, *args: None
    return resp


def _opener_for(side_effect):
    """Build an ``(opener, calls)`` pair for injection as ``fetch_remote_bundles(opener=...)``.

    ``side_effect`` is handed to a MagicMock, so it can be an exception to raise
    on every attempt or a scripted sequence of per-attempt outcomes. The mock is
    returned alongside so a test can assert how many requests were made, and with
    which URL and timeout.
    """
    calls = MagicMock(side_effect=side_effect)

    def opener(url, *, timeout):
        """Record the request, then return or raise the scripted outcome."""
        return calls(url, timeout=timeout)

    return opener, calls


class TestBundlesDoc:
    """Tests for the BundlesDoc result type."""

    def test_is_frozen(self):
        """BundlesDoc is immutable: attribute assignment raises (pins frozen=True)."""
        doc = BundlesDoc(None, [])
        with pytest.raises(dataclasses.FrozenInstanceError):
            doc.data = {}  # type: ignore[misc]


def test_load_valid_yaml(temp_bundles_file):
    """Test loading valid YAML file."""
    bundles_file = temp_bundles_file("""
        version: 1.0
        bundles: {}
    """)
    result = load_local_bundles(bundles_file)
    assert isinstance(result.data, dict)
    assert result.data["version"] == 1.0
    assert result.errors == []


def test_load_nonexistent_file(tmp_path: Path):
    """Test loading non-existent file reports the exact message."""
    bundles_file = tmp_path / "nonexistent.yml"
    result = load_local_bundles(bundles_file)
    assert result.data is None
    assert result.errors == [f"Template bundles file not found: {bundles_file}"]


def test_load_invalid_yaml(temp_bundles_file):
    """Test loading invalid YAML reports the exact prefix."""
    bundles_file = temp_bundles_file("invalid: yaml: syntax:")
    result = load_local_bundles(bundles_file)
    assert result.data is None
    assert len(result.errors) == 1
    assert result.errors[0].startswith("Invalid YAML: ")


def test_load_empty_file(temp_bundles_file):
    """Test loading empty file reports the exact message."""
    bundles_file = temp_bundles_file("")
    result = load_local_bundles(bundles_file)
    assert result.data is None
    assert result.errors == ["Template bundles file is empty"]


def test_load_non_utf8_file(tmp_path: Path):
    """A non-UTF-8 file is reported, not crashed on (fuzzing regression)."""
    bundles_file = tmp_path / "bad-encoding.yml"
    bundles_file.write_bytes(b"\xb5\n")
    result = load_local_bundles(bundles_file)
    assert result.data is None
    assert len(result.errors) == 1
    assert result.errors[0].startswith("Invalid YAML: ")


@pytest.mark.parametrize("scalar", ["5", "just a string", "[1, 2, 3]"])
def test_load_non_dict_document(temp_bundles_file, scalar):
    """A YAML document that isn't a mapping is reported, not crashed on (fuzzing regression)."""
    result = load_local_bundles(temp_bundles_file(scalar))
    assert result.data is None
    assert result.errors == ["Template bundles file must be a dictionary"]


def test_fetch_remote_bundles_http_404():
    """Test fetching remote bundles returns 404 error."""
    opener, _calls = _opener_for(HTTPError(_URL, 404, "Not Found", HTTPMessage(), BytesIO(b"")))

    result = fetch_remote_bundles("test/repo", "main", opener=opener)
    assert result.data is None
    assert result.errors == ["Template bundles file not found in repository test/repo (branch: main)"]


def test_fetch_remote_bundles_http_error_non_404():
    """Test fetching remote bundles with non-404 HTTP error."""
    opener, _calls = _opener_for(HTTPError(_URL, 500, "Internal Server Error", HTTPMessage(), BytesIO(b"")))

    result = fetch_remote_bundles("test/repo", "main", opener=opener)
    assert result.data is None
    assert result.errors == ["HTTP error fetching template bundles: 500 Internal Server Error"]


def test_fetch_remote_bundles_url_error(monkeypatch):
    """A persistent URL error gives up after the default attempts, retrying once."""
    opener, calls = _opener_for(URLError("Connection refused"))
    sleep = MagicMock()
    monkeypatch.setattr(time, "sleep", sleep)

    result = fetch_remote_bundles("test/repo", "main", opener=opener)
    assert result.data is None
    assert result.errors == [f"Error fetching template bundles from {_URL}: Connection refused"]
    # Default = 2 attempts (1 retry): two requests, one backoff sleep of 1.0s.
    assert calls.call_count == 2
    assert sleep.call_args_list == [((1.0,), {})]


def test_fetch_remote_bundles_timeout(monkeypatch):
    """A persistent timeout gives up after the default attempts with the exact message."""
    opener, calls = _opener_for(TimeoutError("Timeout"))
    sleep = MagicMock()
    monkeypatch.setattr(time, "sleep", sleep)

    result = fetch_remote_bundles("test/repo", "main", opener=opener)
    assert result.data is None
    assert result.errors == [f"Timeout fetching template bundles from {_URL}"]
    assert calls.call_count == 2
    assert sleep.call_args_list == [((1.0,), {})]


def test_fetch_remote_bundles_retry_then_success(monkeypatch):
    """A transient failure followed by success returns the parsed data after one retry."""
    opener, calls = _opener_for([URLError("flaky"), _response(b"version: 1.0\nbundles: {}")])
    sleep = MagicMock()
    monkeypatch.setattr(time, "sleep", sleep)

    result = fetch_remote_bundles("test/repo", "main", opener=opener)
    assert result.data == {"version": 1.0, "bundles": {}}
    assert result.errors == []
    assert calls.call_count == 2
    assert sleep.call_args_list == [((1.0,), {})]


def test_fetch_remote_bundles_backoff_schedule(monkeypatch):
    """Backoff is linear (backoff, 2*backoff, ...) and the last attempt does not sleep."""
    opener, calls = _opener_for(URLError("down"))
    sleep = MagicMock()
    monkeypatch.setattr(time, "sleep", sleep)

    result = fetch_remote_bundles("test/repo", "main", attempts=3, backoff=2.0, opener=opener)
    assert result.data is None
    # 3 attempts -> 2 sleeps between them: 2.0 then 4.0. No sleep after the final attempt.
    assert calls.call_count == 3
    assert sleep.call_args_list == [((2.0,), {}), ((4.0,), {})]


def test_fetch_remote_bundles_invalid_yaml():
    """Test fetching remote bundles with invalid YAML."""
    opener, _calls = _opener_for([_response(b"invalid: yaml: syntax:")])

    result = fetch_remote_bundles("test/repo", "main", opener=opener)
    assert result.data is None
    assert len(result.errors) == 1
    assert result.errors[0].startswith("Invalid YAML in remote template bundles: ")


def test_fetch_remote_bundles_empty_file():
    """Test fetching remote bundles with empty file."""
    opener, _calls = _opener_for([_response(b"")])

    result = fetch_remote_bundles("test/repo", "main", opener=opener)
    assert result.data is None
    assert result.errors == ["Remote template bundles file is empty"]


def test_fetch_remote_bundles_not_dict():
    """Test fetching remote bundles that's not a dictionary."""
    opener, _calls = _opener_for([_response(b"- item1\n- item2")])

    result = fetch_remote_bundles("test/repo", "main", opener=opener)
    assert result.data is None
    assert result.errors == ["Remote template bundles must be a dictionary"]


def test_fetch_remote_bundles_url_is_https():
    """The URL handed to the opener is https, whatever the repo and branch contain.

    Replaces a former ``test_fetch_remote_bundles_invalid_scheme`` (#340), which could
    only reach the deleted ``urlparse`` guard by monkeypatching this module's
    ``urlparse`` — it pinned the implementation of an unreachable branch. This asserts
    the property that guard was reaching for, through the public arguments: the scheme
    is a literal prefix, so no interpolated value can move the request off https.
    """
    opener, calls = _opener_for([_response(b"version: 1.0\nbundles: {}")])

    result = fetch_remote_bundles("../../evil", "http://elsewhere", opener=opener)
    assert result.errors == []
    assert calls.call_args.args[0].startswith("https://raw.githubusercontent.com/")


def test_fetch_remote_bundles_success():
    """A successful fetch parses the document and requests the expected URL and timeout."""
    body = b"version: 1.0\nbundles:\n  core:\n    description: Core\n    files:\n      - .gitignore"
    opener, calls = _opener_for([_response(body)])

    result = fetch_remote_bundles("test/repo", "main", opener=opener)
    assert isinstance(result.data, dict)
    assert "version" in result.data
    assert "bundles" in result.data
    assert result.errors == []
    # Pin the URL and the default timeout so a mutated value is caught.
    assert calls.call_args_list == [((_URL,), {"timeout": 10.0})]


def test_fetch_remote_bundles_custom_timeout():
    """A custom timeout is forwarded to the opener verbatim."""
    opener, calls = _opener_for([_response(b"version: 1.0\nbundles: {}")])

    fetch_remote_bundles("test/repo", "main", timeout=42.5, opener=opener)
    assert calls.call_args.kwargs["timeout"] == 42.5


def test_fetch_remote_bundles_no_retries(monkeypatch):
    """attempts=1 makes a single request and never sleeps."""
    opener, calls = _opener_for(URLError("down"))
    sleep = MagicMock()
    monkeypatch.setattr(time, "sleep", sleep)

    result = fetch_remote_bundles("test/repo", "main", attempts=1, opener=opener)
    assert result.data is None
    assert calls.call_count == 1
    assert sleep.call_args_list == []


def test_fetch_remote_bundles_logs_each_attempt(monkeypatch, capsys):
    """Every failed attempt is logged; retried ones mention the backoff delay."""
    opener, _calls = _opener_for(URLError("down"))
    monkeypatch.setattr(time, "sleep", MagicMock())

    fetch_remote_bundles("test/repo", "main", attempts=2, backoff=1.0, opener=opener)
    captured = capsys.readouterr()
    out = captured.err
    assert captured.out == ""  # retry diagnostics are stderr-only
    assert "Attempt 1/2 failed" in out
    assert "retrying in 1.0s" in out
    # The final attempt is logged but has nothing to retry.
    assert "Attempt 2/2 failed" in out
    assert "Attempt 2/2 failed: " in out
    assert out.count("retrying in") == 1


class Test_Opener:  # noqa: N801  # name mandated by check_test_layout.py (mirrors source class `_Opener`)
    """Tests for the injected opener protocol."""

    def test_defaults_to_urlopen(self):
        """The opener defaults to urlopen, so production callers need not pass one."""
        assert inspect.signature(fetch_remote_bundles).parameters["opener"].default is urlopen

    def test_urlopen_satisfies_the_protocol(self):
        """Urlopen is accepted where an _Opener is expected — the seam matches the real callable."""
        opener: _bundles_fetch._Opener = urlopen
        assert callable(opener)


class TestFetcher:
    """Tests for the injected fetcher protocol — the same seam one layer up."""

    def test_fetch_remote_bundles_satisfies_the_protocol(self):
        """The real fetcher is accepted where a Fetcher is expected."""
        fetcher: _bundles_fetch.Fetcher = fetch_remote_bundles
        assert callable(fetcher)

    def test_protocol_call_accepts_the_shape_main_uses(self):
        """The protocol's __call__ names exactly the arguments ``check_template_bundles`` passes.

        The orchestration layer calls ``fetcher(repo, branch, attempts=..., timeout=...)``.
        Pinning that here means a change to either side that leaves them disagreeing is a
        test failure rather than a TypeError at the first real fetch.
        """
        params = inspect.signature(_bundles_fetch.Fetcher.__call__).parameters
        assert list(params) == ["self", "repo", "branch", "attempts", "timeout"]
        assert params["attempts"].kind is inspect.Parameter.KEYWORD_ONLY
        assert params["timeout"].kind is inspect.Parameter.KEYWORD_ONLY
