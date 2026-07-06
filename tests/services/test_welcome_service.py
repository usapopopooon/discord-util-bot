"""Tests for welcome service helpers."""

from __future__ import annotations

from src.services.welcome_service import (
    DISCORD_MESSAGE_MAX_LENGTH,
    WelcomeMessageInput,
    limit_welcome_message_content,
    render_welcome_message,
)


def test_render_welcome_message_replaces_placeholders() -> None:
    rendered = render_welcome_message(
        "{mention} / {username} / {displayName} / {guildName} / {memberCount}",
        WelcomeMessageInput(
            mention="<@1>",
            username="user",
            display_name="ちるちる",
            guild_name="CHILLカフェ",
            member_count=128,
        ),
    )

    assert rendered == "<@1> / user / ちるちる / CHILLカフェ / 128"


def test_render_welcome_message_supports_snake_case_aliases() -> None:
    rendered = render_welcome_message(
        "{display_name} entered {guild_name} as #{member_count}",
        WelcomeMessageInput(
            mention="<@1>",
            username="user",
            display_name="ちるちる",
            guild_name="CHILLカフェ",
            member_count=128,
        ),
    )

    assert rendered == "ちるちる entered CHILLカフェ as #128"


def test_render_welcome_message_keeps_unknown_placeholders() -> None:
    rendered = render_welcome_message(
        "Hello {unknown}",
        WelcomeMessageInput(
            mention="<@1>",
            username="user",
            display_name="ちるちる",
            guild_name="CHILLカフェ",
            member_count=128,
        ),
    )

    assert rendered == "Hello {unknown}"


def test_limit_welcome_message_content_truncates_to_discord_limit() -> None:
    content = "a" * (DISCORD_MESSAGE_MAX_LENGTH + 10)
    limited = limit_welcome_message_content(content)

    assert len(limited) == DISCORD_MESSAGE_MAX_LENGTH
    assert limited.endswith("...")
