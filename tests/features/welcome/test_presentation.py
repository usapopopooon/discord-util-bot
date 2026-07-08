"""welcome presentation helper tests."""

from types import SimpleNamespace

import discord

from src.features.welcome.presentation import (
    WELCOME_EMBED_COLOR,
    build_welcome_banner_input,
    build_welcome_embed,
    build_welcome_render_inputs,
    build_welcome_status_message,
    format_message_content,
)


def test_format_message_content_truncates_long_text() -> None:
    formatted = format_message_content("あ" * 141)

    assert formatted == f"{'あ' * 137}..."


def test_build_welcome_status_message_for_disabled_config() -> None:
    message = build_welcome_status_message(None)

    assert "welcome投稿は無効です。" in message
    assert "デフォルト本文" in message
    assert "{mention}" in message


def test_build_welcome_status_message_for_enabled_config() -> None:
    config = SimpleNamespace(
        enabled=True,
        channel_id="123",
        message_content="いらっしゃいませ、{mention}!",
        banner_message_template="{displayName} さんが入店しました",
    )

    message = build_welcome_status_message(config)

    assert "welcome投稿は有効です。送信先: <#123>" in message
    assert "本文: いらっしゃいませ、{mention}!" in message
    assert "画像内メッセージ: {displayName} さんが入店しました" in message


def test_build_welcome_render_inputs_uses_public_and_banner_mentions() -> None:
    inputs = build_welcome_render_inputs(
        username="chill",
        display_name="ちるちる",
        guild_name="CHILLカフェ",
        member_count=128,
        mention="<@123>",
    )

    assert inputs.message.mention == "<@123>"
    assert inputs.banner.mention == "@ちるちる"
    assert inputs.message.display_name == "ちるちる"


def test_build_welcome_banner_input_renders_headline() -> None:
    inputs = build_welcome_render_inputs(
        username="chill",
        display_name="ちるちる",
        guild_name="CHILLカフェ",
        member_count=128,
        mention="<@123>",
    )

    banner_input = build_welcome_banner_input(
        display_name="ちるちる",
        username="chill",
        guild_name="CHILLカフェ",
        member_count=128,
        banner_message_template="{displayName} さんが {guildName} に入店",
        inputs=inputs,
        avatar_bytes=b"avatar",
    )

    assert banner_input.headline_text == "ちるちる さんが CHILLカフェ に入店"
    assert banner_input.avatar_bytes == b"avatar"


def test_build_welcome_embed_points_to_attachment() -> None:
    inputs = build_welcome_render_inputs(
        username="chill",
        display_name="ちるちる",
        guild_name="CHILLカフェ",
        member_count=128,
        mention="<@123>",
    )

    embed = build_welcome_embed(
        message_template="いらっしゃいませ、{mention}!",
        inputs=inputs,
        attachment_name="welcome-123.png",
    )

    assert isinstance(embed, discord.Embed)
    assert embed.description == "いらっしゃいませ、<@123>!"
    assert embed.color == discord.Color(WELCOME_EMBED_COLOR)
    assert embed.image.url == "attachment://welcome-123.png"
