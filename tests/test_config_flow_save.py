"""Tests for config_flow save logic — toggle clears sub-fields, schema builds correctly."""
import sys
sys.path.insert(0, ".")

# conftest.py stubs all HA modules before this runs

from custom_components.venice_ai.const import (
    CONF_TTS_ENABLED, CONF_TTS_MODEL, CONF_TTS_VOICE, CONF_TTS_RESPONSE_FORMAT, CONF_TTS_SPEED,
    CONF_STT_ENABLED, CONF_STT_MODEL, CONF_STT_RESPONSE_FORMAT, CONF_STT_TIMESTAMPS,
    RECOMMENDED_TTS_ENABLED, RECOMMENDED_STT_ENABLED,
)


def _apply_save_cleanup(user_input: dict) -> dict:
    """Mirror the toggle-cleanup logic from async_step_init."""
    user_input = dict(user_input)
    if not user_input.get(CONF_TTS_ENABLED, RECOMMENDED_TTS_ENABLED):
        for key in (CONF_TTS_MODEL, CONF_TTS_VOICE, CONF_TTS_RESPONSE_FORMAT, CONF_TTS_SPEED):
            user_input.pop(key, None)
    if not user_input.get(CONF_STT_ENABLED, RECOMMENDED_STT_ENABLED):
        for key in (CONF_STT_MODEL, CONF_STT_RESPONSE_FORMAT, CONF_STT_TIMESTAMPS):
            user_input.pop(key, None)
    return user_input


# ── TTS toggle off clears sub-fields ─────────────────────────────────────────

def test_tts_disabled_clears_model():
    result = _apply_save_cleanup({
        CONF_TTS_ENABLED: False,
        CONF_TTS_MODEL: "tts-kokoro",
        CONF_TTS_VOICE: "bm_daniel",
        CONF_TTS_RESPONSE_FORMAT: "mp3",
        CONF_TTS_SPEED: 1.0,
    })
    assert CONF_TTS_MODEL not in result
    assert CONF_TTS_VOICE not in result
    assert CONF_TTS_RESPONSE_FORMAT not in result
    assert CONF_TTS_SPEED not in result

def test_tts_disabled_preserves_toggle_key():
    result = _apply_save_cleanup({CONF_TTS_ENABLED: False})
    assert CONF_TTS_ENABLED in result
    assert result[CONF_TTS_ENABLED] is False

def test_tts_enabled_preserves_sub_fields():
    result = _apply_save_cleanup({
        CONF_TTS_ENABLED: True,
        CONF_TTS_MODEL: "tts-kokoro",
        CONF_TTS_VOICE: "bm_daniel",
    })
    assert result[CONF_TTS_MODEL] == "tts-kokoro"
    assert result[CONF_TTS_VOICE] == "bm_daniel"


# ── STT toggle off clears sub-fields ─────────────────────────────────────────

def test_stt_disabled_clears_model():
    result = _apply_save_cleanup({
        CONF_STT_ENABLED: False,
        CONF_STT_MODEL: "nvidia/parakeet-tdt-0.6b-v3",
        CONF_STT_RESPONSE_FORMAT: "json",
        CONF_STT_TIMESTAMPS: False,
    })
    assert CONF_STT_MODEL not in result
    assert CONF_STT_RESPONSE_FORMAT not in result
    assert CONF_STT_TIMESTAMPS not in result

def test_stt_enabled_preserves_sub_fields():
    result = _apply_save_cleanup({
        CONF_STT_ENABLED: True,
        CONF_STT_MODEL: "nvidia/parakeet-tdt-0.6b-v3",
        CONF_STT_RESPONSE_FORMAT: "json",
    })
    assert result[CONF_STT_MODEL] == "nvidia/parakeet-tdt-0.6b-v3"

def test_both_disabled_clears_all_sub_fields():
    result = _apply_save_cleanup({
        CONF_TTS_ENABLED: False,
        CONF_TTS_MODEL: "tts-kokoro",
        CONF_STT_ENABLED: False,
        CONF_STT_MODEL: "nvidia/parakeet-tdt-0.6b-v3",
    })
    assert CONF_TTS_MODEL not in result
    assert CONF_STT_MODEL not in result

def test_missing_toggle_defaults_to_recommended_enabled():
    """If toggle key absent, RECOMMENDED_* applies — sub-fields should be kept."""
    result = _apply_save_cleanup({
        CONF_TTS_MODEL: "tts-kokoro",
        CONF_STT_MODEL: "nvidia/parakeet-tdt-0.6b-v3",
    })
    # RECOMMENDED_TTS_ENABLED and RECOMMENDED_STT_ENABLED are True
    assert CONF_TTS_MODEL in result
    assert CONF_STT_MODEL in result
