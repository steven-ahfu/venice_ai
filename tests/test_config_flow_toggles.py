"""Regression tests: boolean toggles in the options flow must use ``default=``.

The Home Assistant frontend initialises ``BooleanSelector`` fields to *off* and
ignores ``description={"suggested_value": ...}``. A toggle built with
``suggested_value`` therefore always renders unchecked and submits ``False`` —
which silently disabled TTS and made the options flow skip the voice-selection
step. These tests pin the fix (``default=``) by inspecting the built schema's
voluptuous markers, so a regression back to ``suggested_value`` fails loudly.
"""
import types

import voluptuous as vol

# conftest.py stubs all HA modules before this import runs.
from custom_components.venice_ai.config_flow import VeniceAIOptionsFlow
from custom_components.venice_ai import const


# Every boolean toggle in the options flow + its expected default when the
# config entry has no stored value yet.
BOOLEAN_TOGGLES = {
    const.CONF_STRIP_THINKING_RESPONSE: False,
    const.CONF_DISABLE_THINKING: const.RECOMMENDED_DISABLE_THINKING,
    const.CONF_CONTINUE_CONVERSATION: const.RECOMMENDED_CONTINUE_CONVERSATION,
    const.CONF_ENABLE_WEB_SEARCH: const.RECOMMENDED_ENABLE_WEB_SEARCH,
    const.CONF_TTS_ENABLED: const.RECOMMENDED_TTS_ENABLED,
    const.CONF_STT_ENABLED: const.RECOMMENDED_STT_ENABLED,
    const.CONF_STT_TIMESTAMPS: const.RECOMMENDED_STT_TIMESTAMPS,
}


def _build_schema(stored_options: dict | None = None) -> vol.Schema:
    flow = VeniceAIOptionsFlow()
    flow.config_entry = types.SimpleNamespace(options=stored_options or {}, data={})
    return flow._build_options_schema([], [], [], [])


def _marker_for(schema: vol.Schema, key: str) -> vol.Marker:
    for marker in schema.schema:
        if marker.schema == key:
            return marker
    raise AssertionError(f"{key!r} not found in options schema")


def test_boolean_toggles_use_default_not_suggested_value():
    schema = _build_schema()
    for key, expected_default in BOOLEAN_TOGGLES.items():
        marker = _marker_for(schema, key)
        # A real ``default=`` produces a callable default factory; an unset
        # default is ``vol.UNDEFINED``. ``suggested_value`` would leave the
        # default unset and stash the value under ``marker.description``.
        assert marker.default is not vol.UNDEFINED, (
            f"{key} must use default=, not suggested_value"
        )
        assert marker.default() == expected_default, (
            f"{key} default should be {expected_default}"
        )
        assert not (marker.description or {}).get("suggested_value"), (
            f"{key} must not rely on suggested_value for its toggle state"
        )


def test_tts_enabled_defaults_true_so_voice_step_is_not_skipped():
    # Fresh entry (no stored options): TTS must default on so the options flow
    # routes into the voice-selection step.
    marker = _marker_for(_build_schema(), const.CONF_TTS_ENABLED)
    assert marker.default() is True


def test_stored_toggle_state_is_preserved():
    # An explicitly-disabled toggle stays disabled when re-opening options.
    schema = _build_schema({const.CONF_TTS_ENABLED: False})
    assert _marker_for(schema, const.CONF_TTS_ENABLED).default() is False
