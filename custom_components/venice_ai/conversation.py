"""Conversation support for Venice AI using ConversationEntity pattern."""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import re
from collections import OrderedDict
from typing import Any

from homeassistant.components import conversation as conversation_component
from homeassistant.components.conversation import (
    HOME_ASSISTANT_AGENT,
    ConversationEntity,
    ConversationEntityFeature,
    ConversationInput,
    ConversationResult,
    ChatLog,
    UserContent,
    AssistantContent,
    SystemContent,
    ToolResultContent,
    ConverseError,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LLM_HASS_API
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, TemplateError
from homeassistant.helpers import intent, llm, device_registry as dr, selector
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.template import Template
from homeassistant.util import ulid as ulid_util

from .client import AsyncVeniceAIClient, RateLimitError, VeniceAIError
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
    CONF_ENABLE_WEB_SEARCH,
    RECOMMENDED_ENABLE_WEB_SEARCH,
    CONF_CONTINUE_CONVERSATION,
    RECOMMENDED_CONTINUE_CONVERSATION,
    CONF_CONTEXT_THRESHOLD,
    CONF_SKILLS,
    DOMAIN,
    RECOMMENDED_CONTEXT_THRESHOLD,
    HAS_VOLUPTUOUS_OPENAPI,
    MAX_CHAT_HISTORY_SIZE,
    MAX_CHAT_LOG_LENGTH,
    RECOMMENDED_CHAT_MODEL,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_MAX_TOOL_ITERATIONS,
    RECOMMENDED_TEMPERATURE,
    RECOMMENDED_TOP_P,
)
from .functions import get_function
from .helpers import get_exposed_entities

if HAS_VOLUPTUOUS_OPENAPI:
    from voluptuous_openapi import convert as voluptuous_convert  # type: ignore[import-untyped]

_LOGGER = logging.getLogger(__name__)

# Default system prompt for Venice AI
DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful AI assistant for {{ ha_name }}. "
    "You can control lights, switches, climate, media players, and other smart home devices. "
    "Always be concise and helpful."
    "{% if skills %}\n\n## Available Skills\n"
    "{% for skill in skills %}### {{ skill.name }}\n{{ skill.content }}\n{% endfor %}"
    "{% endif %}"
)


def _control_home_assistant_enabled(llm_api: Any) -> bool:
    """Return whether Home Assistant control/routing is enabled."""
    if llm_api in (None, "", [], (), {}):
        return False
    return True


def _hass_result_satisfied(result: ConversationResult | None) -> bool:
    """Return whether a native Home Assistant result fully handled the request."""
    return result is not None and getattr(result.response, "error_code", None) is None


async def _async_try_hass_agent(
    hass: HomeAssistant,
    user_input: ConversationInput,
    current_agent: Any,
) -> ConversationResult | None:
    """Try the built-in Home Assistant agent before Venice."""
    hass_agent = conversation_component.async_get_agent(hass, HOME_ASSISTANT_AGENT)
    if hass_agent is None or hass_agent is current_agent:
        _LOGGER.debug("Home Assistant agent not available for native intent handling")
        return None

    try:
        return await hass_agent.async_process(user_input)
    except Exception as err:
        _LOGGER.warning("Native Home Assistant handling failed: %s", err)
        return None


_VENICE_THINKING_RE = re.compile(r" thinking\b.*? end of thinking\b", re.DOTALL | re.IGNORECASE)


def _strip_thinking(text: str) -> str:
    """Remove <think>…</think> (or  thinking… end of thinking ) blocks from model output.

    Handles both the XML-style tags used by some reasoning models and the
    literal `` thinking`` / `` end of thinking`` markers emitted by Venice AI.
    Only matched marker pairs are stripped; an unmatched Venice opener is left
    in place so legitimate prose containing the phrase ``end of thinking`` is
    not silently truncated.
    """
    if not text:
        return text
    # XML-style <think>…</think>
    while True:
        start = text.lower().find("<think>")
        if start == -1:
            break
        end = text.lower().find("</think>", start)
        if end == -1:
            # unmatched open tag – strip to end to be safe
            text = text[:start].strip()
            break
        text = text[:start] + text[end + 8:]
    # Venice-style  thinking… end of thinking — strip only matched pairs.
    text = _VENICE_THINKING_RE.sub("", text)
    return text.strip()


def _build_venice_params(
    disable_thinking: bool, enable_web_search: bool
) -> dict[str, Any] | None:
    """Assemble the ``venice_parameters`` payload, or None if both flags are off.

    Returning None (not an empty dict) matters because an empty dict still
    serialises as ``"venice_parameters": {}`` on the wire, which some Venice
    backends reject.
    """
    if not (disable_thinking or enable_web_search):
        return None
    params: dict[str, Any] = {}
    if disable_thinking:
        params["disable_thinking"] = True
    if enable_web_search:
        params["enable_web_search"] = "auto"
    return params


def _convert_schema_to_hashable(obj: Any) -> Any:
    """Recursively convert a voluptuous schema into a hashable representation."""
    if isinstance(obj, dict):
        return frozenset((k, _convert_schema_to_hashable(v)) for k, v in obj.items())
    if isinstance(obj, list):
        return tuple(_convert_schema_to_hashable(v) for v in obj)
    if isinstance(obj, selector.Selector):
        _LOGGER.debug(
            "_convert_schema_to_hashable: replacing selector %s with str",
            obj.__class__.__name__,
        )
        return str
    return obj


def _format_venice_schema(raw_schema: dict[str, Any]) -> dict[str, Any]:
    """Convert a schema dict into a Venice-compatible OpenAPI-like schema.

    Recursively traverses the schema, preserving nested dict/list structures
    and selector metadata (e.g., SelectSelector options become JSON Schema
    ``enum`` values) while mapping Python types to JSON Schema types.
    """
    schema: dict[str, Any] = {}
    for key, val in raw_schema.items():
        # Unwrap voluptuous Required/Optional wrappers
        if hasattr(val, "schema"):
            val = val.schema

        if val is str or val is Any:
            schema[key] = {"type": "string"}
        elif val is int:
            schema[key] = {"type": "integer"}
        elif val is float:
            schema[key] = {"type": "number"}
        elif val is bool:
            schema[key] = {"type": "boolean"}
        elif isinstance(val, selector.SelectSelector):
            config = getattr(val, "config", None)
            options = getattr(config, "options", None) if config else None
            if options:
                schema[key] = {"type": "string", "enum": list(options)}
                _LOGGER.debug(
                    "_format_venice_schema: preserved SelectSelector with %d options for key %s",
                    len(options),
                    key,
                )
            else:
                schema[key] = {"type": "string"}
        elif isinstance(val, selector.Selector):
            _LOGGER.debug(
                "_format_venice_schema: converting selector %s to string for key %s",
                val.__class__.__name__,
                key,
            )
            schema[key] = {"type": "string"}
        elif isinstance(val, dict):
            schema[key] = {"type": "object", "properties": _format_venice_schema(val)}
        elif isinstance(val, list):
            schema[key] = {
                "type": "array",
                "items": _format_venice_schema({"__item__": val[0]}).get("__item__", {}),
            }
        else:
            _LOGGER.debug(
                "_format_venice_schema: unsupported type %s for key %s, defaulting to string",
                type(val).__name__,
                key,
            )
            schema[key] = {"type": "string"}
    return schema


def _convert_tool_parameters(tool: llm.Tool) -> dict[str, Any] | None:
    """Convert tool parameters schema to Venice-compatible format."""
    if not tool.parameters:
        return None

    if HAS_VOLUPTUOUS_OPENAPI:
        try:
            hashable = _convert_schema_to_hashable(tool.parameters)
            parameters_schema = voluptuous_convert(hashable)
            # voluptuous_openapi may return list for 'anyOf' patterns; simplify
            if isinstance(parameters_schema, list):
                parameters_schema = parameters_schema[0]
            if isinstance(parameters_schema, dict) and "properties" in parameters_schema:
                def _ensure_types(sub_schema: dict[str, Any]) -> None:
                    if "properties" in sub_schema:
                        for _, prop in sub_schema["properties"].items():
                            if isinstance(prop, dict):
                                if "type" not in prop:
                                    if "properties" in prop:
                                        prop["type"] = "object"
                                    elif "enum" in prop:
                                        prop["type"] = "string"
                                    else:
                                        prop["type"] = "string"
                                _ensure_types(prop)

                _ensure_types(parameters_schema)
                return parameters_schema
            elif isinstance(parameters_schema, dict):
                return {"type": "object", "properties": parameters_schema}
            else:
                _LOGGER.warning(
                    "Unexpected schema type from voluptuous_openapi: %s",
                    type(parameters_schema).__name__,
                )
                return {"type": "object", "properties": {}}
        except Exception as e:
            _LOGGER.error("Failed to convert schema: %s", e, exc_info=True)
            return {"type": "object", "properties": {}}
    else:
        _LOGGER.debug("Cannot perform detailed schema conversion without voluptuous_openapi.")
        return {"type": "object", "properties": {}}


def _convert_chat_log_to_venice_messages(
    chat_log: ChatLog,
    system_prompt: str,
    strip_thinking: bool = False,
) -> list[dict[str, Any]]:
    """Convert Home Assistant ChatLog to Venice AI message format."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    for msg in chat_log.content:
        if isinstance(msg, UserContent):
            messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AssistantContent):
            content = _strip_thinking(msg.content) if strip_thinking else msg.content
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": content}
            if msg.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.tool_name,
                            "arguments": json.dumps(tc.tool_args),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            # Guard: some APIs reject empty tool_calls arrays
            if assistant_msg.get("tool_calls") == []:
                assistant_msg.pop("tool_calls")
            messages.append(assistant_msg)
        elif isinstance(msg, ToolResultContent):
            messages.append({
                "role": "tool",
                "tool_call_id": msg.tool_call_id,
                "content": json.dumps(msg.tool_result),
            })
        elif isinstance(msg, SystemContent):
            _LOGGER.debug("Skipping SystemContent in chat_log to avoid duplicate system prompt")
        else:
            _LOGGER.warning("Unsupported message type for Venice conversion: %s", type(msg))

    return messages


def _trim_chat_log(chat_log: ChatLog) -> None:
    """Trim chat log to prevent unbounded growth during long conversations.

    Preserves the first user message and the most recent messages up to
    MAX_CHAT_LOG_LENGTH. System and tool-result messages are trimmed first.
    """
    content = chat_log.content
    if len(content) <= MAX_CHAT_LOG_LENGTH:
        return

    keep_first = [content[0]]
    tail = content[-(MAX_CHAT_LOG_LENGTH - 1):]
    trimmed = keep_first + tail
    _LOGGER.debug(
        "Trimmed chat log from %d to %d messages", len(content), len(trimmed)
    )
    chat_log.content.clear()
    chat_log.content.extend(trimmed)


def _truncate_message_history(chat_log: ChatLog) -> None:
    """Clear middle of history on token overflow across multiple turns.

    Fires reactively after an API response reports total_tokens exceeding
    the configured threshold. Only takes effect when multiple user messages
    have accumulated (last_user_idx > 1). Complements the count-based
    _trim_chat_log() which runs proactively before each API call.
    """
    messages = chat_log.content
    last_user_idx = None
    for i in reversed(range(len(messages))):
        if isinstance(messages[i], UserContent):
            last_user_idx = i
            break
    if last_user_idx is not None and last_user_idx > 1:
        removed = last_user_idx - 1
        del messages[1:last_user_idx]
        _LOGGER.info(
            "Token threshold exceeded; removed %d messages from conversation history",
            removed,
        )


class VeniceAIConversationEntity(ConversationEntity):
    """Venice AI conversation entity."""

    _attr_supported_features = ConversationEntityFeature.CONTROL

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the entity."""
        self.entry = entry
        self._client = entry.runtime_data.client
        self._attr_unique_id = f"{entry.entry_id}_conversation"
        self._attr_name = entry.title
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Venice AI",
            model="Conversation",
            entry_type=dr.DeviceEntryType.SERVICE,
        )
        # Conversation history keyed by conversation_id.
        # OrderedDict used as an LRU cache: entries are moved to the tail on
        # each access and the oldest (head) entry is evicted when the dict
        # exceeds MAX_CHAT_HISTORY_SIZE, preventing unbounded memory growth.
        self._chat_logs: OrderedDict[str, ChatLog] = OrderedDict()

    def _get_or_create_chat_log(self, conversation_id: str | None) -> ChatLog:
        """Return the persisted ChatLog for *conversation_id*, or create a new one.

        Uses the OrderedDict as an LRU cache:
        - On hit: move the entry to the tail (most-recently-used position).
        - On miss: create a new empty ChatLog, insert at the tail, and evict the
          oldest entry (head) if the cache exceeds MAX_CHAT_HISTORY_SIZE.

        The caller is responsible for appending the new user message after this
        method returns.
        """
        cid = conversation_id or ulid_util.ulid_now()
        if cid in self._chat_logs:
            # Promote to most-recently-used
            self._chat_logs.move_to_end(cid)
            _LOGGER.debug("Resuming existing conversation %s (%d messages)", cid, len(self._chat_logs[cid].content))
            return self._chat_logs[cid]

        # New conversation. ChatLog requires `hass` as its first dataclass field —
        # without it instantiation raises TypeError synchronously, which HA's
        # pipeline surfaces as "Unexpected error during intent recognition".
        chat_log = ChatLog(hass=self.hass, conversation_id=cid, content=[])
        self._chat_logs[cid] = chat_log
        # Evict least-recently-used if over the limit
        if len(self._chat_logs) > MAX_CHAT_HISTORY_SIZE:
            evicted_id, _ = self._chat_logs.popitem(last=False)
            _LOGGER.debug(
                "Evicted oldest conversation %s from history cache (limit=%d)",
                evicted_id,
                MAX_CHAT_HISTORY_SIZE,
            )
        _LOGGER.debug("Started new conversation %s", cid)
        return chat_log

    @property
    def supported_languages(self) -> list[str]:
        """Return list of supported languages."""
        return ["en", "es", "fr", "de", "it", "pt", "nl", "ja", "ko", "zh"]

    @property
    def supported_options(self) -> list[str]:
        """Return list of supported options."""
        return [CONF_PROMPT, CONF_CHAT_MODEL, CONF_MAX_TOKENS, CONF_TEMPERATURE, CONF_TOP_P, CONF_MAX_TOOL_ITERATIONS, CONF_STRIP_THINKING_RESPONSE, CONF_DISABLE_THINKING, CONF_ENABLE_WEB_SEARCH, CONF_CONTINUE_CONVERSATION, CONF_CONTEXT_THRESHOLD]

    async def async_process(
        self, user_input: ConversationInput
    ) -> ConversationResult:
        """Process a conversation input."""
        options = self.entry.options
        llm_api = options.get(CONF_LLM_HASS_API)

        if _control_home_assistant_enabled(llm_api):
            hass_result = await _async_try_hass_agent(self.hass, user_input, self)
            if _hass_result_satisfied(hass_result):
                return hass_result

        return await self._async_process_with_venice(user_input, options, llm_api)

    async def _async_process_with_venice(
        self,
        user_input: ConversationInput,
        options: dict[str, Any],
        llm_api: Any,
    ) -> ConversationResult:
        """Process a conversation input with Venice and optional tool use."""
        model: str = options.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL)
        # NumberSelector with step=1 still returns a float from the HA frontend;
        # the Venice API (and our client typing) expects int for max_tokens.
        max_tokens: int = int(options.get(CONF_MAX_TOKENS, RECOMMENDED_MAX_TOKENS))
        temperature: float = float(options.get(CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE))
        top_p: float = float(options.get(CONF_TOP_P, RECOMMENDED_TOP_P))
        strip_thinking: bool = bool(options.get(CONF_STRIP_THINKING_RESPONSE, False))
        prompt_template_str = options.get(CONF_PROMPT, DEFAULT_SYSTEM_PROMPT)

        # Render system prompt template with Home Assistant context so
        # template functions (e.g. now(), states(), area_entities()) work.
        try:
            prompt_template = Template(prompt_template_str, self.hass)
            exposed_entities = get_exposed_entities(self.hass)

            # Load enabled skills and build skills context for system prompt
            skills_context: list[dict[str, str]] = []
            enabled_skill_names = options.get(CONF_SKILLS, [])
            if enabled_skill_names:
                try:
                    from .skills import SkillManager
                    skill_manager = await SkillManager.async_get_instance(self.hass)
                    for skill in skill_manager.get_enabled_skills(enabled_skill_names):
                        skills_context.append({
                            "name": skill.name,
                            "description": skill.description,
                            "content": skill.content,
                        })
                except Exception as skills_err:
                    _LOGGER.warning("Failed to load skills: %s", skills_err)

            system_prompt = prompt_template.async_render(
                {
                    "ha_name": self.hass.config.location_name,
                    "exposed_entities": exposed_entities,
                    "current_device_id": user_input.device_id,
                    "user_input": user_input,
                    "skills": skills_context,
                },
                parse_result=False,
            )
        except TemplateError as err:
            _LOGGER.error("Error rendering prompt template: %s", err)
            raise HomeAssistantError(f"Error rendering prompt: {err}") from err

        # Set up LLM API(s) if configured.  Accepts either a list of API ids
        # (new multi-select form) or a single string (legacy stored value).
        tools: list[llm.Tool] = []
        llm_context: llm.LLMContext | None = None
        if llm_api:
            if isinstance(llm_api, str):
                llm_api_ids = [llm_api]
            else:
                llm_api_ids = list(llm_api)
            llm_context = llm.LLMContext(
                platform=DOMAIN,
                context=user_input.context,
                language=user_input.language,
                assistant=HOME_ASSISTANT_AGENT,
                device_id=user_input.device_id,
            )
            for api_id in llm_api_ids:
                try:
                    api = await llm.async_get_api(self.hass, api_id, llm_context)
                    tools.extend(api.tools)
                except Exception as err:
                    _LOGGER.warning("Failed to get LLM API %s: %s", api_id, err)

        # Convert tools to Venice format
        venice_tools = []
        for tool in tools:
            tool_dict: dict[str, Any] = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                },
            }
            parameters_schema = _convert_tool_parameters(tool)
            if parameters_schema is None and tool.parameters:
                _LOGGER.warning(
                    "Could not format params for tool %s. Sending without params.", tool.name
                )
            else:
                tool_dict["function"]["parameters"] = parameters_schema or {"type": "object", "properties": {}}
            venice_tools.append(tool_dict)

        # Load function tools from the ToolManager (bundled + user file).
        # Replaces the previous CONF_FUNCTION_TOOLS YAML textbox: tools now
        # live in default_tools.yaml (shipped) and /config/venice_ai/tools.yaml
        # (optional user overrides), validated once at load time.
        function_configs: list[dict] = []
        try:
            from .tools import ToolManager
            tool_manager = await ToolManager.async_get_instance(self.hass)
            for tool in tool_manager.get_all_tools():
                fc = tool.config
                function_configs.append(fc)
                venice_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": fc.get("parameters", {"type": "object", "properties": {}}),
                    },
                })
        except Exception as tools_err:
            _LOGGER.error("Failed to load Venice AI tools: %s", tools_err)

        # Retrieve existing chat log or create a new one, then append the new user message.
        # History is persisted across calls so the model has full multi-turn context.
        chat_log = self._get_or_create_chat_log(user_input.conversation_id)
        chat_log.content.append(UserContent(content=user_input.text))

        assistant_response_content = None
        text_content = ""

        max_tool_iterations: int = int(options.get(CONF_MAX_TOOL_ITERATIONS, RECOMMENDED_MAX_TOOL_ITERATIONS))

        try:
            _trim_chat_log(chat_log)
            for iteration in range(max_tool_iterations):
                messages = _convert_chat_log_to_venice_messages(
                    chat_log, system_prompt, strip_thinking=strip_thinking
                )

                if not messages:
                    _LOGGER.error("Message list is empty before sending to API.")
                    raise HomeAssistantError("Message list is empty before sending to API.")

                venice_params = _build_venice_params(
                    disable_thinking=options.get(CONF_DISABLE_THINKING, RECOMMENDED_DISABLE_THINKING),
                    enable_web_search=options.get(CONF_ENABLE_WEB_SEARCH, RECOMMENDED_ENABLE_WEB_SEARCH),
                )
                response_data = await self._client.chat.completions.create_non_streaming(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    tools=venice_tools if venice_tools else None,
                    venice_parameters=venice_params,
                    stream=False,
                )
                if not isinstance(response_data, dict):
                    _LOGGER.error(
                        "Invalid response type from Venice AI: %s",
                        type(response_data).__name__,
                    )
                    raise HomeAssistantError(
                        f"Received invalid response type: {type(response_data).__name__}"
                    )

                if not response_data.get("choices"):
                    _LOGGER.error("Invalid response from Venice AI: %s", response_data)
                    raise HomeAssistantError("Received invalid response")

                choice = response_data["choices"][0]
                if not isinstance(choice, dict):
                    _LOGGER.error(
                        "Invalid choice type in Venice AI response: %s",
                        type(choice).__name__,
                    )
                    raise HomeAssistantError("Received invalid choice format")

                message = choice.get("message", {})
                if not isinstance(message, dict):
                    _LOGGER.error(
                        "Invalid message type in Venice AI response: %s",
                        type(message).__name__,
                    )
                    raise HomeAssistantError("Received invalid message format")

                text_content = message.get("content", "")
                if strip_thinking:
                    text_content = _strip_thinking(text_content)
                tool_calls = message.get("tool_calls", [])

                # Reactive token-based truncation: clear history middle if context is filling up
                usage = response_data.get("usage", {}) if isinstance(response_data, dict) else {}
                total_tokens: int = int(usage.get("total_tokens", 0) or 0)
                context_threshold: int = int(options.get(CONF_CONTEXT_THRESHOLD, RECOMMENDED_CONTEXT_THRESHOLD))
                if total_tokens > context_threshold:
                    _truncate_message_history(chat_log)

                if not tool_calls:
                    assistant_response_content = text_content
                    break

                # Process tool calls
                # Build ToolInput list for AssistantContent.tool_calls so history is correct
                tool_inputs_for_history: list[llm.ToolInput] = []
                for tc in tool_calls:
                    cid = tc.get("id")
                    fn = tc.get("function", {})
                    tname = fn.get("name")
                    try:
                        targs = json.loads(fn.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        targs = {}
                    if cid and tname:
                        tool_inputs_for_history.append(
                            llm.ToolInput(id=cid, tool_name=tname, tool_args=targs)
                        )
                assistant_content = AssistantContent(
                    agent_id=self.entity_id,
                    content=text_content,
                    tool_calls=tool_inputs_for_history or None,
                )
                chat_log.content.append(assistant_content)

                for tool_call_data in tool_calls:
                    call_id = tool_call_data.get("id")
                    func_details = tool_call_data.get("function", {})
                    call_type = tool_call_data.get("type", "function")
                    tool_name = func_details.get("name")
                    tool_args_str = func_details.get("arguments", "{}")

                    if not call_id or call_type != "function" or not func_details:
                        _LOGGER.warning("Skipping malformed tool call: %s", tool_call_data)
                        continue
                    if not tool_name:
                        _LOGGER.warning("Tool call missing name: %s", tool_call_data)
                        continue

                    try:
                        tool_args = json.loads(tool_args_str)
                    except json.JSONDecodeError:
                        _LOGGER.error(
                            "Failed JSON parse for tool %s args: %s", tool_name, tool_args_str
                        )
                        continue

                    # Find matching tool: first check HA LLM API tools, then custom function configs
                    tool_result = None
                    matched_ha_tool = False
                    for tool in tools:
                        if tool.name == tool_name:
                            matched_ha_tool = True
                            try:
                                tool_input = llm.ToolInput(
                                    id=call_id,
                                    tool_name=tool_name,
                                    tool_args=tool_args,
                                )
                                tool_result = await tool.async_call(
                                    self.hass, tool_input, llm_context
                                )
                            except Exception as tool_err:
                                _LOGGER.warning("Tool %s failed: %s", tool_name, tool_err)
                                tool_result = {"error": str(tool_err)}
                            break

                    if not matched_ha_tool:
                        # Check custom function configs
                        for fc in function_configs:
                            if fc.get("name") == tool_name:
                                try:
                                    fn = get_function(fc["type"])
                                    tool_result = await fn.execute(
                                        self.hass, fc, tool_args, llm_context, exposed_entities
                                    )
                                except Exception as fn_err:
                                    _LOGGER.warning("Function %s failed: %s", tool_name, fn_err)
                                    tool_result = {"error": str(fn_err)}
                                break

                    if tool_result is None:
                        _LOGGER.warning("Tool %s not found in HA tools or custom functions", tool_name)
                        tool_result = {"error": f"Tool {tool_name} not found"}

                    tool_result_content = ToolResultContent(
                        agent_id=self.entity_id,
                        tool_call_id=call_id,
                        tool_name=tool_name,
                        tool_result=tool_result,
                    )
                    chat_log.content.append(tool_result_content)

                # Trim chat log to prevent unbounded growth after processing all tool calls
                _trim_chat_log(chat_log)
            else:
                _LOGGER.warning("Reached max tool iterations (%d)", max_tool_iterations)
                assistant_response_content = text_content or ""

            if assistant_response_content is None:
                _LOGGER.error("Assistant response content was None after loop.")
                assistant_response_content = "Sorry, I couldn't get a response."

        except RateLimitError as err:
            _LOGGER.warning("Rate limit hit during conversation: %s", err)
            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                "Rate limit exceeded. Please wait a moment and try again.",
            )
            return ConversationResult(
                conversation_id=chat_log.conversation_id,
                response=intent_response,
            )
        except (VeniceAIError, HomeAssistantError, TemplateError) as err:
            _LOGGER.error("Error during conversation processing: %s", err)
            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                f"Error: {err}",
            )
            return ConversationResult(
                conversation_id=chat_log.conversation_id,
                response=intent_response,
            )
        except Exception as err:
            _LOGGER.exception("Unexpected error during conversation processing")
            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                "Unexpected error occurred.",
            )
            return ConversationResult(
                conversation_id=chat_log.conversation_id,
                response=intent_response,
            )

        # Persist the final assistant turn so subsequent calls see the full history.
        chat_log.content.append(
            AssistantContent(agent_id=self.entity_id, content=assistant_response_content)
        )
        _trim_chat_log(chat_log)

        # Build response
        intent_response = intent.IntentResponse(language=user_input.language)
        intent_response.async_set_speech(assistant_response_content)

        # Signal HA to keep listening if the response ends with a question
        # and the user has enabled extended conversation in options.
        should_continue = (
            options.get(CONF_CONTINUE_CONVERSATION, RECOMMENDED_CONTINUE_CONVERSATION)
            and assistant_response_content.rstrip().endswith("?")
        )

        return ConversationResult(
            conversation_id=chat_log.conversation_id,
            response=intent_response,
            continue_conversation=should_continue,
        )

    async def async_added_to_hass(self) -> None:
        """Write state once added so entity_id is resolved before first use."""
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Venice AI conversation entity."""
    from . import VeniceAIRuntimeData

    runtime_data: VeniceAIRuntimeData = entry.runtime_data
    if not runtime_data or not runtime_data.client:
        _LOGGER.error(
            "Venice AI client not available in runtime_data for entry %s",
            entry.entry_id,
        )
        return

    entity = VeniceAIConversationEntity(entry)
    async_add_entities([entity])
