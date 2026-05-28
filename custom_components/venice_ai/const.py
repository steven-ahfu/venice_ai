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
RECOMMENDED_CHAT_MODEL = "llama-3.3-70b"  # Venice AI default model with function calling support
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

# Venice AI TTS options
CONF_TTS_MODEL = "tts_model"
RECOMMENDED_TTS_MODEL = "tts-kokoro"
CONF_TTS_VOICE = "tts_voice"
RECOMMENDED_TTS_VOICE = "bm_daniel"
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
