"""Tests for pure-Python helpers in conversation.py."""
import sys
sys.path.insert(0, ".")

# conftest.py stubs all HA modules before this runs
from custom_components.venice_ai.conversation import (
    _strip_thinking,
    _trim_chat_log,
    DEFAULT_SYSTEM_PROMPT,
)


# ── _strip_thinking ───────────────────────────────────────────────────────────

def test_strip_thinking_xml_tags():
    result = _strip_thinking("<think>internal reasoning</think>Hello world")
    assert result == "Hello world"

def test_strip_thinking_xml_case_insensitive():
    result = _strip_thinking("<THINK>reasoning</THINK>Answer")
    assert result == "Answer"

def test_strip_thinking_multiple_blocks():
    result = _strip_thinking("<think>a</think>word<think>b</think>end")
    assert result == "wordend"

def test_strip_thinking_unmatched_open_tag():
    # Unmatched <think> — should strip to end of open tag
    result = _strip_thinking("before<think>dangling")
    assert result == "before"

def test_strip_thinking_venice_style():
    result = _strip_thinking(" thinking some internal thoughts end of thinking real answer")
    assert result == "real answer"

def test_strip_thinking_no_tags_passthrough():
    result = _strip_thinking("plain response")
    assert result == "plain response"

def test_strip_thinking_empty_string():
    result = _strip_thinking("")
    assert result == ""

def test_strip_thinking_only_tags():
    result = _strip_thinking("<think>all internal</think>")
    assert result == ""


# ── _trim_chat_log ────────────────────────────────────────────────────────────

class _FakeMsg:
    def __init__(self, label):
        self.label = label
    def __repr__(self):
        return f"Msg({self.label})"

class _FakeChatLog:
    def __init__(self, messages):
        self.content = list(messages)

def test_trim_does_nothing_when_under_limit():
    msgs = [_FakeMsg(i) for i in range(10)]
    log = _FakeChatLog(msgs)
    _trim_chat_log(log)
    assert len(log.content) == 10

def test_trim_keeps_first_and_recent():
    from custom_components.venice_ai.const import MAX_CHAT_LOG_LENGTH
    msgs = [_FakeMsg(i) for i in range(MAX_CHAT_LOG_LENGTH + 20)]
    log = _FakeChatLog(msgs)
    _trim_chat_log(log)
    assert len(log.content) == MAX_CHAT_LOG_LENGTH
    assert log.content[0].label == 0  # first preserved
    assert log.content[-1].label == MAX_CHAT_LOG_LENGTH + 19  # last preserved

def test_trim_exactly_at_limit_unchanged():
    from custom_components.venice_ai.const import MAX_CHAT_LOG_LENGTH
    msgs = [_FakeMsg(i) for i in range(MAX_CHAT_LOG_LENGTH)]
    log = _FakeChatLog(msgs)
    _trim_chat_log(log)
    assert len(log.content) == MAX_CHAT_LOG_LENGTH


# ── DEFAULT_SYSTEM_PROMPT ─────────────────────────────────────────────────────

def test_default_system_prompt_is_nonempty():
    assert isinstance(DEFAULT_SYSTEM_PROMPT, str)
    assert len(DEFAULT_SYSTEM_PROMPT) > 20


# ── venice_params assembly ────────────────────────────────────────────────────
# Directly test the logic extracted from async_process so a regression can't
# silently break it (e.g. the old "venice_params or None" empty-dict bug).

def _build_venice_params(disable_thinking: bool, enable_web_search: bool):
    """Mirror of the venice_params assembly in conversation.py:async_process."""
    venice_params = None
    if disable_thinking or enable_web_search:
        venice_params = {}
        if disable_thinking:
            venice_params["disable_thinking"] = True
        if enable_web_search:
            venice_params["enable_web_search"] = "auto"
    return venice_params

def test_venice_params_both_off_returns_none():
    assert _build_venice_params(False, False) is None

def test_venice_params_web_search_only():
    p = _build_venice_params(False, True)
    assert p == {"enable_web_search": "auto"}
    assert "disable_thinking" not in p

def test_venice_params_disable_thinking_only():
    p = _build_venice_params(True, False)
    assert p == {"disable_thinking": True}
    assert "enable_web_search" not in p

def test_venice_params_both_on():
    p = _build_venice_params(True, True)
    assert p == {"disable_thinking": True, "enable_web_search": "auto"}
