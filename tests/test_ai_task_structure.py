"""Tests for AI-task structured-output helpers in ai_task.py."""
import sys

sys.path.insert(0, ".")

# conftest.py stubs all HA modules before this runs
from custom_components.venice_ai.ai_task import _extract_json, _structure_to_json_schema


def test_extract_json_plain():
    assert _extract_json('{"a": 1}') == '{"a": 1}'


def test_extract_json_strips_bare_fence():
    assert _extract_json("```\n{\"a\": 1}\n```") == '{"a": 1}'


def test_extract_json_strips_language_fence():
    assert _extract_json("```json\n{\"a\": 1}\n```") == '{"a": 1}'


def test_extract_json_strips_surrounding_whitespace():
    assert _extract_json("  \n {\"a\": 1} \n ") == '{"a": 1}'


def test_structure_none_returns_none():
    assert _structure_to_json_schema(None) is None


def test_structure_conversion_best_effort():
    # Without voluptuous_openapi in the test env, conversion returns None
    # rather than raising — the caller falls back to a plain JSON instruction.
    import voluptuous as vol

    result = _structure_to_json_schema(vol.Schema({"name": str}))
    assert result is None or isinstance(result, dict)
