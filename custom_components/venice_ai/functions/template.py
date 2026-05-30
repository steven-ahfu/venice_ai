"""Template executor — renders a Jinja2 template against live HA state.

The `value_template` is rendered through HA's `Template` helper, so all
state functions and filters (`states`, `state_attr`, `now()`, etc.) are
available. The LLM-supplied `arguments` are passed in as variables.

`parse_result` (default `false`) controls whether the rendered string is
deserialised — leave it off when you want plain text back; turn it on if the
template produces JSON/numbers/booleans you want as native Python types.

This is the cheapest, safest way to give the LLM read access to HA state —
no service calls, no shell, no I/O. Reach for `native get_history` if you
need historical values; use `template` for current state.

Returns the rendered value (string by default), or `{error: ...}` on a
template error.

Example `tools.yaml` — read the shopping list back to the user, and report
the lowest phone battery:

    - name: read_shopping_list
      type: template
      description: Read the current shopping list back to the user.
      value_template: >-
        {% set items = state_attr('todo.shopping_list', 'all') or [] %}
        {% if items %}{{ items | map(attribute='summary') | join(', ') }}
        {% else %}The shopping list is empty.{% endif %}

    - name: lowest_phone_battery
      type: template
      description: Report which device has the lowest battery and its level.
      value_template: >-
        {% set batt = states.sensor
            | selectattr('attributes.device_class', 'eq', 'battery')
            | sort(attribute='state') | first %}
        {{ batt.name }} at {{ batt.state }}%
"""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.template import Template

from .base import Function


class TemplateFunction(Function):
    """Renders a Jinja2 template with call arguments available as variables."""

    @property
    def function_type(self) -> str:
        return "template"

    def validate_schema(self, config: dict[str, Any]) -> dict[str, Any]:
        config = super().validate_schema(config)
        if "value_template" not in config:
            from ..exceptions import InvalidFunction
            raise InvalidFunction(config["name"], "missing 'value_template'")
        return config

    async def execute(
        self,
        hass: HomeAssistant,
        function_config: dict[str, Any],
        arguments: dict[str, Any],
        llm_context: Any,
        exposed_entities: list[dict[str, Any]],
    ) -> Any:
        template_str = function_config["value_template"]
        parse_result = function_config.get("parse_result", False)
        try:
            result = Template(template_str, hass).async_render(arguments, parse_result=parse_result)
            return result
        except TemplateError as err:
            return {"error": f"Template render failed: {err}"}
