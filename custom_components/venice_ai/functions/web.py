"""REST + Scrape executors — pull data from external URLs.

`RestFunction` issues an HTTP request via HA's shared httpx client and
returns either the raw body or, if `value_template` is set, a Jinja2
rendering with `value` (text) and `value_json` (parsed body if the response
is JSON) in scope.

`ScrapeFunction` fetches a page and runs a BeautifulSoup CSS selector:
  * `select`     — CSS selector; defaults to whole-page text
  * `attribute`  — element attribute to extract (omit → element text)
  * `index`      — which match to use when the selector returns multiple
  * `value_template` — optional post-processing template

Both raise on HTTP 4xx/5xx (via `response.raise_for_status`) and surface
network errors as `{error: ...}`.

Use `resource_template` instead of `resource` when the URL needs to be
built from LLM arguments — it's rendered with the same Jinja2 context.

Example `tools.yaml` — current weather (REST + JSON parsing) and the
latest Hacker News headline (scrape):

    - name: get_current_weather
      type: rest
      description: Current weather for a city via wttr.in.
      parameters:
        type: object
        properties:
          location:
            type: string
            description: City name, e.g. "Tokyo" or "Paris, France".
        required: [location]
      resource_template: "https://wttr.in/{{ location | urlencode }}?format=j1"
      method: GET
      value_template: >-
        {% set c = value_json.current_condition[0] %}
        {{ c.weatherDesc[0].value }}, {{ c.temp_C }}°C, humidity {{ c.humidity }}%.

    - name: top_hn_story
      type: scrape
      description: Title of the current #1 story on Hacker News.
      resource: "https://news.ycombinator.com/"
      select: "tr.athing .titleline > a"
      index: 0
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urlparse

from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
from homeassistant.helpers.httpx_client import get_async_client

from .base import Function

_LOGGER = logging.getLogger(__name__)

_ALLOWED_URL_SCHEMES = {"http", "https"}


def _assert_url_safe(url: str, allow_internal: bool) -> None:
    """Reject schemes other than http(s) and (unless opted in) URLs that resolve
    to loopback / link-local / private / reserved IP space.

    HA usually runs alongside other unauthenticated services on the local network,
    so without this guard an LLM-controlled ``rest`` or ``scrape`` tool can probe
    cloud metadata (169.254.169.254), the HA REST API, or internal admin panels.
    """
    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_URL_SCHEMES:
        raise ValueError(f"URL scheme '{parsed.scheme}' is not allowed")
    if allow_internal:
        return
    host = parsed.hostname
    if not host:
        raise ValueError("URL is missing a hostname")
    try:
        addrs = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except OSError as err:
        raise ValueError(f"Cannot resolve host '{host}': {err}") from err
    for addr in addrs:
        ip = ipaddress.ip_address(addr)
        if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise ValueError(f"URL host '{host}' resolves to non-public address {addr}")


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

            allow_internal = bool(function_config.get("allow_internal_urls", False))
            _assert_url_safe(resource, allow_internal)

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

            allow_internal = bool(function_config.get("allow_internal_urls", False))
            _assert_url_safe(resource, allow_internal)

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
