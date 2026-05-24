"""Script function — runs a HA script sequence with arguments as run variables."""
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
