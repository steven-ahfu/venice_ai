"""Tests for native Home Assistant routing helpers."""

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, ".")

from custom_components.venice_ai.conversation import (
    HOME_ASSISTANT_AGENT,
    _async_try_hass_agent,
    _control_home_assistant_enabled,
    _hass_result_satisfied,
)


def _make_user_input():
    return SimpleNamespace(
        text="turn on the kitchen lights",
        conversation_id="conv-1",
        device_id="device-1",
        language="en",
        context=SimpleNamespace(user_id="user-1"),
    )


def _make_result(error_code):
    return SimpleNamespace(
        response=SimpleNamespace(error_code=error_code),
        conversation_id="conv-1",
    )


def test_control_home_assistant_enabled():
    assert _control_home_assistant_enabled(["assist"]) is True
    assert _control_home_assistant_enabled("assist") is True
    assert _control_home_assistant_enabled(None) is False
    assert _control_home_assistant_enabled([]) is False
    assert _control_home_assistant_enabled("") is False


def test_hass_result_satisfied():
    assert _hass_result_satisfied(_make_result(None)) is True
    assert _hass_result_satisfied(_make_result("unknown")) is False
    assert _hass_result_satisfied(None) is False


async def test_async_try_hass_agent_uses_default_agent():
    hass = MagicMock()
    current_agent = object()
    user_input = _make_user_input()
    expected = _make_result(None)
    hass_agent = SimpleNamespace(async_process=AsyncMock(return_value=expected))

    with patch(
        "custom_components.venice_ai.conversation.conversation_component.async_get_agent",
        return_value=hass_agent,
        create=True,
    ) as mock_get_agent:
        result = await _async_try_hass_agent(hass, user_input, current_agent)

    assert result is expected
    mock_get_agent.assert_called_once_with(hass, HOME_ASSISTANT_AGENT)
    hass_agent.async_process.assert_awaited_once_with(user_input)


async def test_async_try_hass_agent_returns_none_when_missing():
    hass = MagicMock()
    user_input = _make_user_input()

    with patch(
        "custom_components.venice_ai.conversation.conversation_component.async_get_agent",
        return_value=None,
        create=True,
    ):
        result = await _async_try_hass_agent(hass, user_input, object())

    assert result is None


async def test_async_try_hass_agent_returns_none_on_exception():
    hass = MagicMock()
    user_input = _make_user_input()
    hass_agent = SimpleNamespace(async_process=AsyncMock(side_effect=RuntimeError("boom")))

    with patch(
        "custom_components.venice_ai.conversation.conversation_component.async_get_agent",
        return_value=hass_agent,
        create=True,
    ):
        result = await _async_try_hass_agent(hass, user_input, object())

    assert result is None
