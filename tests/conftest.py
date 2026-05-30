"""Shared test fixtures: stub all HA modules before any package import."""
import sys
import types
import unittest.mock


def _stub(name: str, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# Ensure parent packages exist first
for pkg in ["homeassistant", "homeassistant.components", "homeassistant.helpers", "homeassistant.util"]:
    if pkg not in sys.modules:
        sys.modules[pkg] = types.ModuleType(pkg)

# homeassistant.const — needs CONF_API_KEY and Platform
class _Platform:
    CONVERSATION = "conversation"
    TTS = "tts"
    STT = "stt"
    AI_TASK = "ai_task"

_const = _stub(
    "homeassistant.const",
    CONF_API_KEY="api_key",
    CONF_LLM_HASS_API="llm_hass_api",
    Platform=_Platform,
)

# homeassistant.core
class _HA:
    pass

_stub(
    "homeassistant.core",
    HomeAssistant=_HA,
    ServiceCall=object,
    ServiceResponse=object,
    SupportsResponse=unittest.mock.MagicMock(),
    callback=lambda f: f,
)

# homeassistant.config_entries
class _ConfigEntry:
    def __init__(self, **kw):
        self.__dict__.update(kw)

class _ConfigFlow:
    def __init_subclass__(cls, **kwargs):
        # HA's real ConfigFlow accepts `domain=...` via PEP 487; absorb it.
        super().__init_subclass__()
class _OptionsFlow: pass

_stub(
    "homeassistant.config_entries",
    ConfigEntry=_ConfigEntry,
    ConfigFlow=_ConfigFlow,
    OptionsFlow=_OptionsFlow,
    ConfigFlowResult=dict,
)

# homeassistant.exceptions
class _HAError(Exception): pass
class _TemplateError(Exception): pass
class _ConfigEntryAuthFailed(Exception): pass
class _ConfigEntryNotReady(Exception): pass
class _ServiceValidationError(Exception): pass

_stub(
    "homeassistant.exceptions",
    HomeAssistantError=_HAError,
    TemplateError=_TemplateError,
    ConfigEntryAuthFailed=_ConfigEntryAuthFailed,
    ConfigEntryNotReady=_ConfigEntryNotReady,
    ServiceValidationError=_ServiceValidationError,
)

# homeassistant.helpers.config_validation
_stub("homeassistant.helpers.config_validation", string=str, config_entry_only_config_schema=lambda d: None)

# homeassistant.helpers.selector
_sel = _stub("homeassistant.helpers.selector")
for name in [
    "BooleanSelector", "NumberSelector", "NumberSelectorConfig",
    "SelectOptionDict", "SelectSelector", "SelectSelectorConfig",
    "SelectSelectorMode", "TemplateSelector", "ConfigEntrySelector", "Selector",
]:
    setattr(_sel, name, unittest.mock.MagicMock())

# homeassistant.helpers.llm
_llm = _stub("homeassistant.helpers.llm")
for name in ["Tool", "LLMContext", "ToolInput", "async_get_api", "async_get_apis"]:
    setattr(_llm, name, unittest.mock.MagicMock())

# homeassistant.helpers.device_registry
_dr = _stub("homeassistant.helpers.device_registry")
for name in ["DeviceInfo", "DeviceEntryType"]:
    setattr(_dr, name, unittest.mock.MagicMock())

# homeassistant.helpers.entity_platform
_stub("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)

# homeassistant.helpers.template
_stub("homeassistant.helpers.template", Template=unittest.mock.MagicMock())

# homeassistant.helpers.httpx_client
_stub("homeassistant.helpers.httpx_client", get_async_client=unittest.mock.MagicMock())

# homeassistant.helpers.issue_registry
_ir = _stub("homeassistant.helpers.issue_registry", IssueSeverity=unittest.mock.MagicMock())
_ir.async_create_issue = unittest.mock.MagicMock()
_ir.async_delete_issue = unittest.mock.MagicMock()
_ir.async_get = unittest.mock.MagicMock()

# homeassistant.helpers.intent
_intent = _stub("homeassistant.helpers.intent")
for name in ["IntentResponse", "IntentResponseErrorCode"]:
    setattr(_intent, name, unittest.mock.MagicMock())

# homeassistant.helpers.entity_registry
_er = _stub("homeassistant.helpers.entity_registry")
for name in ["RegistryEntry", "EntityRegistry", "async_get", "async_entries_for_config_entry"]:
    setattr(_er, name, unittest.mock.MagicMock())

# homeassistant.helpers (parent — needs sub-module attrs for `from homeassistant.helpers import x`)
_stub("homeassistant.helpers",
      config_validation=sys.modules["homeassistant.helpers.config_validation"],
      llm=_llm,
      selector=_sel,
      issue_registry=_ir,
      intent=_intent,
      device_registry=_dr,
      entity_registry=_er,
)

# homeassistant.helpers.typing
_stub("homeassistant.helpers.typing", ConfigType=dict)

# homeassistant.helpers.update_coordinator
class _DataUpdateCoordinator:
    def __init__(self, hass, logger, name, update_interval):
        self.hass = hass
        self.last_exception = None
        self.last_update_success = True
        self.data = None
        self.update_interval = update_interval
    async def async_config_entry_first_refresh(self): pass
    def async_add_listener(self, cb): return lambda: None
    def __class_getitem__(cls, _): return cls

_stub(
    "homeassistant.helpers.update_coordinator",
    DataUpdateCoordinator=_DataUpdateCoordinator,
    UpdateFailed=Exception,
)

# homeassistant.components.conversation
_conv = _stub("homeassistant.components.conversation")
for name in [
    "HOME_ASSISTANT_AGENT", "ConversationEntity", "ConversationEntityFeature",
    "ConversationInput", "ConversationResult", "ChatLog", "UserContent",
    "AssistantContent", "SystemContent", "ToolResultContent", "ConverseError",
]:
    setattr(_conv, name, unittest.mock.MagicMock())

# homeassistant.components.stt
_stt = _stub("homeassistant.components.stt")
for name in [
    "SpeechResult", "SpeechResultState", "SpeechToTextEntity",
    "AudioFormats", "AudioCodecs", "AudioBitRates", "AudioSampleRates",
    "AudioChannels", "SpeechMetadata",
]:
    setattr(_stt, name, unittest.mock.MagicMock())

# homeassistant.components.tts
_tts = _stub("homeassistant.components.tts")
for name in [
    "ATTR_AUDIO_OUTPUT", "ATTR_VOICE", "TTSAudioRequest", "TTSAudioResponse",
    "TextToSpeechEntity", "TtsAudioType", "Voice",
]:
    setattr(_tts, name, unittest.mock.MagicMock())

# homeassistant.components.ai_task
_ai_task = _stub("homeassistant.components.ai_task")
for name in ["AITaskEntity", "AITaskEntityFeature", "GenDataTask", "GenDataTaskResult"]:
    setattr(_ai_task, name, unittest.mock.MagicMock())

# homeassistant.components.diagnostics
_stub("homeassistant.components.diagnostics", async_redact_data=lambda d, _: d)

# homeassistant.util.ulid
_stub("homeassistant.util.ulid", ulid_now=lambda: "test-ulid-000")

# homeassistant.util (parent)
_util = sys.modules["homeassistant.util"]
setattr(_util, "ulid", sys.modules["homeassistant.util.ulid"])

# homeassistant.components (parent needs sub-attrs)
_comps = sys.modules["homeassistant.components"]
for attr in ["conversation", "stt", "tts", "ai_task", "diagnostics"]:
    setattr(_comps, attr, sys.modules[f"homeassistant.components.{attr}"])

# homeassistant.__version__
_ha_root = sys.modules["homeassistant"]
setattr(_ha_root, "__version__", "2024.1.0")
_stub("homeassistant.const", **{
    **{k: getattr(sys.modules["homeassistant.const"], k)
       for k in dir(sys.modules["homeassistant.const"])},
    "__version__": "2024.1.0",
})
