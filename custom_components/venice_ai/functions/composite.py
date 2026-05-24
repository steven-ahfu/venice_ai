"""Composite function — chains multiple functions in sequence."""
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
