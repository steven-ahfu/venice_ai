"""Helper utilities for Venice AI integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components import conversation
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


def get_exposed_entities(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Return a list of entities exposed to the conversation agent."""
    try:
        from homeassistant.components.conversation import async_should_expose
    except ImportError:
        return []

    states = [
        s for s in hass.states.async_all()
        if async_should_expose(hass, conversation.DOMAIN, s.entity_id)
    ]
    registry = er.async_get(hass)
    result = []
    for state in states:
        entity = registry.async_get(state.entity_id)
        result.append({
            "entity_id": state.entity_id,
            "name": state.name,
            "state": state.state,
            "aliases": [str(a) for a in entity.aliases] if entity and entity.aliases else [],
            "area_id": entity.area_id if entity else None,
        })
    return result
