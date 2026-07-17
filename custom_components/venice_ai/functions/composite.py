"""Composite executor — runs a list of tool steps in order in one LLM call.

Each entry in `sequence` is a full inline tool config (same shape as a
`tools.yaml` entry, minus the top-level `name`/`description`/`parameters`).
The composite's `arguments` flow into every step as Jinja2 variables, and
each step can capture its result with `response_variable: <name>` so later
steps (and the final return) can reference it.

The composite returns the **last step's** result. If you need to assemble a
custom payload, put a `template` step at the end that combines variables
captured earlier.

Why this exists: it lets one LLM tool call do "fetch X, then fetch Y, then
format both" — avoiding the latency of an extra round-trip per fetch.

Example `tools.yaml` — morning briefing that fetches weather, picks the
lowest phone battery, and formats both in one call:

    - name: morning_briefing
      type: composite
      description: Build a single morning summary with weather and the
        lowest phone battery. Use when the user asks for a morning briefing
        or "how's the day looking".
      parameters:
        type: object
        properties:
          location:
            type: string
            description: City to fetch weather for.
        required: [location]
      sequence:
        - type: rest
          resource_template: "https://wttr.in/{{ location | urlencode }}?format=j1"
          method: GET
          response_variable: weather
        - type: template
          value_template: >-
            Weather: {{ (weather | from_json).current_condition[0].weatherDesc[0].value }},
            {{ (weather | from_json).current_condition[0].temp_C }}°C.
            Lowest battery: {{ states.sensor
              | selectattr('attributes.device_class', 'eq', 'battery')
              | map(attribute='state') | map('int', 0) | min }}%.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .base import Function

_LOGGER = logging.getLogger(__name__)


class CompositeFunction(Function):
    """Chains multiple function configs in sequence, passing results between steps."""

    @property
    def function_type(self) -> str:
        return "composite"

    def validate_schema(self, config: dict[str, Any]) -> dict[str, Any]:
        config = super().validate_schema(config)
        if "sequence" not in config or not isinstance(config["sequence"], list):
            from ..exceptions import InvalidFunction
            raise InvalidFunction(config["name"], "missing or invalid 'sequence' (must be a list)")
        return config

    async def execute(
        self,
        hass: HomeAssistant,
        function_config: dict[str, Any],
        arguments: dict[str, Any],
        llm_context: Any,
        exposed_entities: list[dict[str, Any]],
    ) -> Any:
        from . import get_function

        current_args = dict(arguments)
        last_result: Any = None

        for step_config in function_config["sequence"]:
            step_type = step_config.get("type")
            if not step_type:
                return {"error": "Composite step missing 'type'"}
            try:
                fn = get_function(step_type)
                last_result = await fn.execute(hass, step_config, current_args, llm_context, exposed_entities)
                response_var = step_config.get("response_variable")
                if response_var:
                    current_args[response_var] = last_result
            except Exception as err:
                _LOGGER.warning("Composite step '%s' failed: %s", step_type, err)
                return {"error": f"Step '{step_type}' failed: {err}"}

        return last_result
