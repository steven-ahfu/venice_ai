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
    VOICE_CHAT_MODELS,
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
    MODEL_VOICES,
    VENICE_TTS_VOICES,
    friendly_voice_label,
    tts_model_sublabel,
)

_LOGGER = logging.getLogger(__name__)


# Try to import DEFAULT_SYSTEM_PROMPT; fallback if not available
try:
    from .conversation import DEFAULT_SYSTEM_PROMPT
except ImportError:
    _LOGGER.warning("Could not import DEFAULT_SYSTEM_PROMPT from conversation.py, using fallback.")
    DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant."

def apply_toggle_cleanup(user_input: dict[str, Any]) -> dict[str, Any]:
    """Drop TTS/STT sub-fields when their respective toggle is off.

    Mutates and returns ``user_input`` so the OptionsFlow's saved data only
    carries keys that match the user's toggle state — otherwise stale sub-field
    values can re-enable an entity the user just disabled the next time the
    options dict is replayed (HA merges new options over the previous dict).
    """
    if not user_input.get(CONF_TTS_ENABLED, RECOMMENDED_TTS_ENABLED):
        for key in (CONF_TTS_MODEL, CONF_TTS_VOICE, CONF_TTS_RESPONSE_FORMAT, CONF_TTS_SPEED):
            user_input.pop(key, None)
    if not user_input.get(CONF_STT_ENABLED, RECOMMENDED_STT_ENABLED):
        for key in (CONF_STT_MODEL, CONF_STT_RESPONSE_FORMAT, CONF_STT_TIMESTAMPS):
            user_input.pop(key, None)
    return user_input


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): cv.string,
    }
)


def _chat_model_label(model: dict[str, Any]) -> str:
    """Format a chat model dropdown label with an estimated blended cost.

    Estimate assumes a 60% input / 40% output token mix per conversation,
    so a model that costs $1/M in and $3.20/M out is shown as
    ``(0.60 × $1.00) + (0.40 × $3.20) = $1.88/M chat tokens``.
    Live API pricing is preferred; for curated models the static snapshot in
    ``VOICE_CHAT_MODELS`` is the fallback, and their tier is appended.
    Returns ``"<Display Name> · ~$X.YZ/M · <tier>"``.
    """
    spec = model.get("model_spec") or {}
    curated = VOICE_CHAT_MODELS.get(model.get("id", ""))
    name = spec.get("name") or (curated or {}).get("name") or model.get("id", "Unknown")
    pricing = (spec.get("pricing") or {})
    input_price = pricing.get("input", {}).get("usd")
    output_price = pricing.get("output", {}).get("usd")
    if (input_price is None or output_price is None) and curated:
        input_price = curated.get("input_usd")
        output_price = curated.get("output_usd")
    tier_suffix = f" · {curated['tier']}" if curated else ""
    if input_price is None or output_price is None:
        return f"{name}{tier_suffix}"
    blended = 0.60 * input_price + 0.40 * output_price
    return f"{name} · ~${blended:.2f}/M{tier_suffix}"


def curate_chat_models(
    fetched: list[SelectOptionDict], current_model: str | None = None
) -> list[SelectOptionDict]:
    """Reduce the fetched chat-model options to the curated voice-chat set.

    Keeps ``VOICE_CHAT_MODELS`` dict order (recommended → value → step-up →
    ultra-light). A currently-selected model that is not curated is appended
    so an existing config entry never shows an empty/invalid selection. If
    Venice has rotated out every curated model, the full fetched list is
    returned unchanged rather than an empty dropdown.
    """
    by_id = {opt["value"]: opt for opt in fetched}
    curated = [by_id[mid] for mid in VOICE_CHAT_MODELS if mid in by_id]
    if not curated:
        return fetched
    if current_model and current_model in by_id and current_model not in VOICE_CHAT_MODELS:
        curated.append(by_id[current_model])
    return curated


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
            self._async_abort_entries_match({CONF_API_KEY: user_input[CONF_API_KEY]})
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
    ) -> tuple[list[SelectOptionDict], list[SelectOptionDict], list[SelectOptionDict], dict[str, list[str]], dict[str, str]]:
        """Fetch available models from Venice AI.

        Voice lists for every TTS model are returned as a model-id → voice-ids
        map so the voice step can be built without an extra API call after the
        user picks a model.

        Returns:
            (chat_models, tts_models, stt_models, voices_by_model, errors)
        """
        chat_options: list[SelectOptionDict] = []
        tts_options: list[SelectOptionDict] = []
        stt_options: list[SelectOptionDict] = []
        voices_by_model: dict[str, list[str]] = {}
        errors: dict[str, str] = {}

        api_key = self.config_entry.data.get(CONF_API_KEY)
        if not api_key:
            _LOGGER.warning("No API key found in config entry for options flow")
            errors["base"] = "missing_api_key"
            return chat_options, tts_options, stt_options, voices_by_model, errors

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
                            label=_chat_model_label(m),
                            value=m.get("id", ""),
                        )
                        for m in text_resp
                        if m.get("id")
                        and m.get("model_spec", {})
                            .get("capabilities", {})
                            .get("supportsFunctionCalling")
                            is True
                    ]
                    if fetched:
                        chat_options = curate_chat_models(
                            fetched,
                            self.config_entry.options.get(CONF_CHAT_MODEL),
                        )
                        _LOGGER.debug(
                            "Found %d text models, %d after voice-chat curation",
                            len(fetched), len(chat_options),
                        )
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
                        SelectOptionDict(
                            label=tts_model_sublabel(m.get("id", "")),
                            value=m.get("id", ""),
                        )
                        for m in tts_resp
                        if m.get("id")
                    ]
                    for m in tts_resp:
                        model_id = m.get("id")
                        if not model_id:
                            continue
                        voices = m.get("model_spec", {}).get("voices", []) or []
                        if voices:
                            voices_by_model[model_id] = list(voices)
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

        # Fallback to defaults when nothing was fetched — offer the curated
        # set with snapshot pricing so options stay usable while offline.
        if not chat_options:
            chat_options = [
                SelectOptionDict(label=_chat_model_label({"id": model_id}), value=model_id)
                for model_id in VOICE_CHAT_MODELS
            ]
        if not tts_options:
            tts_options = [
                SelectOptionDict(label=tts_model_sublabel(model_id), value=model_id)
                for model_id in MODEL_VOICES
            ] or [SelectOptionDict(label=tts_model_sublabel(RECOMMENDED_TTS_MODEL), value=RECOMMENDED_TTS_MODEL)]
        if not stt_options:
            stt_options = [SelectOptionDict(label=RECOMMENDED_STT_MODEL, value=RECOMMENDED_STT_MODEL)]

        return chat_options, tts_options, stt_options, voices_by_model, errors

    def _build_options_schema(
        self,
        models_options: list[SelectOptionDict],
        tts_models_options: list[SelectOptionDict],
        stt_models_options: list[SelectOptionDict],
        llm_api_options: list[SelectOptionDict] | None = None,
    ) -> vol.Schema:
        """Build the voluptuous options schema from fetched model lists.

        The TTS voice picker lives on a dedicated follow-up step so its
        choices can depend on the TTS model the user just selected. STT and
        TTS sub-fields are otherwise always included so re-enabling a toggle
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
                    NumberSelectorConfig(min=1, max=32768, step=1, mode="box")
                ),
                vol.Optional(
                    CONF_TOP_P,
                    description={"suggested_value": options.get(CONF_TOP_P, RECOMMENDED_TOP_P)},
                ): NumberSelector(
                    NumberSelectorConfig(min=0.0, max=1.0, step=0.05, mode="box")
                ),
                vol.Optional(
                    CONF_TEMPERATURE,
                    description={"suggested_value": options.get(CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE)},
                ): NumberSelector(
                    NumberSelectorConfig(min=0.0, max=2.0, step=0.05, mode="box")
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
                # BooleanSelector toggles MUST use ``default=`` (not
                # ``suggested_value``): the HA frontend initialises boolean
                # fields to off and ignores ``suggested_value``, so a toggle
                # built with ``suggested_value`` always renders unchecked and
                # submits ``False`` even when the stored/recommended value is
                # True. This is what silently disabled TTS and skipped the
                # voice step. ``default=`` is the canonical HA core pattern.
                vol.Optional(
                    CONF_STRIP_THINKING_RESPONSE,
                    default=options.get(CONF_STRIP_THINKING_RESPONSE, False),
                ): BooleanSelector(),
                vol.Optional(
                    CONF_DISABLE_THINKING,
                    default=options.get(CONF_DISABLE_THINKING, RECOMMENDED_DISABLE_THINKING),
                ): BooleanSelector(),
                vol.Optional(
                    CONF_CONTINUE_CONVERSATION,
                    default=options.get(CONF_CONTINUE_CONVERSATION, RECOMMENDED_CONTINUE_CONVERSATION),
                ): BooleanSelector(),
                vol.Optional(
                    CONF_ENABLE_WEB_SEARCH,
                    default=options.get(CONF_ENABLE_WEB_SEARCH, RECOMMENDED_ENABLE_WEB_SEARCH),
                ): BooleanSelector(),
                vol.Optional(
                    CONF_MAX_TOOL_ITERATIONS,
                    description={"suggested_value": options.get(CONF_MAX_TOOL_ITERATIONS, RECOMMENDED_MAX_TOOL_ITERATIONS)},
                ): NumberSelector(
                    NumberSelectorConfig(min=1, max=20, step=1, mode="box")
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
                    default=options.get(CONF_TTS_ENABLED, RECOMMENDED_TTS_ENABLED),
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
                NumberSelectorConfig(min=0.25, max=4.0, step=0.25, mode="box")
            ),
        }

        # STT toggle — always shown; sub-fields always follow.
        stt_toggle: dict[Any, Any] = {
            vol.Optional(
                CONF_STT_ENABLED,
                default=options.get(CONF_STT_ENABLED, RECOMMENDED_STT_ENABLED),
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
                default=options.get(CONF_STT_TIMESTAMPS, RECOMMENDED_STT_TIMESTAMPS),
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

    def _build_skills_schema(
        self,
        skill_options: list[SelectOptionDict],
    ) -> vol.Schema:
        """Build the schema for the skills & tools step."""
        options = self.config_entry.options
        valid_skill_values = {o["value"] for o in skill_options}
        return vol.Schema({
            vol.Optional(
                CONF_SKILLS,
                description={
                    "suggested_value": [
                        s for s in options.get(CONF_SKILLS, [])
                        if s in valid_skill_values
                    ]
                },
            ): SelectSelector(
                SelectSelectorConfig(
                    options=skill_options,
                    multiple=True,
                )
            ),
        })

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the main options (page 1 of 3)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Normalise CONF_LLM_HASS_API: empty list / blank → drop key entirely.
            llm_api_value = user_input.get(CONF_LLM_HASS_API)
            if not llm_api_value:
                user_input.pop(CONF_LLM_HASS_API, None)
            else:
                if isinstance(llm_api_value, str):
                    llm_api_value = [llm_api_value]
                valid_ids = {api.id for api in llm.async_get_apis(self.hass)}
                filtered = [a for a in llm_api_value if a in valid_ids]
                if not filtered:
                    user_input.pop(CONF_LLM_HASS_API, None)
                else:
                    user_input[CONF_LLM_HASS_API] = filtered

            if not errors:
                tts_enabled = user_input.get(CONF_TTS_ENABLED, RECOMMENDED_TTS_ENABLED)
                apply_toggle_cleanup(user_input)

                # Carry existing skills forward (they're edited on the next step).
                user_input.setdefault(CONF_SKILLS, self.config_entry.options.get(CONF_SKILLS, []))
                self._init_data = user_input

                if tts_enabled:
                    return await self.async_step_tts_voice()
                # TTS off — drop any stored voice and skip straight to skills.
                self._init_data.pop(CONF_TTS_VOICE, None)
                return await self.async_step_skills_and_tools()

        models, tts_models, stt_models, voices_by_model, fetch_errors = await self._fetch_model_options()
        self._voices_by_model = voices_by_model
        llm_api_options = self._fetch_llm_api_options()

        options_schema = self._build_options_schema(models, tts_models, stt_models, llm_api_options)

        if fetch_errors:
            errors.update(fetch_errors)

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            errors=errors,
        )

    async def async_step_tts_voice(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a voice for the TTS model chosen on the previous step."""
        init_data: dict[str, Any] = getattr(self, "_init_data", {})
        selected_model = init_data.get(
            CONF_TTS_MODEL,
            self.config_entry.options.get(CONF_TTS_MODEL, RECOMMENDED_TTS_MODEL),
        )

        if user_input is not None:
            init_data[CONF_TTS_VOICE] = user_input[CONF_TTS_VOICE]
            self._init_data = init_data
            return await self.async_step_skills_and_tools()

        # Prefer live-fetched voices; fall back to the static map when the API
        # call in async_step_init failed or returned nothing for this model.
        voices_by_model: dict[str, list[str]] = getattr(self, "_voices_by_model", {})
        voices = voices_by_model.get(selected_model) or MODEL_VOICES.get(
            selected_model, VENICE_TTS_VOICES
        )

        voice_options = [
            SelectOptionDict(label=friendly_voice_label(selected_model, v), value=v)
            for v in voices
        ]

        previous_voice = self.config_entry.options.get(CONF_TTS_VOICE, RECOMMENDED_TTS_VOICE)
        valid_values = {v for v in voices}
        suggested = previous_voice if previous_voice in valid_values else (
            voices[0] if voices else RECOMMENDED_TTS_VOICE
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_TTS_VOICE,
                    description={"suggested_value": suggested},
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=voice_options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="tts_voice",
            data_schema=schema,
            description_placeholders={
                "model_label": tts_model_sublabel(selected_model),
            },
        )

    async def async_step_skills_and_tools(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Skills and function calling options (page 2 of 2)."""
        if user_input is not None:
            merged = {**getattr(self, "_init_data", {}), **user_input}
            return self.async_create_entry(title="", data=merged)

        # Load skills for the multi-select.
        skill_options: list[SelectOptionDict] = []
        try:
            from .skills import SkillManager
            skill_manager = await SkillManager.async_get_instance(self.hass)
            await skill_manager.async_load_skills()
            skill_options = [
                SelectOptionDict(label=f"{s.name} — {s.description}", value=s.name)
                for s in skill_manager.get_all_skills()
            ]
        except Exception:
            _LOGGER.debug("Could not load skills for options form", exc_info=True)

        # Load tools for the read-only description.
        tools_path = "config/venice_ai/tools.yaml"
        tools_names = "(none)"
        try:
            from .tools import ToolManager
            tool_manager = await ToolManager.async_get_instance(self.hass)
            await tool_manager.async_load_tools()
            tools_path = str(tool_manager.user_tools_path)
            loaded = tool_manager.get_all_tools()
            if loaded:
                tools_names = ", ".join(f"`{t.name}`" for t in loaded)
        except Exception:
            _LOGGER.debug("Could not load tools for options form", exc_info=True)
            tools_names = "(error loading tools)"

        return self.async_show_form(
            step_id="skills_and_tools",
            data_schema=self._build_skills_schema(skill_options),
            description_placeholders={
                "tools_path": tools_path,
                "tools_names": tools_names,
            },
        )
