"""Script executor — runs a Home Assistant script `sequence` from inline YAML.

The `sequence` block is the same shape you'd write under
`script:` in `configuration.yaml` — service calls, delays, conditions, etc.
The LLM-supplied `arguments` are passed in as run variables, so the sequence
can reference them with `{{ var_name }}` exactly like a normal HA script.

If a step assigns to `_function_result` (e.g. via `variables:`), that value
is returned to the model; otherwise the function returns `"Success"`.

This is the right escape hatch when you want LLM-callable behavior but
prefer HA's script engine over inline templates or shell commands — it
inherits HA's permission model and shows up in script traces.

Example `tools.yaml` — flash the office lights N times when the LLM is asked
to "alert" or "ping" the user:

    - name: flash_office_lights
      type: script
      description: Flash the office light strip a few times to get attention.
      parameters:
        type: object
        properties:
          times:
            type: integer
            description: How many flashes (1-10).
        required: [times]
      sequence:
        - repeat:
            count: "{{ times | int }}"
            sequence:
              - service: light.turn_on
                target: { entity_id: light.office }
                data: { brightness: 255, transition: 0 }
              - delay: "00:00:00.3"
              - service: light.turn_off
                target: { entity_id: light.office }
              - delay: "00:00:00.3"
        - variables:
            _function_result: "Flashed {{ times }} times"
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .base import Function

_LOGGER = logging.getLogger(__name__)


class ScriptFunction(Function):
    """Executes a Home Assistant script sequence."""

    @property
    def function_type(self) -> str:
        return "script"

    def validate_schema(self, config: dict[str, Any]) -> dict[str, Any]:
        config = super().validate_schema(config)
        if "sequence" not in config:
            from ..exceptions import InvalidFunction
            raise InvalidFunction(config["name"], "missing 'sequence'")
        return config

    async def execute(
        self,
        hass: HomeAssistant,
        function_config: dict[str, Any],
        arguments: dict[str, Any],
        llm_context: Any,
        exposed_entities: list[dict[str, Any]],
    ) -> Any:
        try:
            from homeassistant.helpers.script import Script
            script = Script(
                hass,
                function_config["sequence"],
                function_config.get("name", "venice_function"),
                "venice_ai",
            )
            script_vars = dict(arguments)
            await script.async_run(run_variables=script_vars, context=None)
            return script_vars.get("_function_result", "Success")
        except Exception as err:
            _LOGGER.warning("Script function failed: %s", err)
            return {"error": str(err)}
