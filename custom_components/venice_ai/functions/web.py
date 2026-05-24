"""REST and Scrape functions for Venice AI."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
from homeassistant.helpers.httpx_client import get_async_client

from .base import Function

_LOGGER = logging.getLogger(__name__)


class RestFunction(Function):
    """Makes HTTP requests and returns the response."""

    @property
    def function_type(self) -> str:
        return "rest"

    def validate_schema(self, config: dict[str, Any]) -> dict[str, Any]:
        config = super().validate_schema(config)
        if "resource" not in config and "resource_template" not in config:
            from ..exceptions import InvalidFunction
            raise InvalidFunction(config["name"], "missing 'resource' or 'resource_template'")
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
            resource = function_config.get("resource", "")
            if function_config.get("resource_template"):
                resource = Template(function_config["resource_template"], hass).async_render(arguments, parse_result=False)

            method = function_config.get("method", "GET").upper()
            headers = function_config.get("headers", {})
            payload = None
            if function_config.get("payload_template"):
                payload = Template(function_config["payload_template"], hass).async_render(arguments, parse_result=False)
            elif function_config.get("payload"):
                payload = function_config["payload"]

            client = get_async_client(hass)
            response = await client.request(method, resource, content=payload, headers=headers)
            response.raise_for_status()

            value_template = function_config.get("value_template")
            if value_template:
                return Template(value_template, hass).async_render(
                    {"value": response.text, "value_json": response.json() if response.headers.get("content-type", "").startswith("application/json") else {}},
                    parse_result=False,
                )
            return response.text
        except Exception as err:
            _LOGGER.warning("REST function failed: %s", err)
            return {"error": str(err)}


class ScrapeFunction(Function):
    """Scrapes HTML content using CSS selectors."""

    @property
    def function_type(self) -> str:
        return "scrape"

    def validate_schema(self, config: dict[str, Any]) -> dict[str, Any]:
        config = super().validate_schema(config)
        if "resource" not in config and "resource_template" not in config:
            from ..exceptions import InvalidFunction
            raise InvalidFunction(config["name"], "missing 'resource' or 'resource_template'")
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
            from bs4 import BeautifulSoup  # type: ignore[import]
        except ImportError:
            return {"error": "beautifulsoup4 is not installed"}

        try:
            resource = function_config.get("resource", "")
            if function_config.get("resource_template"):
                resource = Template(function_config["resource_template"], hass).async_render(arguments, parse_result=False)

            client = get_async_client(hass)
            response = await client.get(resource)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            select = function_config.get("select")
            attribute = function_config.get("attribute")
            index = function_config.get("index", 0)

            if select:
                elements = soup.select(select)
                if not elements:
                    return {"error": f"No elements matched selector: {select}"}
                el = elements[index] if index < len(elements) else elements[0]
                value = el.get(attribute) if attribute else el.get_text(strip=True)
            else:
                value = soup.get_text(strip=True)

            value_template = function_config.get("value_template")
            if value_template:
                return Template(value_template, hass).async_render({"value": value}, parse_result=False)
            return value
        except Exception as err:
            _LOGGER.warning("Scrape function failed: %s", err)
            return {"error": str(err)}
