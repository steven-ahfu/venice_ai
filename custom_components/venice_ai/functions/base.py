"""Abstract base class for Venice AI custom functions."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from homeassistant.core import HomeAssistant

from ..exceptions import InvalidFunction


class Function(ABC):
    """Abstract base for all custom function types."""

    @property
    @abstractmethod
    def function_type(self) -> str:
        """Return the type string used in YAML config."""

    def validate_schema(self, config: dict[str, Any]) -> dict[str, Any]:
        """Validate a function config dict. Override to add schema validation.

        Raises InvalidFunction on failure.
        """
        if "name" not in config:
            raise InvalidFunction(str(config.get("name", "unknown")), "missing 'name' field")
        if config.get("type") != self.function_type:
            raise InvalidFunction(
                str(config.get("name", "unknown")),
                f"type mismatch: expected '{self.function_type}', got '{config.get('type')}'",
            )
        return config

    @abstractmethod
    async def execute(
        self,
        hass: HomeAssistant,
        function_config: dict[str, Any],
        arguments: dict[str, Any],
        llm_context: Any,
        exposed_entities: list[dict[str, Any]],
    ) -> Any:
        """Execute the function and return a result."""
