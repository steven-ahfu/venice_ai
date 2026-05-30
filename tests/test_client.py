"""Tests for client.py — HTTP layer, retry logic, typed errors."""
import asyncio
import json
import sys
import unittest.mock
import pytest
import httpx

sys.path.insert(0, ".")

from custom_components.venice_ai.client import (
    AsyncVeniceAIClient,
    AuthenticationError,
    RateLimitError,
    ServiceUnavailableError,
    NetworkError,
    VeniceAIError,
    _categorize_http_error,
)


# ── _categorize_http_error ────────────────────────────────────────────────────

def test_categorize_401_returns_auth_error():
    err = _categorize_http_error(401, "Unauthorized")
    assert isinstance(err, AuthenticationError)

def test_categorize_429_returns_rate_limit_error():
    err = _categorize_http_error(429, "Too many requests")
    assert isinstance(err, RateLimitError)

def test_categorize_500_returns_service_unavailable():
    err = _categorize_http_error(500, "Internal Server Error")
    assert isinstance(err, ServiceUnavailableError)

def test_categorize_503_returns_service_unavailable():
    err = _categorize_http_error(503, "Service Unavailable")
    assert isinstance(err, ServiceUnavailableError)

def test_categorize_400_returns_base_error():
    err = _categorize_http_error(400, "Bad Request")
    assert type(err) is VeniceAIError
    assert not isinstance(err, (AuthenticationError, RateLimitError, ServiceUnavailableError))

def test_categorize_includes_context():
    err = _categorize_http_error(429, "Too many requests", context="fetching models")
    assert "fetching models" in str(err)

def test_categorize_401_ignores_context_in_message():
    # AuthenticationError message is simple, not exposing raw detail
    err = _categorize_http_error(401, "raw error body")
    assert "raw error body" not in str(err)


# ── Client lifecycle ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_client_close_is_idempotent():
    """close() called twice must not raise."""
    client = AsyncVeniceAIClient(api_key="test-key")
    await client.close()
    await client.close()  # second call must be a no-op

@pytest.mark.asyncio
async def test_client_context_manager_closes():
    """async with must close the client on exit."""
    async with AsyncVeniceAIClient(api_key="test-key") as client:
        assert not client._closed
    assert client._closed

@pytest.mark.asyncio
async def test_client_does_not_close_injected_http_client():
    """When an external http_client is injected, close() must not close it."""
    external = httpx.AsyncClient()
    client = AsyncVeniceAIClient(api_key="test-key", http_client=external)
    await client.close()
    assert not external.is_closed  # external client still open
    await external.aclose()

def test_client_sub_apis_initialised():
    client = AsyncVeniceAIClient(api_key="k")
    assert client.chat is not None
    assert client.models is not None
    assert client.speech is not None
    assert client.transcriptions is not None
    assert client.images is not None
    assert client.voices is not None

def test_chat_completions_alias():
    """client.chat.completions must alias back to client.chat."""
    client = AsyncVeniceAIClient(api_key="k")
    assert client.chat.completions is client.chat


# ── Retry logic ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retry_on_429_then_success(respx_mock=None):
    """_async_request_with_retry retries on 429 and returns the eventual success."""
    call_count = 0

    class _FakeResponse:
        def __init__(self, status_code, body="{}"):
            self.status_code = status_code
            self._body = body
        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("err", request=None, response=self)
        def json(self):
            return json.loads(self._body)
        @property
        def text(self):
            return self._body
        async def aread(self):
            pass

    async def fake_request(method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return _FakeResponse(429)
        return _FakeResponse(200, '{"ok": true}')

    client = AsyncVeniceAIClient(api_key="k")
    client._http_client.request = fake_request  # type: ignore[method-assign]

    async def _no_sleep(_): pass

    with unittest.mock.patch("custom_components.venice_ai.client.asyncio.sleep", _no_sleep):
        resp = await client._async_request_with_retry("GET", "/test")

    assert resp.json() == {"ok": True}
    assert call_count == 3
    await client.close()


# ── Models TTL cache ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_models_cache_returns_stale_within_ttl():
    """list() returns cached result without hitting the API again within TTL."""
    import time

    call_count = 0

    class _FakeResponse:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"data": [{"id": "model-a"}]}

    async def fake_request(method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        return _FakeResponse()

    client = AsyncVeniceAIClient(api_key="k")
    client._http_client.request = fake_request  # type: ignore[method-assign]

    models1 = await client.models.list("text")
    models2 = await client.models.list("text")

    assert models1 == models2 == [{"id": "model-a"}]
    assert call_count == 1  # second call was served from cache
    await client.close()
