import sys
import types

import pytest

sys.path.insert(0, ".")

# conftest.py stubs all HA modules before this runs
from custom_components.venice_ai import tts as tts_module
from custom_components.venice_ai import const as const_module


class DummySpeech:
    def __init__(self):
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        return b"audio-bytes"


class DummyClient:
    def __init__(self):
        self.speech = DummySpeech()


class DummyEntry:
    """Stand-in for a HA ConfigEntry as VeniceAITTS(config_entry) expects it."""

    def __init__(self, options=None):
        self.entry_id = "entry-1"
        self.domain = "venice_ai"
        self.title = "Venice AI"
        self.options = options or {}
        self.runtime_data = types.SimpleNamespace(client=DummyClient())


@pytest.mark.asyncio
async def test_supported_voices_exposed_for_voice_assistant_ui():
    # With the default tts-kokoro model, the picker exposes that model's voices.
    provider = tts_module.VeniceAITTS(DummyEntry())
    voices = provider.async_get_supported_voices("en")

    kokoro_voices = const_module.MODEL_VOICES["tts-kokoro"]
    assert voices is not None
    assert len(voices) == len(kokoro_voices)
    assert voices[0].voice_id == kokoro_voices[0]


@pytest.mark.asyncio
async def test_tts_audio_prefers_standard_ha_options():
    entry = DummyEntry()
    provider = tts_module.VeniceAITTS(entry)
    client = entry.runtime_data.client
    fmt, data = await provider.async_get_tts_audio(
        "hello",
        "en",
        {
            "voice": "af_alloy",
            "audio_output": "mp3",
            "tts_model": "tts-kokoro",
            "tts_speed": 1.4,
        },
    )

    assert fmt == "mp3"
    assert data == b"audio-bytes"
    assert client.speech.calls[0]["voice"] == "af_alloy"
    assert client.speech.calls[0]["audio_output"] == "mp3"
    assert client.speech.calls[0]["model"] == "tts-kokoro"
    assert client.speech.calls[0]["speed"] == 1.4


@pytest.mark.asyncio
async def test_tts_audio_supports_legacy_venice_option_keys():
    entry = DummyEntry()
    provider = tts_module.VeniceAITTS(entry)
    client = entry.runtime_data.client
    fmt, _ = await provider.async_get_tts_audio(
        "hello",
        "en",
        {
            "tts_voice": "bm_daniel",
            "tts_response_format": "wav",
            "tts_model": "tts-kokoro",
            "tts_speed": 1.0,
        },
    )

    assert fmt == "wav"
    assert client.speech.calls[0]["voice"] == "bm_daniel"
    assert client.speech.calls[0]["audio_output"] == "wav"

