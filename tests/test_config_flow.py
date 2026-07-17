import sys

import pytest

sys.path.insert(0, ".")

# conftest.py stubs all HA modules before this runs
from custom_components.venice_ai import config_flow as cfg_flow


class DummyModels:
    def __init__(self, result=None, error=None):
        self.result = result if result is not None else [{"id": "m1"}]
        self.error = error

    async def list(self, model_type=None):
        if self.error:
            raise self.error
        # Only the text-model call needs the curated/labelled list; other
        # types (tts/asr) can be empty for these tests.
        if model_type in (None, "text"):
            return self.result
        return []


class DummyClient:
    """Async-context-manager client stub matching AsyncVeniceAIClient usage."""

    def __init__(self, api_key=None, http_client=None):
        self.api_key = api_key
        self.models = DummyModels()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class DummyAPI:
    def __init__(self, api_id, name):
        self.id = api_id
        self.name = name


class DummyConfigEntry:
    def __init__(self, options=None, runtime_data=None, data=None):
        self.options = options or {}
        self.runtime_data = runtime_data
        self.data = data or {"api_key": "k"}


@pytest.mark.asyncio
async def test_config_flow_user_step_creates_entry(monkeypatch):
    monkeypatch.setattr(cfg_flow, "AsyncVeniceAIClient", DummyClient)
    flow = cfg_flow.VeniceAIConfigFlow()

    result = await flow.async_step_user({"api_key": "k"})

    # This integration creates the entry with data only; all tunables live in
    # the options flow, so no options are seeded at creation time.
    assert result["title"] == "Venice AI"
    assert result["data"]["api_key"] == "k"


@pytest.mark.asyncio
async def test_config_flow_user_step_invalid_auth(monkeypatch):
    class FailingClient(DummyClient):
        def __init__(self, api_key=None, http_client=None):
            super().__init__(api_key, http_client)
            self.models = DummyModels(error=cfg_flow.AuthenticationError("nope"))

    monkeypatch.setattr(cfg_flow, "AsyncVeniceAIClient", FailingClient)
    flow = cfg_flow.VeniceAIConfigFlow()

    result = await flow.async_step_user({"api_key": "bad"})

    assert result["step_id"] == "user"
    assert result["errors"]["base"] == "invalid_auth"


def _schema_options_for(result, key):
    """Pull the SelectSelector options for a given schema key from a form result."""
    for marker, selector in result["data_schema"].schema.items():
        # voluptuous Optional/Required markers expose the field name as .schema
        if getattr(marker, "schema", None) == key:
            return selector.config.options
    raise AssertionError(f"key {key!r} not found in schema")


@pytest.mark.asyncio
async def test_options_flow_marks_only_web_search_models(monkeypatch):
    monkeypatch.setattr(cfg_flow.llm, "async_get_apis", lambda hass: [])

    models = [
        {
            "id": "web-model",
            "model_spec": {
                "name": "Web Model",
                "capabilities": {
                    "supportsFunctionCalling": True,
                    "supportsWebSearch": True,
                },
            },
        },
        {
            "id": "plain-model",
            "model_spec": {
                "name": "Plain Model",
                "capabilities": {
                    "supportsFunctionCalling": True,
                    "supportsWebSearch": False,
                },
            },
        },
    ]

    def _make_client(*args, **kwargs):
        c = DummyClient()
        c.models = DummyModels(result=models)
        return c

    monkeypatch.setattr(cfg_flow, "AsyncVeniceAIClient", _make_client)
    monkeypatch.setattr(cfg_flow, "get_async_client", lambda hass: object())

    entry = DummyConfigEntry(options={})
    flow = cfg_flow.VeniceAIOptionsFlow()
    flow.hass = object()
    flow.config_entry = entry

    result = await flow.async_step_init(None)

    labels = {opt["value"]: opt["label"] for opt in _schema_options_for(result, cfg_flow.CONF_CHAT_MODEL)}
    assert labels["web-model"].startswith("🔍 ")
    assert not labels["plain-model"].startswith("🔍")
    # The plain model must not carry the marker anywhere in its label.
    assert "🔍" not in labels["plain-model"]


@pytest.mark.asyncio
async def test_options_flow_sanitizes_llm_api_ids(monkeypatch):
    apis = [DummyAPI("valid_api", "Valid API"), DummyAPI("other_api", "Other API")]
    monkeypatch.setattr(cfg_flow.llm, "async_get_apis", lambda hass: apis)

    entry = DummyConfigEntry(options={"llm_hass_api": ["stale_api"]})
    flow = cfg_flow.VeniceAIOptionsFlow()
    flow.hass = object()
    flow.config_entry = entry

    # TTS disabled so the flow skips the voice step and the sanitized options
    # are captured in _init_data before advancing to the skills step.
    await flow.async_step_init(
        {"llm_hass_api": ["valid_api", "unknown_api"], "tts_enabled": False}
    )

    # unknown_api is dropped; only the registered valid_api survives.
    assert flow._init_data["llm_hass_api"] == ["valid_api"]
