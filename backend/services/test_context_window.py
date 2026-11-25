
import pytest

from backend.services.context_window import (
    ContextWindowExceededError,
    count_tokens,
    trim_history_to_budget,
    truncate_prompt_text,
)


def test_count_tokens_fallback():
    assert count_tokens("") == 0
    assert count_tokens("abcd") == 1
    assert count_tokens("abcdefgh") == 2


def test_count_tokens_uses_tokenizer():
    class FakeTokenizer:
        def encode(self, text, add_special_tokens=False):
            return text.split()

    tokenizer = FakeTokenizer()

    assert count_tokens("one two three", tokenizer) == 3
    assert count_tokens("", tokenizer) == 0


def test_truncate_prompt_text_respects_budget():
    text = "a" * 100

    out, truncated = truncate_prompt_text(text, max_tokens=10)
    assert truncated is True
    assert len(out) == 40

    out_ok, truncated_ok = truncate_prompt_text("hello", max_tokens=10)
    assert truncated_ok is False
    assert out_ok == "hello"


def test_truncate_prompt_text_uses_tokenizer():
    class FakeTokenizer:
        def encode(self, text, add_special_tokens=False):
            return text.split()

        def decode(self, token_ids, skip_special_tokens=True):
            return " ".join(token_ids)

    tokenizer = FakeTokenizer()

    output, truncated = truncate_prompt_text(
        "one two three four",
        max_tokens=2,
        tokenizer=tokenizer,
    )

    assert output == "one two"
    assert truncated is True


def test_trim_history_keeps_system_and_latest_user():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "old q1 " * 20},
        {"role": "assistant", "content": "old a1 " * 20},
        {"role": "user", "content": "recent q2"},
        {"role": "assistant", "content": "recent a2"},
        {"role": "user", "content": "current q3"},
    ]

    trimmed = trim_history_to_budget(messages, max_tokens=20)

    assert trimmed[0]["role"] == "system"
    assert trimmed[-1]["content"] == "current q3"
    assert all("old q1" not in message["content"] for message in trimmed)


def test_trim_history_preserves_complete_current_turn():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "current question"},
        {"role": "assistant", "content": "assistant tool call"},
        {"role": "tool", "content": "tool result"},
        {"role": "assistant", "content": "final response"},
    ]

    trimmed = trim_history_to_budget(messages, max_tokens=100)

    assert trimmed == messages


def test_trim_history_groups_multiple_assistant_and_tool_messages():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "previous question"},
        {"role": "assistant", "content": "thinking"},
        {"role": "assistant", "content": "tool call"},
        {"role": "tool", "content": "tool result"},
        {"role": "assistant", "content": "previous answer"},
        {"role": "user", "content": "current question"},
    ]

    trimmed = trim_history_to_budget(
        messages,
        max_tokens=100,
        max_history_turns=1,
    )

    assert trimmed == messages


def test_trim_history_respects_max_history_turns():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "assistant", "content": "a2 continued"},
        {"role": "tool", "content": "tool2"},
        {"role": "user", "content": "u3"},
    ]

    trimmed = trim_history_to_budget(
        messages,
        max_tokens=1000,
        max_history_turns=1,
    )

    assert [message["content"] for message in trimmed] == [
        "sys",
        "u2",
        "a2",
        "a2 continued",
        "tool2",
        "u3",
    ]


def test_trim_history_zero_history_turns_keeps_current_turn():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "current question"},
    ]

    trimmed = trim_history_to_budget(
        messages,
        max_tokens=1000,
        max_history_turns=0,
    )

    assert [message["content"] for message in trimmed] == [
        "sys",
        "current question",
    ]


def test_trim_history_raises_when_mandatory_messages_exceed_budget():
    messages = [
        {"role": "system", "content": "system instructions"},
        {"role": "user", "content": "mandatory question"},
    ]

    with pytest.raises(ContextWindowExceededError):
        trim_history_to_budget(messages, max_tokens=1)


def test_trim_history_does_not_drop_current_turn_to_fit_budget():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "required tool result"},
        {"role": "tool", "content": "required result"},
    ]

    with pytest.raises(ContextWindowExceededError):
        trim_history_to_budget(messages, max_tokens=2)


def test_trim_history_rejects_negative_history_turn_limit():
    messages = [
        {"role": "user", "content": "question"},
    ]

    with pytest.raises(ValueError, match="max_history_turns"):
        trim_history_to_budget(
            messages,
            max_tokens=100,
            max_history_turns=-1,
        )


def test_trim_history_handles_zero_budget_with_empty_mandatory_content():
    messages = [
        {"role": "system", "content": ""},
        {"role": "user", "content": ""},
    ]

    trimmed = trim_history_to_budget(messages, max_tokens=0)

    assert trimmed == messages


def test_trim_history_handles_empty_and_system_only_messages():
    assert trim_history_to_budget([], max_tokens=100) == []

    system_messages = [
        {"role": "system", "content": "instructions"},
        {"role": "system", "content": "additional instructions"},
    ]

    assert trim_history_to_budget(
        system_messages,
        max_tokens=100,
    ) == system_messages


def test_trim_history_without_user_message_returns_system_messages():
    messages = [
        {"role": "system", "content": "instructions"},
        {"role": "assistant", "content": "orphan assistant message"},
    ]

    assert trim_history_to_budget(messages, max_tokens=100) == [
        {"role": "system", "content": "instructions"},
    ]
