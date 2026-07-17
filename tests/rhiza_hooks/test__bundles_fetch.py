"""Tests for the ``rhiza_hooks._bundles_fetch`` module."""

from __future__ import annotations

from pathlib import Path

import pytest

from rhiza_hooks._bundles_fetch import BundlesDoc, load_local_bundles


class TestBundlesDoc:
    """Tests for the BundlesDoc result type."""

    def test_is_frozen(self):
        """BundlesDoc is immutable: attribute assignment raises (pins frozen=True)."""
        import dataclasses

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


def test_fetch_remote_bundles_http_404(monkeypatch):
    """Test fetching remote bundles returns 404 error."""
    from http.client import HTTPMessage
    from io import BytesIO
    from urllib.error import HTTPError

    from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

    def mock_urlopen(url, timeout):
        """Raise an HTTP 404 error in place of opening the URL."""
        headers = HTTPMessage()
        raise HTTPError(url, 404, "Not Found", headers, BytesIO(b""))

    monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)

    result = _fetch_remote_bundles("test/repo", "main")
    assert result.data is None
    assert result.errors == ["Template bundles file not found in repository test/repo (branch: main)"]


def test_fetch_remote_bundles_http_error_non_404(monkeypatch):
    """Test fetching remote bundles with non-404 HTTP error."""
    from http.client import HTTPMessage
    from io import BytesIO
    from urllib.error import HTTPError

    from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

    def mock_urlopen(url, timeout):
        """Raise an HTTP 500 error in place of opening the URL."""
        headers = HTTPMessage()
        raise HTTPError(url, 500, "Internal Server Error", headers, BytesIO(b""))

    monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)

    result = _fetch_remote_bundles("test/repo", "main")
    assert result.data is None
    assert result.errors == ["HTTP error fetching template bundles: 500 Internal Server Error"]


def test_fetch_remote_bundles_url_error(monkeypatch):
    """A persistent URL error gives up after the default attempts, retrying once."""
    from unittest.mock import MagicMock
    from urllib.error import URLError

    from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

    calls = MagicMock(side_effect=URLError("Connection refused"))

    def mock_urlopen(url, timeout):
        """Delegate to the mock that always raises a URLError."""
        return calls(url, timeout)

    sleep = MagicMock()
    monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)
    monkeypatch.setattr("rhiza_hooks._bundles_fetch.time.sleep", sleep)

    result = _fetch_remote_bundles("test/repo", "main")
    assert result.data is None
    url = "https://raw.githubusercontent.com/test/repo/main/.rhiza/template-bundles.yml"
    assert result.errors == [f"Error fetching template bundles from {url}: Connection refused"]
    # Default = 2 attempts (1 retry): urlopen twice, one backoff sleep of 1.0s.
    assert calls.call_count == 2
    assert sleep.call_args_list == [((1.0,), {})]


def test_fetch_remote_bundles_timeout(monkeypatch):
    """A persistent timeout gives up after the default attempts with the exact message."""
    from unittest.mock import MagicMock

    from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

    calls = MagicMock(side_effect=TimeoutError("Timeout"))

    def mock_urlopen(url, timeout):
        """Delegate to the mock that always raises a TimeoutError."""
        return calls(url, timeout)

    sleep = MagicMock()
    monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)
    monkeypatch.setattr("rhiza_hooks._bundles_fetch.time.sleep", sleep)

    result = _fetch_remote_bundles("test/repo", "main")
    assert result.data is None
    url = "https://raw.githubusercontent.com/test/repo/main/.rhiza/template-bundles.yml"
    assert result.errors == [f"Timeout fetching template bundles from {url}"]
    assert calls.call_count == 2
    assert sleep.call_args_list == [((1.0,), {})]


def test_fetch_remote_bundles_retry_then_success(monkeypatch):
    """A transient failure followed by success returns the parsed data after one retry."""
    from unittest.mock import MagicMock
    from urllib.error import URLError

    from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

    def make_response():
        """Build a context-manager response yielding minimal valid bundles YAML."""
        resp = MagicMock()
        resp.read.return_value = b"version: 1.0\nbundles: {}"
        resp.__enter__ = lambda self: self
        resp.__exit__ = lambda self, *args: None
        return resp

    calls = MagicMock(side_effect=[URLError("flaky"), make_response()])

    def mock_urlopen(url, timeout):
        """Delegate to the mock that fails once then returns a response."""
        return calls(url, timeout)

    sleep = MagicMock()
    monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)
    monkeypatch.setattr("rhiza_hooks._bundles_fetch.time.sleep", sleep)

    result = _fetch_remote_bundles("test/repo", "main")
    assert result.data == {"version": 1.0, "bundles": {}}
    assert result.errors == []
    assert calls.call_count == 2
    assert sleep.call_args_list == [((1.0,), {})]


def test_fetch_remote_bundles_backoff_schedule(monkeypatch):
    """Backoff is linear (backoff, 2*backoff, ...) and the last attempt does not sleep."""
    from unittest.mock import MagicMock
    from urllib.error import URLError

    from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

    calls = MagicMock(side_effect=URLError("down"))

    def mock_urlopen(url, timeout):
        """Delegate to the mock that always raises a URLError for backoff testing."""
        return calls(url, timeout)

    sleep = MagicMock()
    monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)
    monkeypatch.setattr("rhiza_hooks._bundles_fetch.time.sleep", sleep)

    result = _fetch_remote_bundles("test/repo", "main", attempts=3, backoff=2.0)
    assert result.data is None
    # 3 attempts -> 2 sleeps between them: 2.0 then 4.0. No sleep after the final attempt.
    assert calls.call_count == 3
    assert sleep.call_args_list == [((2.0,), {}), ((4.0,), {})]


def test_fetch_remote_bundles_invalid_yaml(monkeypatch):
    """Test fetching remote bundles with invalid YAML."""
    from unittest.mock import MagicMock

    from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

    def mock_urlopen(url, timeout):
        """Return a response yielding malformed YAML content."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"invalid: yaml: syntax:"
        mock_response.__enter__ = lambda self: self
        mock_response.__exit__ = lambda self, *args: None
        return mock_response

    monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)

    result = _fetch_remote_bundles("test/repo", "main")
    assert result.data is None
    assert len(result.errors) == 1
    assert result.errors[0].startswith("Invalid YAML in remote template bundles: ")


def test_fetch_remote_bundles_empty_file(monkeypatch):
    """Test fetching remote bundles with empty file."""
    from unittest.mock import MagicMock

    from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

    def mock_urlopen(url, timeout):
        """Return a response yielding empty content."""
        mock_response = MagicMock()
        mock_response.read.return_value = b""
        mock_response.__enter__ = lambda self: self
        mock_response.__exit__ = lambda self, *args: None
        return mock_response

    monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)

    result = _fetch_remote_bundles("test/repo", "main")
    assert result.data is None
    assert result.errors == ["Remote template bundles file is empty"]


def test_fetch_remote_bundles_not_dict(monkeypatch):
    """Test fetching remote bundles that's not a dictionary."""
    from unittest.mock import MagicMock

    from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

    def mock_urlopen(url, timeout):
        """Return a response yielding a YAML list rather than a mapping."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"- item1\n- item2"
        mock_response.__enter__ = lambda self: self
        mock_response.__exit__ = lambda self, *args: None
        return mock_response

    monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)

    result = _fetch_remote_bundles("test/repo", "main")
    assert result.data is None
    assert result.errors == ["Remote template bundles must be a dictionary"]


def test_fetch_remote_bundles_invalid_scheme(monkeypatch):
    """Test fetching remote bundles with invalid URL scheme."""
    from urllib.parse import ParseResult

    from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

    def mock_urlparse(url):
        """Return a parsed URL with an http scheme to trigger scheme rejection."""
        # Return a parsed URL with http scheme instead of https
        return ParseResult(scheme="http", netloc="raw.githubusercontent.com", path="", params="", query="", fragment="")

    monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlparse", mock_urlparse)

    result = _fetch_remote_bundles("test/repo", "main")
    assert result.data is None
    assert result.errors == ["Invalid URL scheme: http. Only https is allowed."]


def test_fetch_remote_bundles_success(monkeypatch):
    """Test successful fetching of remote bundles."""
    from unittest.mock import MagicMock

    from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

    seen = {}

    def mock_urlopen(url, timeout):
        """Record the timeout and return a response with valid bundles YAML."""
        seen["timeout"] = timeout
        mock_response = MagicMock()
        mock_response.read.return_value = (
            b"version: 1.0\nbundles:\n  core:\n    description: Core\n    files:\n      - .gitignore"
        )
        mock_response.__enter__ = lambda self: self
        mock_response.__exit__ = lambda self, *args: None
        return mock_response

    monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)

    result = _fetch_remote_bundles("test/repo", "main")
    assert isinstance(result.data, dict)
    assert "version" in result.data
    assert "bundles" in result.data
    assert result.errors == []
    # Pin the request timeout so a mutated value is caught.
    assert seen["timeout"] == 10


def test_fetch_remote_bundles_custom_timeout(monkeypatch):
    """A custom timeout is forwarded to urlopen verbatim."""
    from unittest.mock import MagicMock

    from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

    seen = {}

    def mock_urlopen(url, timeout):
        """Record the custom timeout and return a minimal valid bundles response."""
        seen["timeout"] = timeout
        resp = MagicMock()
        resp.read.return_value = b"version: 1.0\nbundles: {}"
        resp.__enter__ = lambda self: self
        resp.__exit__ = lambda self, *args: None
        return resp

    monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)

    _fetch_remote_bundles("test/repo", "main", timeout=42.5)
    assert seen["timeout"] == 42.5


def test_fetch_remote_bundles_no_retries(monkeypatch):
    """attempts=1 makes a single request and never sleeps."""
    from unittest.mock import MagicMock
    from urllib.error import URLError

    from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

    calls = MagicMock(side_effect=URLError("down"))

    def mock_urlopen(url, timeout):
        """Delegate to the mock that always raises a URLError for the no-retry case."""
        return calls(url, timeout)

    sleep = MagicMock()
    monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)
    monkeypatch.setattr("rhiza_hooks._bundles_fetch.time.sleep", sleep)

    result = _fetch_remote_bundles("test/repo", "main", attempts=1)
    assert result.data is None
    assert calls.call_count == 1
    assert sleep.call_args_list == []


def test_fetch_remote_bundles_logs_each_attempt(monkeypatch, capsys):
    """Every failed attempt is logged; retried ones mention the backoff delay."""
    from unittest.mock import MagicMock
    from urllib.error import URLError

    from rhiza_hooks.check_template_bundles import _fetch_remote_bundles

    calls = MagicMock(side_effect=URLError("down"))

    def mock_urlopen(url, timeout):
        """Delegate to the mock that always raises a URLError for attempt logging."""
        return calls(url, timeout)

    monkeypatch.setattr("rhiza_hooks._bundles_fetch.urlopen", mock_urlopen)
    monkeypatch.setattr("rhiza_hooks._bundles_fetch.time.sleep", MagicMock())

    _fetch_remote_bundles("test/repo", "main", attempts=2, backoff=1.0)
    out = capsys.readouterr().out
    assert "Attempt 1/2 failed" in out
    assert "retrying in 1.0s" in out
    # The final attempt is logged but has nothing to retry.
    assert "Attempt 2/2 failed" in out
    assert "Attempt 2/2 failed: " in out
    assert out.count("retrying in") == 1
