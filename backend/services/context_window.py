
"""Context-window management: token counting, history trimming, and prompt truncation."""
from __future__ import annotations

from typing import Any

CHARS_PER_TOKEN_FALLBACK = 4


class ContextWindowExceededError(ValueError):
    """Raised when mandatory prompt messages exceed the token budget."""


def count_tokens(text: str, tokenizer: Any | None = None) -> int:
    """Count tokens using the loaded tokenizer, or estimate ~4 chars/token."""
    if not text:
        return 0

    if tokenizer is not None:
        return len(tokenizer.encode(text, add_special_tokens=False))

    return max(
        1,
        (len(text) + CHARS_PER_TOKEN_FALLBACK - 1)
        // CHARS_PER_TOKEN_FALLBACK,
    )


def truncate_prompt_text(
    text: str,
    max_tokens: int,
    tokenizer: Any | None = None,
) -> tuple[str, bool]:
    """Truncate text to fit within max_tokens. Returns (text, was_truncated)."""
    if max_tokens <= 0:
        return "", bool(text)

    if tokenizer is not None:
        ids = tokenizer.encode(text, add_special_tokens=False)
        if len(ids) <= max_tokens:
            return text, False

        truncated = tokenizer.decode(
            ids[:max_tokens],
            skip_special_tokens=True,
        )
        return truncated, True

    max_chars = max_tokens * CHARS_PER_TOKEN_FALLBACK
    if len(text) <= max_chars:
        return text, False

    return text[:max_chars], True


def _message_tokens(
    messages: list[dict[str, str]],
    tokenizer: Any | None,
) -> int:
    """Count the content tokens in a group of messages."""
    return sum(
        count_tokens(message.get("content", ""), tokenizer)
        for message in messages
    )


def _group_history_turns(
    messages: list[dict[str, str]],
) -> list[list[dict[str, str]]]:
    """Group messages into user-initiated turns.

    Every user message starts a new turn. Assistant and tool messages
    following that user message remain part of the same turn.
    """
    turns: list[list[dict[str, str]]] = []
    current_turn: list[dict[str, str]] = []

    for message in messages:
        if message.get("role") == "user" and current_turn:
            turns.append(current_turn)
            current_turn = []

        current_turn.append(message)

    if current_turn:
        turns.append(current_turn)

    return turns


def trim_history_to_budget(
    messages: list[dict[str, str]],
    max_tokens: int,
    tokenizer: Any | None = None,
    max_history_turns: int | None = None,
) -> list[dict[str, str]]:
    """Keep system messages and the latest user turn, trimming old turns.

    System messages and the latest user-initiated turn are mandatory.
    Older history is removed from oldest to newest until the budget fits.

    Raises:
        ContextWindowExceededError: If mandatory messages exceed max_tokens.
    """
    if not messages:
        return []

    system_messages = [
        message for message in messages
        if message.get("role") == "system"
    ]
    non_system_messages = [
        message for message in messages
        if message.get("role") != "system"
    ]

    # Without a user message, there is no current user turn to preserve.
    if not any(
        message.get("role") == "user"
        for message in non_system_messages
    ):
        return system_messages

    latest_user_index = max(
        index
        for index, message in enumerate(non_system_messages)
        if message.get("role") == "user"
    )

    history_messages = non_system_messages[:latest_user_index]
    current_turn = non_system_messages[latest_user_index:]

    history_turns = _group_history_turns(history_messages)

    if max_history_turns is not None:
        if max_history_turns < 0:
            raise ValueError("max_history_turns cannot be negative")

        if max_history_turns == 0:
            history_turns = []
        else:
            history_turns = history_turns[-max_history_turns:]

    mandatory_tokens = _message_tokens(
        system_messages,
        tokenizer,
    ) + _message_tokens(current_turn, tokenizer)

    if mandatory_tokens > max_tokens:
        raise ContextWindowExceededError(
            "Mandatory system and current-turn messages require "
            f"{mandatory_tokens} tokens, but the available budget is "
            f"{max_tokens} tokens."
        )

    remaining_tokens = max_tokens - mandatory_tokens
    kept_history_reversed: list[list[dict[str, str]]] = []

    # Keep the newest complete history turns first.
    for turn in reversed(history_turns):
        turn_tokens = _message_tokens(turn, tokenizer)

        if turn_tokens > remaining_tokens:
            break

        kept_history_reversed.append(turn)
        remaining_tokens -= turn_tokens

    kept_history: list[dict[str, str]] = []
    for turn in reversed(kept_history_reversed):
        kept_history.extend(turn)

    return [
        *system_messages,
        *kept_history,
        *current_turn,
    ]
