"""Tests for VCGuardCog."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from src.cogs.vc_guard import VCGuardCog, _ensure_can_manage_vcguard


def _make_cog() -> VCGuardCog:
    bot = MagicMock(spec=commands.Bot)
    bot.wait_until_ready = AsyncMock()
    return VCGuardCog(bot)


def _make_member(*, is_bot: bool = False) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = 123
    member.bot = is_bot
    member.guild = MagicMock()
    member.guild.id = 456
    member.move_to = AsyncMock()
    return member


def _make_voice_channel(
    *,
    channel_id: int = 789,
    guild_id: int = 456,
    user_limit: int = 2,
    member_count: int = 3,
) -> MagicMock:
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = channel_id
    channel.guild = MagicMock()
    channel.guild.id = guild_id
    channel.user_limit = user_limit
    channel.members = [MagicMock() for _ in range(member_count)]
    channel.mention = f"<#{channel_id}>"
    return channel


def _make_voice_state(channel: discord.VoiceChannel | None) -> MagicMock:
    state = MagicMock(spec=discord.VoiceState)
    state.channel = channel
    return state


class TestVoiceStateUpdate:
    @pytest.mark.asyncio
    async def test_disconnects_joiner_when_watched_channel_exceeds_limit(self) -> None:
        cog = _make_cog()
        cog._configs = {"456": {"789"}}
        member = _make_member()
        channel = _make_voice_channel(user_limit=2, member_count=3)

        await cog.on_voice_state_update(
            member,
            _make_voice_state(None),
            _make_voice_state(channel),
        )

        member.move_to.assert_called_once_with(
            None,
            reason="VCGuard: VC の人数制限を超過したため切断",
        )

    @pytest.mark.asyncio
    async def test_ignores_unwatched_channel(self) -> None:
        cog = _make_cog()
        cog._configs = {"456": {"999"}}
        member = _make_member()
        channel = _make_voice_channel()

        await cog.on_voice_state_update(
            member,
            _make_voice_state(None),
            _make_voice_state(channel),
        )

        member.move_to.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_when_within_limit(self) -> None:
        cog = _make_cog()
        cog._configs = {"456": {"789"}}
        member = _make_member()
        channel = _make_voice_channel(user_limit=3, member_count=3)

        await cog.on_voice_state_update(
            member,
            _make_voice_state(None),
            _make_voice_state(channel),
        )

        member.move_to.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_unlimited_channel(self) -> None:
        cog = _make_cog()
        cog._configs = {"456": {"789"}}
        member = _make_member()
        channel = _make_voice_channel(user_limit=0, member_count=50)

        await cog.on_voice_state_update(
            member,
            _make_voice_state(None),
            _make_voice_state(channel),
        )

        member.move_to.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_channel_move_with_same_channel(self) -> None:
        cog = _make_cog()
        cog._configs = {"456": {"789"}}
        member = _make_member()
        channel = _make_voice_channel(user_limit=2, member_count=3)

        await cog.on_voice_state_update(
            member,
            _make_voice_state(channel),
            _make_voice_state(channel),
        )

        member.move_to.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_bots(self) -> None:
        cog = _make_cog()
        cog._configs = {"456": {"789"}}
        member = _make_member(is_bot=True)
        channel = _make_voice_channel(user_limit=2, member_count=3)

        await cog.on_voice_state_update(
            member,
            _make_voice_state(None),
            _make_voice_state(channel),
        )

        member.move_to.assert_not_called()

    @pytest.mark.asyncio
    async def test_http_error_is_swallowed(self) -> None:
        cog = _make_cog()
        cog._configs = {"456": {"789"}}
        member = _make_member()
        member.move_to.side_effect = discord.HTTPException(MagicMock(), "error")
        channel = _make_voice_channel(user_limit=2, member_count=3)

        await cog.on_voice_state_update(
            member,
            _make_voice_state(None),
            _make_voice_state(channel),
        )

        member.move_to.assert_called_once()


class TestPermissions:
    @pytest.mark.asyncio
    async def test_allows_administrators(self) -> None:
        interaction = MagicMock(spec=discord.Interaction)
        member = MagicMock(spec=discord.Member)
        member.guild_permissions.administrator = True
        interaction.user = member

        result = await _ensure_can_manage_vcguard(interaction)

        assert result is True
        interaction.response.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_move_members_without_administrator(self) -> None:
        interaction = MagicMock(spec=discord.Interaction)
        member = MagicMock(spec=discord.Member)
        member.guild_permissions.administrator = False
        member.guild_permissions.move_members = True
        interaction.user = member
        interaction.response.send_message = AsyncMock()

        result = await _ensure_can_manage_vcguard(interaction)

        assert result is False
        interaction.response.send_message.assert_called_once_with(
            "このコマンドを使うには管理者権限が必要です。",
            ephemeral=True,
        )


class TestChannelCleanup:
    @pytest.mark.asyncio
    async def test_deleted_watched_voice_channel_is_cleaned_up(self) -> None:
        cog = _make_cog()
        channel = _make_voice_channel()

        with (
            patch(
                "src.cogs.vc_guard.delete_vc_guard_config_by_channel",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_delete,
            patch.object(cog, "_load_cache", new_callable=AsyncMock) as mock_load,
        ):
            await cog.on_guild_channel_delete(channel)

        mock_delete.assert_called_once()
        mock_load.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deleted_channel_without_config_skips_cache_reload(
        self,
    ) -> None:
        cog = _make_cog()
        channel = _make_voice_channel()

        with (
            patch(
                "src.cogs.vc_guard.delete_vc_guard_config_by_channel",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch.object(cog, "_load_cache", new_callable=AsyncMock) as mock_load,
        ):
            await cog.on_guild_channel_delete(channel)

        mock_load.assert_not_called()


class TestCogLifecycle:
    @pytest.mark.asyncio
    async def test_cog_load_starts_tasks(self) -> None:
        cog = _make_cog()
        with (
            patch.object(cog._refresh_cache, "start") as mock_refresh_start,
            patch.object(cog._cleanup_missing_channels, "start") as mock_cleanup_start,
        ):
            await cog.cog_load()

        mock_refresh_start.assert_called_once()
        mock_cleanup_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_cog_unload_cancels_running_tasks(self) -> None:
        cog = _make_cog()
        with (
            patch.object(cog._refresh_cache, "is_running", return_value=True),
            patch.object(cog._refresh_cache, "cancel") as mock_refresh_cancel,
            patch.object(
                cog._cleanup_missing_channels, "is_running", return_value=True
            ),
            patch.object(
                cog._cleanup_missing_channels, "cancel"
            ) as mock_cleanup_cancel,
        ):
            await cog.cog_unload()

        mock_refresh_cancel.assert_called_once()
        mock_cleanup_cancel.assert_called_once()
