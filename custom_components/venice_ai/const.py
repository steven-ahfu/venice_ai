"""Constants for the Venice AI Conversation integration."""

from datetime import timedelta

DOMAIN = "venice_ai"

# Coordinator refresh interval — must be a timedelta for DataUpdateCoordinator
UPDATE_INTERVAL = timedelta(hours=1)

# Centralized voluptuous_openapi detection
try:
    from voluptuous_openapi import convert as voluptuous_convert  # noqa: F401
    HAS_VOLUPTUOUS_OPENAPI = True
except ImportError:
    HAS_VOLUPTUOUS_OPENAPI = False

CONF_PROMPT = "prompt"
CONF_CHAT_MODEL = "chat_model"
RECOMMENDED_CHAT_MODEL = "mistral-small-3-2-24b-instruct"  # top curated pick: non-reasoning, reliable tool calling

# Curated chat models for the voice-assistant use case: function calling
# required, no forced long reasoning (non-reasoning or effort-controllable),
# cheap/fast architectures. Selected from the live Venice text-model list on
# 2026-07-16 (see voicechat_assistant_models.json export). Dict order is the
# dropdown order: recommended → value → step-up → ultra-light. Prices are USD
# per 1M tokens and are only a fallback — the config flow prefers live
# pricing from GET /models when available.
VOICE_CHAT_MODELS: dict[str, dict] = {
    # Recommended: start here
    "mistral-small-3-2-24b-instruct": {
        "name": "Mistral Small 3.2 24B Instruct", "tier": "recommended",
        "input_usd": 0.09375, "output_usd": 0.25,
    },
    "openai-gpt-oss-120b": {
        "name": "OpenAI GPT OSS 120B", "tier": "recommended",
        "input_usd": 0.07, "output_usd": 0.3,
    },
    "qwen3-5-9b": {
        "name": "Qwen 3.5 9B", "tier": "recommended",
        "input_usd": 0.1, "output_usd": 0.15,
    },
    "google-gemma-4-31b-it": {
        "name": "Google Gemma 4 31B Instruct", "tier": "recommended",
        "input_usd": 0.12, "output_usd": 0.36,
    },
    # Value
    "nvidia-nemotron-3-nano-30b-a3b": {
        "name": "NVIDIA Nemotron 3 Nano 30B", "tier": "value",
        "input_usd": 0.075, "output_usd": 0.3,
    },
    "google-gemma-3-27b-it": {
        "name": "Google Gemma 3 27B Instruct", "tier": "value",
        "input_usd": 0.12, "output_usd": 0.2,
    },
    "zai-org-glm-4.7-flash": {
        "name": "GLM 4.7 Flash", "tier": "value",
        "input_usd": 0.125, "output_usd": 0.5,
    },
    # Reasoning model with no effort knob — verify thinking can be disabled
    # before trusting its latency for voice.
    "deepseek-v4-flash": {
        "name": "DeepSeek V4 Flash", "tier": "value",
        "input_usd": 0.138, "output_usd": 0.275,
    },
    "openai-gpt-4o-mini-2024-07-18": {
        "name": "GPT-4o Mini", "tier": "value",
        "input_usd": 0.1875, "output_usd": 0.75,
    },
    "mistral-small-2603": {
        "name": "Mistral Small 4", "tier": "value",
        "input_usd": 0.1875, "output_usd": 0.75,
    },
    # Step-up: if the cheap ones fumble tool calls
    "zai-org-glm-4.7": {
        "name": "GLM 4.7", "tier": "step-up",
        "input_usd": 0.55, "output_usd": 2.65,
    },
    "gemini-3-flash-preview": {
        "name": "Gemini 3 Flash Preview", "tier": "step-up",
        "input_usd": 0.7, "output_usd": 3.75,
    },
    # Ultra-light: near-instant canned commands only
    "llama-3.2-3b": {
        "name": "Llama 3.2 3B", "tier": "ultra-light",
        "input_usd": 0.15, "output_usd": 0.6,
    },
}
CONF_MAX_TOKENS = "max_tokens"
RECOMMENDED_MAX_TOKENS = 2048
CONF_TOP_P = "top_p"
RECOMMENDED_TOP_P = 0.9
CONF_TEMPERATURE = "temperature"
RECOMMENDED_TEMPERATURE = 0.7

# Venice AI reasoning model options
CONF_STRIP_THINKING_RESPONSE = "strip_thinking_response"
CONF_DISABLE_THINKING = "disable_thinking"
RECOMMENDED_DISABLE_THINKING = False

# Venice AI web search option. Only effective on models whose capabilities
# advertise supportsWebSearch (marked with 🔍 in the model picker).
CONF_ENABLE_WEB_SEARCH = "enable_web_search"
RECOMMENDED_ENABLE_WEB_SEARCH = False

# Venice AI TTS options
CONF_TTS_MODEL = "tts_model"
RECOMMENDED_TTS_MODEL = "tts-kokoro"
CONF_TTS_VOICE = "tts_voice"
RECOMMENDED_TTS_VOICE = "af_sky"
CONF_TTS_RESPONSE_FORMAT = "tts_response_format"
RECOMMENDED_TTS_RESPONSE_FORMAT = "mp3"
CONF_TTS_SPEED = "tts_speed"
RECOMMENDED_TTS_SPEED = 1.0

# Static fallback voice lists per TTS model (sourced from GET /models?type=tts).
# The config flow fetches these live; this map is used when the API is unreachable.
MODEL_VOICES: dict[str, list[str]] = {
    "tts-kokoro": [
        "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jadzia", "af_jessica",
        "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
        "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael",
        "am_onyx", "am_puck", "am_santa", "bf_alice", "bf_emma", "bf_lily",
        "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
        "ef_dora", "em_alex", "em_santa", "ff_siwis",
        "hf_alpha", "hf_beta", "hm_omega", "hm_psi",
        "if_sara", "im_nicola",
        "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo",
        "pf_dora", "pm_alex", "pm_santa",
        "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
        "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
    ],
    "tts-qwen3-0-6b": ["Aiden", "Dylan", "Eric", "Ono_Anna", "Ryan", "Serena", "Sohee", "Uncle_Fu", "Vivian"],
    "tts-qwen3-1-7b": ["Aiden", "Dylan", "Eric", "Ono_Anna", "Ryan", "Serena", "Sohee", "Uncle_Fu", "Vivian"],
    "tts-xai-v1": ["ara", "eve", "leo", "rex", "sal"],
    "tts-inworld-1-5-max": [
        "Alex", "Ashley", "Craig", "Edward", "Elizabeth",
        "Hades", "Luna", "Mark", "Olivia", "Pixie",
        "Priya", "Ronald", "Sarah", "Theodore",
    ],
    "tts-chatterbox-hd": ["Aurora", "Blade", "Britney", "Carl", "Cliff", "Richard", "Rico", "Siobhan", "Vicky"],
    "tts-orpheus": ["dan", "jess", "leah", "leo", "mia", "tara", "zac", "zoe"],
    "tts-elevenlabs-turbo-v2-5": [
        "Alice", "Aria", "Bill", "Brian", "Callum", "Charlie", "Charlotte",
        "Chris", "Daniel", "Eric", "George", "Jessica", "Laura", "Liam",
        "Lily", "Matilda", "Rachel", "River", "Roger", "Sarah", "Will",
    ],
    "tts-minimax-speech-02-hd": [
        "CalmWoman", "CasualGuy", "DeepVoiceMan", "DeterminedMan", "ElegantMan",
        "ExuberantGirl", "FriendlyPerson", "ImposingManner", "InspirationalGirl",
        "LivelyGirl", "LovelyGirl", "PatientMan", "SweetGirl", "WiseWoman", "YoungKnight",
    ],
    "tts-gemini-3-1-flash": [
        "Achernar", "Achird", "Algenib", "Algieba", "Alnilam", "Aoede", "Autonoe",
        "Callirrhoe", "Charon", "Despina", "Enceladus", "Erinome", "Fenrir", "Gacrux",
        "Iapetus", "Kore", "Laomedeia", "Leda", "Orus", "Puck", "Pulcherrima",
        "Rasalgethi", "Sadachbia", "Sadaltager", "Schedar", "Sulafat", "Umbriel",
        "Vindemiatrix", "Zephyr", "Zubenelgenubi",
    ],
}

# Fallback for unknown models — use Kokoro voices as a safe default
VENICE_TTS_VOICES = MODEL_VOICES["tts-kokoro"]

# Friendly display names for TTS models (sourced from GET /models?type=tts → model_spec.name)
MODEL_LABELS: dict[str, str] = {
    "tts-kokoro": "Kokoro Text to Speech",
    "tts-qwen3-0-6b": "Qwen 3 TTS 0.6B",
    "tts-qwen3-1-7b": "Qwen 3 TTS 1.7B",
    "tts-xai-v1": "xAI TTS v1",
    "tts-inworld-1-5-max": "Inworld TTS-1.5 Max",
    "tts-chatterbox-hd": "Chatterbox HD (Resemble AI)",
    "tts-orpheus": "Orpheus TTS",
    "tts-elevenlabs-turbo-v2-5": "ElevenLabs Turbo v2.5",
    "tts-minimax-speech-02-hd": "MiniMax Speech-02 HD",
    "tts-gemini-3-1-flash": "Gemini 3.1 Flash TTS",
}

# USD price per 1M input characters (sourced from GET /models?type=tts → model_spec.pricing.input.usd)
MODEL_PRICING_USD_PER_MTOK: dict[str, float] = {
    "tts-kokoro": 3.5,
    "tts-qwen3-0-6b": 87.5,
    "tts-qwen3-1-7b": 112.5,
    "tts-xai-v1": 18.75,
    "tts-inworld-1-5-max": 12.5,
    "tts-chatterbox-hd": 50.0,
    "tts-orpheus": 62.5,
    "tts-elevenlabs-turbo-v2-5": 62.5,
    "tts-minimax-speech-02-hd": 125.0,
    "tts-gemini-3-1-flash": 187.5,
}


# Kokoro voice-id prefix decoding: ``<lang><gender>_<name>`` (e.g. ``af_sky``).
# The first letter is the language, the second is the gender.
_KOKORO_LANGUAGES: dict[str, str] = {
    "a": "American",
    "b": "British",
    "e": "Spanish",
    "f": "French",
    "h": "Hindi",
    "i": "Italian",
    "j": "Japanese",
    "p": "Portuguese",
    "z": "Mandarin",
}
_KOKORO_GENDERS: dict[str, str] = {"f": "Female", "m": "Male"}


def friendly_voice_label(model_id: str, voice_id: str) -> str:
    """Return a human-friendly label for a Venice TTS voice id.

    Kokoro voices use a ``<lang><gender>_<name>`` pattern (e.g. ``af_sky`` =
    American Female "Sky"). The capitalised name alone is not unique — several
    voices share a name across languages/genders (e.g. ``am_santa``,
    ``em_santa``, ``pm_santa`` all become "Santa"), which makes them
    impossible to tell apart in the voice picker. Append the language/gender
    so every entry is distinct. Other models already ship user-friendly
    names — return them unchanged.
    """
    if model_id == "tts-kokoro":
        prefix, _, name = voice_id.partition("_")
        if name and len(prefix) == 2:
            display = name[:1].upper() + name[1:]
            language = _KOKORO_LANGUAGES.get(prefix[0])
            gender = _KOKORO_GENDERS.get(prefix[1])
            if language and gender:
                return f"{display} ({language} {gender})"
            return display
    return voice_id


def tts_model_sublabel(model_id: str) -> str:
    """Return a display string like ``"Kokoro Text to Speech ($3.50 / 1M chars)"``."""
    name = MODEL_LABELS.get(model_id, model_id)
    price = MODEL_PRICING_USD_PER_MTOK.get(model_id)
    if price is None:
        return name
    return f"{name} (${price:.2f} / 1M chars)"

# Automatically keep conversation open after a question response
CONF_CONTINUE_CONVERSATION = "continue_conversation"
RECOMMENDED_CONTINUE_CONVERSATION = False

# Venice AI web search toggle
CONF_ENABLE_WEB_SEARCH = "enable_web_search"
RECOMMENDED_ENABLE_WEB_SEARCH = False

# Venice AI STT options
CONF_STT_ENABLED = "stt_enabled"
RECOMMENDED_STT_ENABLED = True
CONF_STT_MODEL = "stt_model"
RECOMMENDED_STT_MODEL = "nvidia/parakeet-tdt-0.6b-v3"
CONF_STT_RESPONSE_FORMAT = "stt_response_format"
RECOMMENDED_STT_RESPONSE_FORMAT = "json"
CONF_STT_TIMESTAMPS = "stt_timestamps"
RECOMMENDED_STT_TIMESTAMPS = False

# Venice AI TTS toggle
CONF_TTS_ENABLED = "tts_enabled"
RECOMMENDED_TTS_ENABLED = True

# Conversation tool iteration limit
CONF_MAX_TOOL_ITERATIONS = "max_tool_iterations"
RECOMMENDED_MAX_TOOL_ITERATIONS = 5
MAX_CHAT_LOG_LENGTH = 50

# Maximum number of concurrent conversations held in-memory (LRU eviction)
MAX_CHAT_HISTORY_SIZE = 20

# Maximum audio buffer size for STT to prevent memory spikes (10 MB)
MAX_STT_BUFFER_SIZE = 10 * 1024 * 1024

CONF_FUNCTION_TOOLS = "function_tools"
CONF_SKILLS = "skills"

CONF_CONTEXT_THRESHOLD = "context_threshold"
RECOMMENDED_CONTEXT_THRESHOLD = 40000

# Venice AI doesn't have an unsupported-models list currently
UNSUPPORTED_MODELS: list[str] = []
