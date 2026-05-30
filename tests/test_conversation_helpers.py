"""Tests for pure-Python helpers in conversation.py."""
import sys
sys.path.insert(0, ".")

# conftest.py stubs all HA modules before this runs
from custom_components.venice_ai.conversation import (
    _build_venice_params,
    _strip_thinking,
    _trim_chat_log,
)


# ── _strip_thinking ───────────────────────────────────────────────────────────

def test_strip_thinking_xml_tags():
    assert _strip_thinking("<think>internal reasoning</think>Hello world") == "Hello world"

def test_strip_thinking_xml_case_insensitive():
    assert _strip_thinking("<THINK>reasoning</THINK>Answer") == "Answer"

def test_strip_thinking_multiple_blocks():
    assert _strip_thinking("<think>a</think>word<think>b</think>end") == "wordend"

def test_strip_thinking_unmatched_open_tag():
    assert _strip_thinking("before<think>dangling") == "before"

def test_strip_thinking_venice_style():
    assert _strip_thinking(" thinking some internal thoughts end of thinking real answer") == "real answer"

def test_strip_thinking_venice_style_with_leading_text():
    # Real prose before the matched marker pair must survive.
    assert (
        _strip_thinking("Hello.  thinking quietly end of thinking  Goodbye.")
        == "Hello.   Goodbye."
    )

def test_strip_thinking_venice_unmatched_opener_not_truncated():
    # Bug guard: previously `parts[-1]` discarded all text before any literal
    # "end of thinking" substring, even when no matched ` thinking` opener
    # preceded it. The prose must be returned unchanged.
    input_text = "Reflecting on the end of thinking about this puzzle."
    assert _strip_thinking(input_text) == input_text

def test_strip_thinking_no_tags_passthrough():
    assert _strip_thinking("plain response") == "plain response"

def test_strip_thinking_empty_string():
    assert _strip_thinking("") == ""

def test_strip_thinking_only_tags():
    assert _strip_thinking("<think>all internal</think>") == ""


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
    log = _FakeChatLog([_FakeMsg(i) for i in range(10)])
    _trim_chat_log(log)
    assert len(log.content) == 10

def test_trim_keeps_first_and_recent():
    from custom_components.venice_ai.const import MAX_CHAT_LOG_LENGTH
    msgs = [_FakeMsg(i) for i in range(MAX_CHAT_LOG_LENGTH + 20)]
    log = _FakeChatLog(msgs)
    _trim_chat_log(log)
    assert len(log.content) == MAX_CHAT_LOG_LENGTH
    assert log.content[0].label == 0  # first preserved (system prompt)
    assert log.content[-1].label == MAX_CHAT_LOG_LENGTH + 19  # last preserved

def test_trim_exactly_at_limit_unchanged():
    from custom_components.venice_ai.const import MAX_CHAT_LOG_LENGTH
    log = _FakeChatLog([_FakeMsg(i) for i in range(MAX_CHAT_LOG_LENGTH)])
    _trim_chat_log(log)
    assert len(log.content) == MAX_CHAT_LOG_LENGTH


# ── _build_venice_params ──────────────────────────────────────────────────────
# Guard against the "empty dict instead of None" wire-format regression.

def test_venice_params_both_off_returns_none():
    assert _build_venice_params(False, False) is None

def test_venice_params_web_search_only():
    assert _build_venice_params(False, True) == {"enable_web_search": "auto"}

def test_venice_params_disable_thinking_only():
    assert _build_venice_params(True, False) == {"disable_thinking": True}

def test_venice_params_both_on():
    assert _build_venice_params(True, True) == {
        "disable_thinking": True,
        "enable_web_search": "auto",
    }
