"""Tests for TTS/STT model sublabel rendering (name + cost).

Labels must prefer live API data (model_spec.name / pricing) so newly-added
models are named and priced without a code change, and fall back to the
shipped static maps otherwise.
"""
import sys

sys.path.insert(0, ".")

# conftest.py stubs all HA modules before this runs
from custom_components.venice_ai.const import (
    tts_model_sublabel,
    stt_model_sublabel,
    MODEL_LABELS,
    MODEL_PRICING_USD_PER_MTOK,
    STT_MODEL_LABELS,
)


def test_tts_label_from_live_spec():
    label = tts_model_sublabel({
        "id": "tts-brand-new",
        "model_spec": {"name": "Brand New TTS", "pricing": {"input": {"usd": 9.0}}},
    })
    assert label == "Brand New TTS ($9.00 / 1M chars)"


def test_tts_label_from_static_fallback_bare_id():
    # tts-gradium-v1 ships in the static maps
    assert "tts-gradium-v1" in MODEL_LABELS
    assert MODEL_PRICING_USD_PER_MTOK["tts-gradium-v1"] == 47.5
    assert tts_model_sublabel("tts-gradium-v1") == "Gradium TTS ($47.50 / 1M chars)"


def test_tts_label_live_spec_overrides_static():
    # A live name/price wins over the shipped snapshot.
    label = tts_model_sublabel({
        "id": "tts-kokoro",
        "model_spec": {"name": "Kokoro v2", "pricing": {"input": {"usd": 4.0}}},
    })
    assert label == "Kokoro v2 ($4.00 / 1M chars)"


def test_tts_label_unknown_model_is_id_only():
    assert tts_model_sublabel({"id": "tts-mystery", "model_spec": {}}) == "tts-mystery"


def test_stt_label_from_live_spec_name_only():
    # Venice does not expose STT pricing, so the label is name-only.
    label = stt_model_sublabel({
        "id": "openai/whisper-large-v3",
        "model_spec": {"name": "Whisper Large V3"},
    })
    assert label == "Whisper Large V3"


def test_stt_label_from_static_fallback():
    assert "nvidia/parakeet-tdt-0.6b-v3" in STT_MODEL_LABELS
    assert stt_model_sublabel("nvidia/parakeet-tdt-0.6b-v3") == "Parakeet ASR"


def test_stt_label_unknown_model_is_id_only():
    assert stt_model_sublabel({"id": "stt-mystery", "model_spec": {}}) == "stt-mystery"


def test_stt_label_with_live_pricing_shows_cost():
    # If Venice ever adds STT pricing, the label should surface it.
    label = stt_model_sublabel({
        "id": "stt-paid",
        "model_spec": {"name": "Paid STT", "pricing": {"input": {"usd": 5.0}}},
    })
    assert label == "Paid STT ($5.00 / 1M chars)"
