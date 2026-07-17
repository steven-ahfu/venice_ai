"""Tests for config_flow toggle-cleanup logic.

These exercise the real ``apply_toggle_cleanup`` exported from config_flow —
NOT a hand-copy — so a regression in the OptionsFlow save path is caught.
"""
import sys
sys.path.insert(0, ".")

# conftest.py stubs all HA modules before this runs
from custom_components.venice_ai.config_flow import apply_toggle_cleanup
from custom_components.venice_ai.const import (
    CONF_TTS_ENABLED, CONF_TTS_MODEL, CONF_TTS_VOICE, CONF_TTS_RESPONSE_FORMAT, CONF_TTS_SPEED,
    CONF_STT_ENABLED, CONF_STT_MODEL, CONF_STT_RESPONSE_FORMAT, CONF_STT_TIMESTAMPS,
    RECOMMENDED_TTS_ENABLED, RECOMMENDED_STT_ENABLED,
)


def test_tts_disabled_clears_all_tts_sub_fields():
    result = apply_toggle_cleanup({
        CONF_TTS_ENABLED: False,
        CONF_TTS_MODEL: "tts-kokoro",
        CONF_TTS_VOICE: "bm_daniel",
        CONF_TTS_RESPONSE_FORMAT: "mp3",
        CONF_TTS_SPEED: 1.0,
    })
    for key in (CONF_TTS_MODEL, CONF_TTS_VOICE, CONF_TTS_RESPONSE_FORMAT, CONF_TTS_SPEED):
        assert key not in result
    assert result[CONF_TTS_ENABLED] is False


def test_tts_enabled_preserves_sub_fields():
    result = apply_toggle_cleanup({
        CONF_TTS_ENABLED: True,
        CONF_TTS_MODEL: "tts-kokoro",
        CONF_TTS_VOICE: "bm_daniel",
    })
    assert result[CONF_TTS_MODEL] == "tts-kokoro"
    assert result[CONF_TTS_VOICE] == "bm_daniel"


def test_stt_disabled_clears_all_stt_sub_fields():
    result = apply_toggle_cleanup({
        CONF_STT_ENABLED: False,
        CONF_STT_MODEL: "nvidia/parakeet-tdt-0.6b-v3",
        CONF_STT_RESPONSE_FORMAT: "json",
        CONF_STT_TIMESTAMPS: False,
    })
    for key in (CONF_STT_MODEL, CONF_STT_RESPONSE_FORMAT, CONF_STT_TIMESTAMPS):
        assert key not in result


def test_missing_toggle_uses_recommended_default():
    # RECOMMENDED_*_ENABLED are True, so absent toggle keys preserve sub-fields.
    assert RECOMMENDED_TTS_ENABLED is True
    assert RECOMMENDED_STT_ENABLED is True
    result = apply_toggle_cleanup({
        CONF_TTS_MODEL: "tts-kokoro",
        CONF_STT_MODEL: "nvidia/parakeet-tdt-0.6b-v3",
    })
    assert result[CONF_TTS_MODEL] == "tts-kokoro"
    assert result[CONF_STT_MODEL] == "nvidia/parakeet-tdt-0.6b-v3"
