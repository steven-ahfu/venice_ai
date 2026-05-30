"""Tests for the file-tool path resolver.

Exercises ``_resolve_path`` directly. This is the *only* defense against the
LLM reading arbitrary files via the read_file / write_file / edit_file tools,
so test the rejection paths in particular.
"""
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, ".")

# conftest.py stubs all HA modules before this runs
from custom_components.venice_ai.functions.file import _resolve_path


def _hass(config_dir):
    return SimpleNamespace(config=SimpleNamespace(config_dir=str(config_dir)))


def test_relative_path_resolves_inside_workspace(tmp_path):
    resolved = _resolve_path(_hass(tmp_path), "notes.txt")
    assert resolved == (tmp_path / "venice_ai" / "notes.txt").resolve()


def test_relative_path_with_dotdot_inside_workspace_ok(tmp_path):
    # foo/../notes.txt resolves back into the workspace — allowed.
    resolved = _resolve_path(_hass(tmp_path), "foo/../notes.txt")
    assert resolved == (tmp_path / "venice_ai" / "notes.txt").resolve()


def test_relative_path_escaping_workspace_rejected(tmp_path):
    # Bug guard: previously '../venice_ai_attack/foo' resolved to a sibling
    # directory and passed a str.startswith() check because '/.../venice_ai'
    # is a prefix of '/.../venice_ai_attack'.
    with pytest.raises(ValueError, match="outside the allowed workspace"):
        _resolve_path(_hass(tmp_path), "../venice_ai_attack/foo")


def test_sibling_directory_with_shared_prefix_rejected(tmp_path):
    # Directly verifies the prefix-vs-component-boundary fix.
    with pytest.raises(ValueError, match="outside the allowed workspace"):
        _resolve_path(_hass(tmp_path), "../venice_ai_evil")


def test_absolute_path_inside_workspace_allowed(tmp_path):
    abs_path = str(tmp_path / "venice_ai" / "deep" / "file.txt")
    resolved = _resolve_path(_hass(tmp_path), abs_path)
    assert resolved == (tmp_path / "venice_ai" / "deep" / "file.txt").resolve()


def test_absolute_path_outside_workspace_rejected(tmp_path):
    with pytest.raises(ValueError, match="outside the allowed workspace"):
        _resolve_path(_hass(tmp_path), "/etc/passwd")


def test_allow_dir_grants_absolute_access(tmp_path):
    extra = tmp_path / "extra"
    extra.mkdir()
    target = extra / "log.txt"
    resolved = _resolve_path(_hass(tmp_path), str(target), allow_dirs=[str(extra)])
    assert resolved == target.resolve()


def test_allow_dir_does_not_override_workspace_for_bare_relative(tmp_path):
    # Bare relative paths resolve against the workspace first; allow_dirs are
    # additional roots that *absolute* paths may live inside, not extra search
    # roots for relative paths (otherwise the same name in two roots is
    # ambiguous). Document the actual semantics.
    extra = tmp_path / "extra"
    extra.mkdir()
    resolved = _resolve_path(_hass(tmp_path), "log.txt", allow_dirs=[str(extra)])
    assert resolved == (tmp_path / "venice_ai" / "log.txt").resolve()


def test_allow_dir_does_not_widen_to_unrelated_paths(tmp_path):
    extra = tmp_path / "extra"
    extra.mkdir()
    with pytest.raises(ValueError, match="outside the allowed workspace"):
        _resolve_path(_hass(tmp_path), "/etc/passwd", allow_dirs=[str(extra)])
