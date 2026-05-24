"""Template function — renders a Jinja2 template with arguments as variables."""
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
