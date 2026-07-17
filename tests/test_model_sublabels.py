"""Tests for TTS/STT model sublabel rendering (name + cost).

Labels must prefer live API data (model_spec.name / pricing) so newly-added
models are named and priced without a code change, and fall back to the
shipped static maps otherwise.
"""
import sys

sys.path.insert(0, ".")

# conftest.py stubs all HA modules before this runs
from custom_components.venice_ai.const import (
    align_cost_labels,
    friendly_voice_label,
    tts_model_sublabel,
    stt_model_sublabel,
    MODEL_LABELS,
    MODEL_PRICING_USD_PER_MTOK,
    STT_MODEL_LABELS,
)


def test_tts_label_from_live_spec():
    label = tts_model_sublabel({
        "id": "tts-brand-new",
        "model_spec": {"name": "Brand New TTS", "pricing": {"input": {"usd": 10.0}}},
    })
    assert label == "Brand New TTS     $0.55/hr"


def test_tts_label_from_static_fallback_bare_id():
    # tts-gradium-v1 ships in the static maps
    assert "tts-gradium-v1" in MODEL_LABELS
    assert MODEL_PRICING_USD_PER_MTOK["tts-gradium-v1"] == 47.5
    assert tts_model_sublabel("tts-gradium-v1") == "Gradium TTS     $2.61/hr"


def test_tts_label_live_spec_overrides_static():
    # A live name/price wins over the shipped snapshot.
    label = tts_model_sublabel({
        "id": "tts-kokoro",
        "model_spec": {"name": "Kokoro v2", "pricing": {"input": {"usd": 4.0}}},
    })
    assert label == "Kokoro v2     $0.22/hr"


def test_tts_label_unknown_model_is_id_only():
    assert tts_model_sublabel({"id": "tts-mystery", "model_spec": {}}) == "tts-mystery"


def test_stt_label_from_live_spec_with_pricing():
    # STT pricing arrives as model_spec.pricing.per_audio_second.usd and is
    # shown per hour of audio.
    label = stt_model_sublabel({
        "id": "openai/whisper-large-v3",
        "model_spec": {
            "name": "Whisper Large V3",
            "pricing": {"per_audio_second": {"usd": 0.0001}},
        },
    })
    assert label == "Whisper Large V3     $0.36/hr"


def test_stt_label_name_only_when_spec_has_no_pricing():
    label = stt_model_sublabel({
        "id": "some/unpriced-model",
        "model_spec": {"name": "Unpriced STT"},
    })
    assert label == "Unpriced STT"


def test_stt_label_from_static_fallback():
    assert "nvidia/parakeet-tdt-0.6b-v3" in STT_MODEL_LABELS
    assert (
        stt_model_sublabel("nvidia/parakeet-tdt-0.6b-v3")
        == "Parakeet ASR     $0.36/hr"
    )


def test_stt_label_unknown_model_is_id_only():
    assert stt_model_sublabel({"id": "stt-mystery", "model_spec": {}}) == "stt-mystery"


def test_stt_label_live_pricing_overrides_static():
    label = stt_model_sublabel({
        "id": "elevenlabs/scribe-v2",
        "model_spec": {
            "name": "ElevenLabs Scribe V2",
            "pricing": {"per_audio_second": {"usd": 0.000167}},
        },
    })
    assert label == "ElevenLabs Scribe V2     $0.60/hr"


def test_kokoro_voice_label_uses_bullet_and_prefix():
    assert friendly_voice_label("tts-kokoro", "af_sky") == "Sky \u2022 AF"
    assert friendly_voice_label("tts-kokoro", "zm_yunjian") == "Yunjian \u2022 ZM"


def test_kokoro_voice_label_disambiguates_shared_names():
    labels = {
        friendly_voice_label("tts-kokoro", v)
        for v in ("am_santa", "em_santa", "pm_santa")
    }
    assert labels == {"Santa \u2022 AM", "Santa \u2022 EM", "Santa \u2022 PM"}


def test_kokoro_voice_label_unknown_prefix_falls_back():
    # "x" is not a known Kokoro language code — no tag appended.
    assert friendly_voice_label("tts-kokoro", "xq_test") == "Test"


def test_non_kokoro_voice_ids_unchanged():
    assert friendly_voice_label("tts-orpheus", "tara") == "tara"


def test_align_cost_labels_common_right_edge():
    labels = align_cost_labels([
        "Kokoro Text to Speech     $0.19/hr",
        "xAI TTS v1     $1.03/hr",
    ])
    # Costs end at a common column: equal total character width per row.
    assert len(labels[0]) == len(labels[1])
    assert labels[0].endswith("$0.19/hr") and labels[1].endswith("$1.03/hr")
    assert "\u2007" in labels[1] and "\u00a0" not in labels[1]


def test_align_cost_labels_passes_through_costless_labels():
    labels = align_cost_labels(["Priced     $1.00/hr", "No Price Model"])
    assert labels[1] == "No Price Model"


def test_align_cost_labels_counts_emoji_as_double_width():
    starred, plain = align_cost_labels([
        "Model A ⭐     $1.00/M",
        "Model AAA     $1.00/M",
    ])
    # "Model A ⭐" renders about as wide as "Model AAA" (emoji ≈ 2 cells),
    # so both rows should get the same padded width in character cells.
    assert len(starred) + 1 == len(plain)
