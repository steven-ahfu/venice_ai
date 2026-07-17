"""Tests for the curated voice-chat model list and cost labels.

These exercise the real ``curate_chat_models`` / ``_chat_model_label``
exported from config_flow so a regression in the model dropdown is caught.
"""
import sys
sys.path.insert(0, ".")

# conftest.py stubs all HA modules before this runs
from custom_components.venice_ai.config_flow import _chat_model_label, curate_chat_models
from custom_components.venice_ai.const import RECOMMENDED_CHAT_MODEL, VOICE_CHAT_MODELS


def _opt(model_id: str) -> dict:
    return {"label": model_id, "value": model_id}


def test_recommended_model_is_curated():
    assert RECOMMENDED_CHAT_MODEL in VOICE_CHAT_MODELS


def test_curation_filters_and_preserves_curated_order():
    fetched = [_opt("some-huge-model"), _opt("qwen3-5-9b"),
               _opt("mistral-small-3-2-24b-instruct"), _opt("another-model")]
    result = curate_chat_models(fetched)
    assert [o["value"] for o in result] == [
        "mistral-small-3-2-24b-instruct", "qwen3-5-9b",
    ]


def test_curation_keeps_current_non_curated_selection():
    fetched = [_opt("legacy-model"), _opt("llama-3.2-3b")]
    result = curate_chat_models(fetched, current_model="legacy-model")
    assert [o["value"] for o in result] == ["llama-3.2-3b", "legacy-model"]


def test_curation_falls_back_to_full_list_when_no_overlap():
    fetched = [_opt("brand-new-model-a"), _opt("brand-new-model-b")]
    assert curate_chat_models(fetched, current_model="brand-new-model-a") == fetched


def test_label_prefers_live_pricing_and_appends_tier():
    label = _chat_model_label({
        "id": "qwen3-5-9b",
        "model_spec": {
            "name": "Qwen 3.5 9B",
            "pricing": {"input": {"usd": 1.0}, "output": {"usd": 3.2}},
        },
    })
    # 0.60 * 1.00 + 0.40 * 3.20 = 1.88, and curated tier is appended
    assert label == "Qwen 3.5 9B · ~$1.88/M · recommended"


def test_label_falls_back_to_snapshot_pricing_for_curated_model():
    label = _chat_model_label({"id": "zai-org-glm-4.7"})
    # 0.60 * 0.55 + 0.40 * 2.65 = 1.39
    assert label == "GLM 4.7 · ~$1.39/M · step-up"


def test_label_unknown_model_without_pricing_is_name_only():
    assert _chat_model_label({"id": "mystery-model"}) == "mystery-model"
