"""Config flow for Venice AI Conversation integration."""

from __future__ import annotations

import logging
from types import MappingProxyType
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, llm, selector
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TemplateSelector,
)
from .client import AsyncVeniceAIClient, AuthenticationError, VeniceAIError
from .const import (
    CONF_CHAT_MODEL,
    CONF_MAX_TOKENS,
    CONF_MAX_TOOL_ITERATIONS,
    CONF_PROMPT,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    CONF_STRIP_THINKING_RESPONSE,
    CONF_DISABLE_THINKING,
    RECOMMENDED_DISABLE_THINKING,
    CONF_TTS_MODEL,
    CONF_TTS_VOICE,
    CONF_TTS_RESPONSE_FORMAT,
    CONF_TTS_SPEED,
    CONF_STT_ENABLED,
    RECOMMENDED_STT_ENABLED,
    CONF_STT_MODEL,
    CONF_STT_RESPONSE_FORMAT,
    CONF_STT_TIMESTAMPS,
    CONF_TTS_ENABLED,
    RECOMMENDED_TTS_ENABLED,
    CONF_ENABLE_WEB_SEARCH,
    RECOMMENDED_ENABLE_WEB_SEARCH,
    CONF_CONTINUE_CONVERSATION,
    RECOMMENDED_CONTINUE_CONVERSATION,
    CONF_CONTEXT_THRESHOLD,
    CONF_FUNCTION_TOOLS,
    CONF_SKILLS,
    DOMAIN,
    RECOMMENDED_CONTEXT_THRESHOLD,
    RECOMMENDED_CHAT_MODEL,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_MAX_TOOL_ITERATIONS,
    RECOMMENDED_TEMPERATURE,
    RECOMMENDED_TOP_P,
    RECOMMENDED_TTS_MODEL,
    RECOMMENDED_TTS_VOICE,
    RECOMMENDED_TTS_RESPONSE_FORMAT,
    RECOMMENDED_TTS_SPEED,
    RECOMMENDED_STT_MODEL,
    RECOMMENDED_STT_RESPONSE_FORMAT,
    RECOMMENDED_STT_TIMESTAMPS,
    VENICE_TTS_VOICES,
)

_LOGGER = logging.getLogger(__name__)

_FUNCTION_TOOLS_PLACEHOLDER = """\
# Custom function tools — uncomment and edit any block to enable it.
# Each tool needs: name, type, description.
# Supported types: native, template, script, rest, scrape, bash,
#                  read_file, write_file, edit_file, sqlite, composite.

# ── 1. NATIVE: call a HA service ─────────────────────────────────────────────
#- name: turn_on_entity
#  type: native
#  description: Turn on any exposed entity by entity_id
#  operation: execute_service
#  parameters:
#    type: object
#    properties:
#      entity_id:
#        type: string
#        description: The entity_id to turn on (e.g. light.living_room)
#    required: [entity_id]

# ── 2. NATIVE: get entity history ────────────────────────────────────────────
#- name: get_entity_history
#  type: native
#  description: Get the state history for one or more entities
#  operation: get_history
#  parameters:
#    type: object
#    properties:
#      entity_ids:
#        type: array
#        items:
#          type: string
#        description: List of entity_ids
#      start_time:
#        type: string
#        description: ISO 8601 start time (optional, defaults to 24h ago)
#      end_time:
#        type: string
#        description: ISO 8601 end time (optional, defaults to now)
#    required: [entity_ids]

# ── 3. TEMPLATE: render Jinja2 against HA state ──────────────────────────────
#- name: get_sensor_value
#  type: template
#  description: Return the current state of any sensor by entity_id
#  value_template: "{{ states(entity_id) }}"
#  parameters:
#    type: object
#    properties:
#      entity_id:
#        type: string
#        description: The entity_id of the sensor
#    required: [entity_id]

# ── 4. SCRIPT: run a HA script sequence ──────────────────────────────────────
#- name: set_scene
#  type: script
#  description: Activate a named scene in Home Assistant
#  sequence:
#    - service: scene.turn_on
#      target:
#        entity_id: "{{ scene_id }}"
#  parameters:
#    type: object
#    properties:
#      scene_id:
#        type: string
#        description: The entity_id of the scene (e.g. scene.movie_time)
#    required: [scene_id]

# ── 5. REST: HTTP request with templated URL ──────────────────────────────────
#- name: get_weather
#  type: rest
#  description: Fetch current weather for a city using wttr.in
#  resource_template: "https://wttr.in/{{ city }}?format=j1"
#  method: GET
#  headers:
#    Accept: application/json
#  value_template: "{{ value_json.current_condition[0].weatherDesc[0].value }}, {{ value_json.current_condition[0].temp_C }}°C"
#  parameters:
#    type: object
#    properties:
#      city:
#        type: string
#        description: City name (e.g. "New York")
#    required: [city]

# ── 6. SCRAPE: extract text from a webpage ────────────────────────────────────
#- name: scrape_page_title
#  type: scrape
#  description: Fetch the title of any webpage
#  resource_template: "{{ url }}"
#  select: title
#  parameters:
#    type: object
#    properties:
#      url:
#        type: string
#        description: Full URL of the page to scrape
#    required: [url]

# ── 7. BASH: run a shell command ──────────────────────────────────────────────
#- name: ping_host
#  type: bash
#  description: Ping a hostname or IP and return round-trip time
#  command: "ping -c 4 {{ host }} 2>&1 | tail -3"
#  parameters:
#    type: object
#    properties:
#      host:
#        type: string
#        description: Hostname or IP address to ping
#    required: [host]

# ── 8. READ_FILE: read from the venice_ai workspace ───────────────────────────
#- name: read_note
#  type: read_file
#  description: Read a file from /config/venice_ai/
#  path: "{{ filename }}"
#  parameters:
#    type: object
#    properties:
#      filename:
#        type: string
#        description: Relative path inside /config/venice_ai/ (e.g. notes/todo.txt)
#    required: [filename]

# ── 9. WRITE_FILE: write to the venice_ai workspace ───────────────────────────
#- name: write_note
#  type: write_file
#  description: Write or overwrite a text file in /config/venice_ai/
#  path: "{{ filename }}"
#  content: "{{ content }}"
#  parameters:
#    type: object
#    properties:
#      filename:
#        type: string
#        description: Relative path inside /config/venice_ai/
#      content:
#        type: string
#        description: Full text content to write
#    required: [filename, content]

# ── 10. EDIT_FILE: replace text in a file ─────────────────────────────────────
#- name: edit_note
#  type: edit_file
#  description: Replace a specific string in a file in /config/venice_ai/
#  path: "{{ filename }}"
#  old_text: "{{ old_text }}"
#  new_text: "{{ new_text }}"
#  parameters:
#    type: object
#    properties:
#      filename:
#        type: string
#        description: Relative path inside /config/venice_ai/
#      old_text:
#        type: string
#        description: Exact text to find and replace
#      new_text:
#        type: string
#        description: Replacement text
#    required: [filename, old_text, new_text]

# ── 11. SQLITE: query the HA recorder database ────────────────────────────────
#- name: query_recorder
#  type: sqlite
#  description: Run a read-only SQL SELECT against the HA recorder SQLite database
#  query: "{{ sql }}"
#  parameters:
#    type: object
#    properties:
#      sql:
#        type: string
#        description: >
#          SELECT query against HA recorder DB.
#          Tables: states, state_attributes, events, statistics.
#    required: [sql]

# ── COMPOSITE: chain multiple functions ───────────────────────────────────────
#- name: fetch_and_save_weather
#  type: composite
#  description: Fetch weather for a city and save the result to a file
#  sequence:
#    - type: rest
#      resource_template: "https://wttr.in/{{ city }}?format=3"
#      method: GET
#      response_variable: weather_text
#    - type: write_file
#      path: "weather_cache.txt"
#      content: "{{ weather_text }}"
#  parameters:
#    type: object
#    properties:
#      city:
#        type: string
#        description: City name to fetch weather for
#    required: [city]
"""

# Try to import DEFAULT_SYSTEM_PROMPT; fallback if not available
try:
    from .conversation import DEFAULT_SYSTEM_PROMPT
except ImportError:
    _LOGGER.warning("Could not import DEFAULT_SYSTEM_PROMPT from conversation.py, using fallback.")
    DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant."

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): cv.string,
    }
)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry to the current version."""
    if entry.version == 1:
        return True
    _LOGGER.error(
        "Unable to migrate config entry from version %s. Please recreate the integration.",
        entry.version,
    )
    return False


class VeniceAIConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Venice AI Conversation."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                _LOGGER.debug("Validating Venice AI API key by fetching models")
                async with AsyncVeniceAIClient(api_key=user_input[CONF_API_KEY]) as client:
                    models_response = await client.models.list()
                    if not isinstance(models_response, list):
                        raise VeniceAIError("Invalid models response")

                _LOGGER.debug("API key validation successful, found %d models", len(models_response))

            except AuthenticationError:
                errors["base"] = "invalid_auth"
                _LOGGER.warning("Venice AI authentication failed")
            except VeniceAIError as err:
                errors["base"] = "cannot_connect"
                _LOGGER.error("Cannot connect to Venice AI: %s", err)
            except Exception:
                _LOGGER.exception("Unexpected exception during Venice AI setup validation")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title="Venice AI",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: MappingProxyType[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when API key becomes invalid."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm re-authentication with new API key."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            try:
                _LOGGER.debug("Validating new Venice AI API key for re-auth")
                async with AsyncVeniceAIClient(api_key=user_input[CONF_API_KEY]) as client:
                    models_response = await client.models.list()
                    if not isinstance(models_response, list):
                        raise VeniceAIError("Invalid models response")

                _LOGGER.debug("Re-auth API key validation successful")
            except AuthenticationError:
                errors["base"] = "invalid_auth"
                _LOGGER.warning("Venice AI re-authentication failed: invalid API key")
            except VeniceAIError as err:
                errors["base"] = "cannot_connect"
                _LOGGER.error("Cannot connect to Venice AI during re-auth: %s", err)
            except Exception:
                _LOGGER.exception("Unexpected exception during Venice AI re-auth validation")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={**reauth_entry.data, CONF_API_KEY: user_input[CONF_API_KEY]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): cv.string,
                }
            ),
            errors=errors,
            description_placeholders={"name": reauth_entry.title},
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> VeniceAIOptionsFlow:
        """Get the options flow for this handler.

        Home Assistant injects ``self.config_entry`` automatically on the
        OptionsFlow base class (it's looked up by handler/entry_id at access
        time), so we must NOT pass ``config_entry`` to our constructor — the
        base ``OptionsFlow`` no longer accepts it and ``object.__init__`` then
        raises ``TypeError``, which the frontend surfaces as a 500.
        """
        return VeniceAIOptionsFlow()


class VeniceAIOptionsFlow(OptionsFlow):
    """Options flow for Venice AI."""

    async def _fetch_model_options(
        self,
    ) -> tuple[list[SelectOptionDict], list[SelectOptionDict], list[SelectOptionDict], dict[str, str]]:
        """Fetch available models from Venice AI and return options + errors.

        The client is scoped entirely within this method via ``async with`` so
        that the underlying aiohttp session is guaranteed to be closed on both
        the happy path and any exception or flow-cancellation path.  Storing
        the client on ``self`` is intentionally avoided: config-flow objects can
        be abandoned between steps, and a ``self._client`` reference that
        survives past the ``finally`` block would leak the session if the flow
        is garbage-collected before cleanup runs.

        Returns:
            (chat_models, tts_models, stt_models, errors)
        """
        chat_options: list[SelectOptionDict] = []
        tts_options: list[SelectOptionDict] = []
        stt_options: list[SelectOptionDict] = []
        errors: dict[str, str] = {}

        api_key = self.config_entry.data.get(CONF_API_KEY)
        if not api_key:
            _LOGGER.warning("No API key found in config entry for options flow")
            errors["base"] = "missing_api_key"
            return chat_options, tts_options, stt_options, errors

        try:
            async with AsyncVeniceAIClient(
                api_key=api_key,
                http_client=get_async_client(self.hass),
            ) as client:
                _LOGGER.debug("Fetching text models for options flow")
                text_resp = await client.models.list(model_type="text")
                if isinstance(text_resp, list):
                    fetched = [
                        SelectOptionDict(
                            label=m.get("id", "Unknown") + (" 🔍" if m.get("model_spec", {}).get("capabilities", {}).get("supportsWebSearch", False) else ""),
                            value=m.get("id", ""),
                        )
                        for m in text_resp
                        if m.get("id")
                    ]
                    if fetched:
                        chat_options = fetched
                        _LOGGER.debug("Found %d text models", len(fetched))
                    else:
                        _LOGGER.warning("No text models found")
                else:
                    _LOGGER.error(
                        "Invalid text models response: expected list, got %s",
                        type(text_resp).__name__,
                    )

                _LOGGER.debug("Fetching TTS models for options flow")
                tts_resp = await client.models.list(model_type="tts")
                if isinstance(tts_resp, list):
                    tts_options = [
                        SelectOptionDict(label=m.get("id", "Unknown"), value=m.get("id", ""))
                        for m in tts_resp
                        if m.get("id")
                    ]
                    _LOGGER.debug("Found %d TTS models", len(tts_options))
                else:
                    _LOGGER.debug("No TTS models returned or invalid response")

                _LOGGER.debug("Fetching ASR models for options flow")
                asr_resp = await client.models.list(model_type="asr")
                if isinstance(asr_resp, list):
                    stt_options = [
                        SelectOptionDict(label=m.get("id", "Unknown"), value=m.get("id", ""))
                        for m in asr_resp
                        if m.get("id")
                    ]
                    _LOGGER.debug("Found %d STT models", len(stt_options))
                else:
                    _LOGGER.debug("No ASR models returned or invalid response")

        except AuthenticationError:
            _LOGGER.error("Authentication error fetching models for options flow")
            errors["base"] = "invalid_auth"
        except VeniceAIError as err:
            _LOGGER.error("Connection error fetching models for options flow: %s", err)
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error fetching models for options flow")
            errors["base"] = "unknown"

        # Fallback to defaults when nothing was fetched
        if not chat_options:
            chat_options = [
                SelectOptionDict(label=RECOMMENDED_CHAT_MODEL, value=RECOMMENDED_CHAT_MODEL)
            ]
        if not tts_options:
            tts_options = [
                SelectOptionDict(label=RECOMMENDED_TTS_MODEL, value=RECOMMENDED_TTS_MODEL)
            ]
        if not stt_options:
            stt_options = [
                SelectOptionDict(label=RECOMMENDED_STT_MODEL, value=RECOMMENDED_STT_MODEL)
            ]

        return chat_options, tts_options, stt_options, errors

    def _build_options_schema(
        self,
        models_options: list[SelectOptionDict],
        tts_models_options: list[SelectOptionDict],
        stt_models_options: list[SelectOptionDict],
        llm_api_options: list[SelectOptionDict] | None = None,
        skill_options: list[SelectOptionDict] | None = None,
    ) -> vol.Schema:
        """Build the voluptuous options schema from fetched model lists.

        STT and TTS sub-fields are always included so re-enabling a toggle
        immediately shows the configuration fields without needing a second
        save.  Stale values are cleared in ``async_step_init`` when the toggle
        is saved as off.
        """
        options = self.config_entry.options
        if llm_api_options is None:
            llm_api_options = []
        # Drop any stored LLM API ids that are no longer registered, so the
        # multi-select doesn't try to render an option that isn't in
        # ``llm_api_options`` (which would either render blank or be silently
        # discarded by the frontend).
        valid_api_ids = {opt["value"] for opt in llm_api_options}
        suggested_llm_apis = options.get(CONF_LLM_HASS_API) or []
        if isinstance(suggested_llm_apis, str):
            suggested_llm_apis = [suggested_llm_apis]
        suggested_llm_apis = [a for a in suggested_llm_apis if a in valid_api_ids]

        schema_fields: dict[Any, Any] = {
                vol.Optional(
                    CONF_PROMPT,
                    description={"suggested_value": options.get(CONF_PROMPT, DEFAULT_SYSTEM_PROMPT)},
                ): TemplateSelector(),
                vol.Optional(
                    CONF_CHAT_MODEL,
                    description={"suggested_value": options.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL)},
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=models_options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_MAX_TOKENS,
                    description={"suggested_value": options.get(CONF_MAX_TOKENS, RECOMMENDED_MAX_TOKENS)},
                ): NumberSelector(
                    NumberSelectorConfig(min=1, max=32768, step=1, mode="slider")
                ),
                vol.Optional(
                    CONF_TOP_P,
                    description={"suggested_value": options.get(CONF_TOP_P, RECOMMENDED_TOP_P)},
                ): NumberSelector(
                    NumberSelectorConfig(min=0.0, max=1.0, step=0.05, mode="slider")
                ),
                vol.Optional(
                    CONF_TEMPERATURE,
                    description={"suggested_value": options.get(CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE)},
                ): NumberSelector(
                    NumberSelectorConfig(min=0.0, max=2.0, step=0.05, mode="slider")
                ),
                # Multi-checkbox: matches the canonical HA pattern (openai_conversation,
                # google_generative_ai_conversation, etc).  The previous DROPDOWN +
                # custom_value combo silently dropped selections in the frontend.
                vol.Optional(
                    CONF_LLM_HASS_API,
                    description={"suggested_value": suggested_llm_apis},
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=llm_api_options,
                        multiple=True,
                    )
                ),
                vol.Optional(
                    CONF_STRIP_THINKING_RESPONSE,
                    description={"suggested_value": options.get(CONF_STRIP_THINKING_RESPONSE, False)},
                ): BooleanSelector(),
                vol.Optional(
                    CONF_DISABLE_THINKING,
                    description={"suggested_value": options.get(CONF_DISABLE_THINKING, RECOMMENDED_DISABLE_THINKING)},
                ): BooleanSelector(),
                vol.Optional(
                    CONF_CONTINUE_CONVERSATION,
                    description={"suggested_value": options.get(CONF_CONTINUE_CONVERSATION, RECOMMENDED_CONTINUE_CONVERSATION)},
                ): BooleanSelector(),
                vol.Optional(
                    CONF_ENABLE_WEB_SEARCH,
                    description={"suggested_value": options.get(CONF_ENABLE_WEB_SEARCH, RECOMMENDED_ENABLE_WEB_SEARCH)},
                ): BooleanSelector(),
                vol.Optional(
                    CONF_FUNCTION_TOOLS,
                    default=options.get(CONF_FUNCTION_TOOLS, _FUNCTION_TOOLS_PLACEHOLDER),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
                vol.Optional(
                    CONF_SKILLS,
                    description={
                        "suggested_value": [
                            s for s in options.get(CONF_SKILLS, [])
                            if skill_options and any(o["value"] == s for o in skill_options)
                        ]
                    },
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=skill_options or [],
                        multiple=True,
                    )
                ),
                vol.Optional(
                    CONF_MAX_TOOL_ITERATIONS,
                    description={"suggested_value": options.get(CONF_MAX_TOOL_ITERATIONS, RECOMMENDED_MAX_TOOL_ITERATIONS)},
                ): NumberSelector(
                    NumberSelectorConfig(min=1, max=20, step=1, mode="slider")
                ),
                vol.Optional(
                    CONF_CONTEXT_THRESHOLD,
                    description={"suggested_value": self.config_entry.options.get(
                        CONF_CONTEXT_THRESHOLD, RECOMMENDED_CONTEXT_THRESHOLD
                    )},
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1000,
                        max=200000,
                        step=1000,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                # TTS toggle — always shown; sub-fields always follow.
                vol.Optional(
                    CONF_TTS_ENABLED,
                    description={"suggested_value": options.get(CONF_TTS_ENABLED, RECOMMENDED_TTS_ENABLED)},
                ): BooleanSelector(),
        }

        tts_subfields: dict[Any, Any] = {
            vol.Optional(
                CONF_TTS_MODEL,
                description={"suggested_value": options.get(CONF_TTS_MODEL, RECOMMENDED_TTS_MODEL)},
            ): SelectSelector(
                SelectSelectorConfig(
                    options=tts_models_options,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_TTS_VOICE,
                description={"suggested_value": options.get(CONF_TTS_VOICE, RECOMMENDED_TTS_VOICE)},
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(label=voice, value=voice)
                        for voice in VENICE_TTS_VOICES
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_TTS_RESPONSE_FORMAT,
                description={"suggested_value": options.get(CONF_TTS_RESPONSE_FORMAT, RECOMMENDED_TTS_RESPONSE_FORMAT)},
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(label="MP3", value="mp3"),
                        SelectOptionDict(label="WAV", value="wav"),
                        SelectOptionDict(label="OGG", value="ogg"),
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_TTS_SPEED,
                description={"suggested_value": options.get(CONF_TTS_SPEED, RECOMMENDED_TTS_SPEED)},
            ): NumberSelector(
                NumberSelectorConfig(min=0.25, max=4.0, step=0.25, mode="slider")
            ),
        }

        # STT toggle — always shown; sub-fields always follow.
        stt_toggle: dict[Any, Any] = {
            vol.Optional(
                CONF_STT_ENABLED,
                description={"suggested_value": options.get(CONF_STT_ENABLED, RECOMMENDED_STT_ENABLED)},
            ): BooleanSelector(),
        }

        stt_subfields: dict[Any, Any] = {
            vol.Optional(
                CONF_STT_MODEL,
                description={"suggested_value": options.get(CONF_STT_MODEL, RECOMMENDED_STT_MODEL)},
            ): SelectSelector(
                SelectSelectorConfig(
                    options=stt_models_options,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_STT_RESPONSE_FORMAT,
                description={"suggested_value": options.get(CONF_STT_RESPONSE_FORMAT, RECOMMENDED_STT_RESPONSE_FORMAT)},
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(label="JSON", value="json"),
                        SelectOptionDict(label="Text", value="text"),
                        SelectOptionDict(label="SRT", value="srt"),
                        SelectOptionDict(label="Verbose JSON", value="verbose_json"),
                        SelectOptionDict(label="VTT", value="vtt"),
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_STT_TIMESTAMPS,
                description={"suggested_value": options.get(CONF_STT_TIMESTAMPS, RECOMMENDED_STT_TIMESTAMPS)},
            ): BooleanSelector(),
        }

        schema_fields.update(tts_subfields)
        schema_fields.update(stt_toggle)
        schema_fields.update(stt_subfields)

        return vol.Schema(schema_fields)

    def _fetch_llm_api_options(self) -> list[SelectOptionDict]:
        """Return a list of registered HA LLM APIs as SelectOptionDicts.

        Uses ``llm.async_get_apis(hass)`` (the actual public API — the previous
        ``async_get_api_list`` probe did not exist in HA core, so the dropdown
        always fell through to a stub "assist"-only fallback).  Each registered
        API exposes ``.id`` and ``.name``.
        """
        return [
            SelectOptionDict(label=api.name, value=api.id)
            for api in llm.async_get_apis(self.hass)
        ]

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Normalise CONF_LLM_HASS_API: empty list / blank → drop key entirely.
            llm_api_value = user_input.get(CONF_LLM_HASS_API)
            if not llm_api_value:
                user_input.pop(CONF_LLM_HASS_API, None)
            else:
                # Accept either a list (multi-select) or a single string
                # (legacy stored value).  Validate every entry is registered.
                if isinstance(llm_api_value, str):
                    llm_api_value = [llm_api_value]
                valid_ids = {api.id for api in llm.async_get_apis(self.hass)}
                filtered = [a for a in llm_api_value if a in valid_ids]
                if not filtered:
                    user_input.pop(CONF_LLM_HASS_API, None)
                else:
                    user_input[CONF_LLM_HASS_API] = filtered

            if not errors:
                # When a feature toggle is off, clear its sub-fields so stale
                # values don't persist in storage and confuse the next open.
                if not user_input.get(CONF_TTS_ENABLED, RECOMMENDED_TTS_ENABLED):
                    for key in (CONF_TTS_MODEL, CONF_TTS_VOICE, CONF_TTS_RESPONSE_FORMAT, CONF_TTS_SPEED):
                        user_input.pop(key, None)
                if not user_input.get(CONF_STT_ENABLED, RECOMMENDED_STT_ENABLED):
                    for key in (CONF_STT_MODEL, CONF_STT_RESPONSE_FORMAT, CONF_STT_TIMESTAMPS):
                        user_input.pop(key, None)

                return self.async_create_entry(title="", data=user_input)

        models, tts_models, stt_models, fetch_errors = await self._fetch_model_options()
        llm_api_options = self._fetch_llm_api_options()

        # Load skills for the multi-select
        skill_options: list[SelectOptionDict] = []
        try:
            from .skills import SkillManager
            skill_manager = await SkillManager.async_get_instance(self.hass)
            skill_options = [
                SelectOptionDict(label=s.name, value=s.name)
                for s in skill_manager.get_all_skills()
            ]
        except Exception:
            _LOGGER.debug("Could not load skills for options form", exc_info=True)

        options_schema = self._build_options_schema(models, tts_models, stt_models, llm_api_options, skill_options)

        # Merge fetch errors with validation errors
        if fetch_errors:
            errors.update(fetch_errors)

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            errors=errors,
        )
