"""Native executor — talks to Home Assistant directly (services + recorder).

Dispatches on `operation`:
  * `execute_service`  — calls `hass.services.async_call(domain, service,
                         service_data, blocking=True)`. Enforces the exposed-
                         entity allowlist when `service_data.entity_id` is
                         set: unknown entities raise `EntityNotFound`,
                         non-exposed ones raise `EntityNotExposed`.
  * `get_history`      — queries the recorder for state changes of
                         `entity_ids` between `start_time` and `end_time`
                         (ISO 8601). Defaults to the last 24h.
  * `get_statistics`   — not yet implemented.
  * `add_automation`   — not yet implemented.

`execute_service` is the workhorse — most "do X" tools should use it rather
than `script` or `bash`, because it routes through HA's normal service stack
and respects HA's exposure rules.

Example `tools.yaml` — let the LLM call any HA service safely:

    - name: execute_service
      type: native
      operation: execute_service
      description: Call a Home Assistant service on an exposed entity.
        Use this to turn things on/off, set brightness, play media, etc.
      parameters:
        type: object
        properties:
          domain:
            type: string
            description: The HA domain (light, switch, media_player, …).
          service:
            type: string
            description: The service name (turn_on, turn_off, …).
          service_data:
            type: object
            description: Service data, e.g. {"entity_id": "light.kitchen",
              "brightness_pct": 40}.
        required: [domain, service, service_data]

    - name: thermostat_history
      type: native
      operation: get_history
      description: Get recent thermostat readings.
      parameters:
        type: object
        properties:
          entity_ids:
            type: array
            items: {type: string}
          start_time:
            type: string
            description: ISO 8601 timestamp; defaults to 24h ago.
        required: [entity_ids]
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .base import Function
from ..exceptions import CallServiceError, EntityNotFound, EntityNotExposed

_LOGGER = logging.getLogger(__name__)

_OPERATIONS = {"execute_service", "get_history", "get_statistics", "add_automation"}


class NativeFunction(Function):
    """Calls Home Assistant services or retrieves HA data."""

    @property
    def function_type(self) -> str:
        return "native"

    def validate_schema(self, config: dict[str, Any]) -> dict[str, Any]:
        config = super().validate_schema(config)
        op = config.get("operation")
        if op and op not in _OPERATIONS:
            from ..exceptions import InvalidFunction
            raise InvalidFunction(config["name"], f"unknown operation '{op}'")
        return config

    async def execute(
        self,
        hass: HomeAssistant,
        function_config: dict[str, Any],
        arguments: dict[str, Any],
        llm_context: Any,
        exposed_entities: list[dict[str, Any]],
    ) -> Any:
        operation = function_config.get("operation", "execute_service")

        if operation == "execute_service":
            return await self._execute_service(hass, arguments, exposed_entities)
        if operation == "get_history":
            return await self._get_history(hass, arguments)
        if operation == "get_statistics":
            return await self._get_statistics(hass, arguments)
        if operation == "add_automation":
            return await self._add_automation(hass, arguments)
        return {"error": f"Unknown operation: {operation}"}

    async def _execute_service(
        self,
        hass: HomeAssistant,
        arguments: dict[str, Any],
        exposed_entities: list[dict[str, Any]],
    ) -> Any:
        domain = arguments.get("domain")
        service = arguments.get("service")
        service_data = arguments.get("service_data", {})
        entity_id = service_data.get("entity_id") if isinstance(service_data, dict) else None

        if not domain or not service:
            return {"error": "domain and service are required"}

        if entity_id:
            exposed_ids = {e["entity_id"] for e in exposed_entities}
            if entity_id not in hass.states.async_entity_ids():
                raise EntityNotFound(entity_id)
            if entity_id not in exposed_ids:
                raise EntityNotExposed(entity_id)

        try:
            await hass.services.async_call(
                domain, service, service_data, blocking=True
            )
            return {"success": True}
        except Exception as err:
            raise CallServiceError(domain, service, str(err)) from err

    async def _get_history(self, hass: HomeAssistant, arguments: dict[str, Any]) -> Any:
        try:
            from homeassistant.components import recorder
            entity_ids = arguments.get("entity_ids", [])
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]
            start_time = arguments.get("start_time")
            end_time = arguments.get("end_time")
            import datetime
            start = datetime.datetime.fromisoformat(start_time) if start_time else (
                datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
            )
            end = datetime.datetime.fromisoformat(end_time) if end_time else None
            history = await recorder.get_instance(hass).async_add_executor_job(
                lambda: recorder.history.get_significant_states(hass, start, end, entity_ids)
            )
            result = {}
            for eid, states in history.items():
                result[eid] = [{"state": s.state, "last_changed": s.last_changed.isoformat()} for s in states]
            return result
        except Exception as err:
            _LOGGER.warning("get_history failed: %s", err)
            return {"error": str(err)}

    async def _get_statistics(self, hass: HomeAssistant, arguments: dict[str, Any]) -> Any:
        return {"error": "get_statistics not yet implemented"}

    async def _add_automation(self, hass: HomeAssistant, arguments: dict[str, Any]) -> Any:
        return {"error": "add_automation not yet implemented"}
