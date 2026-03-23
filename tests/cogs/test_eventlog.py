"""Tests for EventLogCog (event logging feature)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from src.cogs.eventlog import EventLogCog

# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------


def _make_cog() -> EventLogCog:
    """Create an EventLogCog with a mock bot."""
    bot = MagicMock(spec=commands.Bot)
    bot.guilds = []
    cog = EventLogCog(bot)
    return cog


def _make_guild(guild_id: int = 789) -> MagicMock:
    """Create a mock guild with a sendable text channel."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    ch = MagicMock(spec=discord.TextChannel)
    ch.send = AsyncMock()
    guild.get_channel = MagicMock(return_value=ch)
    return guild, ch


def _make_member(
    *,
    user_id: int = 12345,
    guild_id: int = 789,
    is_bot: bool = False,
) -> MagicMock:
    """Create a mock Discord member."""
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.bot = is_bot
    member.name = "testuser"
    member.nick = "TestNick"
    member.display_avatar = MagicMock()
    member.display_avatar.url = "https://cdn.example.com/avatar.png"
    member.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    member.joined_at = datetime(2025, 6, 1, tzinfo=UTC)
    everyone_role = MagicMock(spec=discord.Role)
    everyone_role.name = "@everyone"
    member.roles = [everyone_role]
    member.timed_out_until = None
    member.guild = MagicMock()
    member.guild.id = guild_id
    return member


def _make_message(
    *,
    guild_id: int = 789,
    author_bot: bool = False,
    content: str = "Hello world",
) -> MagicMock:
    """Create a mock Discord message."""
    msg = MagicMock(spec=discord.Message)
    msg.guild = MagicMock()
    msg.guild.id = guild_id
    msg.author = MagicMock()
    msg.author.id = 12345
    msg.author.bot = author_bot
    msg.author.display_avatar = MagicMock()
    msg.author.display_avatar.url = "https://cdn.example.com/avatar.png"
    msg.channel = MagicMock()
    msg.channel.id = 100
    msg.content = content
    msg.jump_url = "https://discord.com/channels/789/100/999"
    return msg


# ---------------------------------------------------------------------------
# TestOnMessageDelete
# ---------------------------------------------------------------------------


class TestOnMessageDelete:
    """on_message_delete イベントのテスト。"""

    @pytest.mark.asyncio
    async def test_ignores_bots(self) -> None:
        """Bot のメッセージは無視される。"""
        cog = _make_cog()
        msg = _make_message(author_bot=True)
        await cog.on_message_delete(msg)

    @pytest.mark.asyncio
    async def test_ignores_dm(self) -> None:
        """DM のメッセージは無視される。"""
        cog = _make_cog()
        msg = _make_message()
        msg.guild = None
        await cog.on_message_delete(msg)

    @pytest.mark.asyncio
    async def test_skips_no_config(self) -> None:
        """設定がない場合はスキップする。"""
        cog = _make_cog()
        msg = _make_message()
        await cog.on_message_delete(msg)
        # No error, no send called

    @pytest.mark.asyncio
    async def test_sends_embed(self) -> None:
        """設定がある場合は Embed を送信する。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        msg = _make_message()
        msg.guild = guild

        # audit log が空 (自分で削除)
        async def _empty_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            return
            yield  # noqa: RET504

        guild.audit_logs = _empty_audit

        cog._cache[("789", "message_delete")] = ["100"]

        await cog.on_message_delete(msg)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Message Deleted"
        assert "Hello world" in embed.fields[2].value

    @pytest.mark.asyncio
    async def test_shows_deleted_by(self) -> None:
        """他ユーザーが削除した場合は Deleted By を表示する。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        msg = _make_message()
        msg.guild = guild

        # audit log エントリ (モデレーターが削除)
        entry = MagicMock()
        entry.target = MagicMock()
        entry.target.id = 12345  # message author
        entry.user = MagicMock()
        entry.user.id = 55555  # moderator
        entry.extra = MagicMock()
        entry.extra.channel = MagicMock()
        entry.extra.channel.id = 100  # same as message channel
        entry.created_at = datetime.now(UTC)

        async def _del_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            yield entry

        guild.audit_logs = _del_audit

        cog._cache[("789", "message_delete")] = ["100"]

        await cog.on_message_delete(msg)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Message Deleted"
        field_names = [f.name for f in embed.fields]
        assert "Deleted By" in field_names
        deleted_field = next(f for f in embed.fields if f.name == "Deleted By")
        assert "<@55555>" in deleted_field.value

    @pytest.mark.asyncio
    async def test_no_deleted_by_for_self_delete(self) -> None:
        """自分で削除した場合は Deleted By を表示しない。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        msg = _make_message()
        msg.guild = guild

        # audit log が空 (自分で削除した場合はエントリなし)
        async def _empty_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            return
            yield  # noqa: RET504

        guild.audit_logs = _empty_audit

        cog._cache[("789", "message_delete")] = ["100"]

        await cog.on_message_delete(msg)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        field_names = [f.name for f in embed.fields]
        assert "Deleted By" not in field_names

    @pytest.mark.asyncio
    async def test_truncates_long_content(self) -> None:
        """長いメッセージは切り詰められる。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        msg = _make_message(content="x" * 2000)
        msg.guild = guild

        async def _empty_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            return
            yield  # noqa: RET504

        guild.audit_logs = _empty_audit

        cog._cache[("789", "message_delete")] = ["100"]

        await cog.on_message_delete(msg)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        # Content is the last field (index varies based on Deleted By presence)
        content_field = next(f for f in embed.fields if f.name == "Content")
        assert len(content_field.value) <= 1024


# ---------------------------------------------------------------------------
# TestOnMessageEdit
# ---------------------------------------------------------------------------


class TestOnMessageEdit:
    """on_message_edit イベントのテスト。"""

    @pytest.mark.asyncio
    async def test_ignores_bots(self) -> None:
        cog = _make_cog()
        before = _make_message(author_bot=True)
        after = _make_message(author_bot=True, content="Updated")
        await cog.on_message_edit(before, after)

    @pytest.mark.asyncio
    async def test_skips_same_content(self) -> None:
        """内容が同じ場合はスキップする。"""
        cog = _make_cog()
        before = _make_message(content="Same")
        after = _make_message(content="Same")
        await cog.on_message_edit(before, after)

    @pytest.mark.asyncio
    async def test_sends_embed(self) -> None:
        """編集があった場合は Embed を送信する。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        before = _make_message(content="Before")
        after = _make_message(content="After")
        before.guild = guild
        after.guild = guild

        cog._cache[("789", "message_edit")] = ["100"]

        await cog.on_message_edit(before, after)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Message Edited"
        assert "Before" in embed.fields[2].value
        assert "After" in embed.fields[3].value


# ---------------------------------------------------------------------------
# TestOnMemberJoin
# ---------------------------------------------------------------------------


class TestOnMemberJoinLog:
    """on_member_join イベントのテスト。"""

    @pytest.mark.asyncio
    async def test_ignores_bots(self) -> None:
        cog = _make_cog()
        member = _make_member(is_bot=True)
        await cog.on_member_join(member)

    @pytest.mark.asyncio
    async def test_sends_embed(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        guild.invites = AsyncMock(return_value=[])
        guild.vanity_invite = AsyncMock(return_value=None)
        member = _make_member()
        member.guild = guild

        cog._cache[("789", "member_join")] = ["100"]

        await cog.on_member_join(member)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Member Joined"

    @pytest.mark.asyncio
    async def test_shows_invite_info(self) -> None:
        """招待キャッシュ差分から招待者情報を表示する。"""
        cog = _make_cog()
        guild, ch = _make_guild()

        # 招待モック
        invite = MagicMock()
        invite.code = "abc123"
        invite.uses = 2  # 以前は 1 だった
        invite.inviter = MagicMock()
        invite.inviter.id = 99999
        invite.inviter.name = "InviterUser"
        guild.invites = AsyncMock(return_value=[invite])
        guild.vanity_invite = AsyncMock(return_value=None)

        member = _make_member()
        member.guild = guild

        cog._cache[("789", "member_join")] = ["100"]
        # 招待キャッシュを事前セット (uses=1 で保存)
        from src.cogs.eventlog import _InviteData

        cog._invite_cache[789] = {
            "abc123": _InviteData("abc123", 1, 99999, "InviterUser"),
        }

        await cog.on_member_join(member)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Member Joined"
        # Invited By フィールドが存在する
        field_names = [f.name for f in embed.fields]
        assert "Invited By" in field_names
        invite_field = next(f for f in embed.fields if f.name == "Invited By")
        assert "<@99999>" in invite_field.value
        assert "abc123" in invite_field.value
        assert "Total: 2" in invite_field.value


# ---------------------------------------------------------------------------
# TestOnMemberRemove
# ---------------------------------------------------------------------------


class TestOnMemberRemove:
    """on_member_remove イベントのテスト。"""

    @pytest.mark.asyncio
    async def test_ignores_bots(self) -> None:
        cog = _make_cog()
        member = _make_member(is_bot=True)
        await cog.on_member_remove(member)

    @pytest.mark.asyncio
    async def test_sends_leave_embed(self) -> None:
        """kick でない場合は leave ログを送信する。"""
        cog = _make_cog()
        guild, ch = _make_guild()

        # audit_logs が空 (kick ではない)
        async def _empty_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            return
            yield  # noqa: RET504  # make it async generator

        guild.audit_logs = _empty_audit
        member = _make_member()
        member.guild = guild

        cog._cache[("789", "member_leave")] = ["100"]

        await cog.on_member_remove(member)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Member Left"

    @pytest.mark.asyncio
    async def test_sends_kick_embed(self) -> None:
        """audit log に kick があれば kick ログを送信する。"""
        cog = _make_cog()
        guild, ch = _make_guild()

        # audit log エントリ (kick)
        entry = MagicMock()
        entry.target = MagicMock()
        entry.target.id = 12345
        entry.user = MagicMock()
        entry.user.id = 99999
        entry.reason = "Spamming"
        entry.created_at = datetime.now(UTC)

        async def _kick_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            yield entry

        guild.audit_logs = _kick_audit
        member = _make_member()
        member.guild = guild

        cog._cache[("789", "member_kick")] = ["100"]

        await cog.on_member_remove(member)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Member Kicked"
        assert "<@99999>" in embed.fields[1].value
        assert "Spamming" in embed.fields[2].value

    @pytest.mark.asyncio
    async def test_kick_without_kick_config_falls_back_to_leave(self) -> None:
        """kick 設定がない場合、kick されたメンバーも leave ログに出る。"""
        cog = _make_cog()
        guild, ch = _make_guild()

        # audit_logs は呼ばれないはず (has_kick=False)
        guild.audit_logs = MagicMock(side_effect=AssertionError("should not be called"))
        member = _make_member()
        member.guild = guild

        # kick 設定なし、leave 設定あり
        cog._cache[("789", "member_leave")] = ["100"]

        await cog.on_member_remove(member)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Member Left"

    @pytest.mark.asyncio
    async def test_no_config_skips(self) -> None:
        """leave も kick も設定なしの場合はスキップ。"""
        cog = _make_cog()
        member = _make_member()
        await cog.on_member_remove(member)
        # No error, no send called


# ---------------------------------------------------------------------------
# TestOnMemberBan
# ---------------------------------------------------------------------------


class TestOnMemberBan:
    """on_member_ban イベントのテスト。"""

    @pytest.mark.asyncio
    async def test_ignores_bots(self) -> None:
        cog = _make_cog()
        user = MagicMock(spec=discord.User)
        user.bot = True
        guild = MagicMock(spec=discord.Guild)
        await cog.on_member_ban(guild, user)

    @pytest.mark.asyncio
    async def test_sends_embed_with_moderator(self) -> None:
        """audit log からモデレーター情報と理由を取得して表示する。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        user = MagicMock(spec=discord.User)
        user.id = 12345
        user.bot = False
        user.display_avatar = MagicMock()
        user.display_avatar.url = "https://cdn.example.com/avatar.png"

        # audit log エントリ (ban)
        entry = MagicMock()
        entry.target = MagicMock()
        entry.target.id = 12345
        entry.user = MagicMock()
        entry.user.id = 77777
        entry.reason = "Spam"
        entry.created_at = datetime.now(UTC)

        async def _ban_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            yield entry

        guild.audit_logs = _ban_audit

        cog._cache[("789", "member_ban")] = ["100"]

        await cog.on_member_ban(guild, user)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Member Banned"
        assert "<@77777>" in embed.fields[1].value  # Banned By
        assert "Spam" in embed.fields[2].value  # Reason

    @pytest.mark.asyncio
    async def test_falls_back_to_fetch_ban(self) -> None:
        """audit log で取得できない場合は fetch_ban から理由を取得する。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        user = MagicMock(spec=discord.User)
        user.id = 12345
        user.bot = False
        user.display_avatar = MagicMock()
        user.display_avatar.url = "https://cdn.example.com/avatar.png"

        # audit log が空
        async def _empty_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            return
            yield  # noqa: RET504

        guild.audit_logs = _empty_audit

        ban_entry = MagicMock()
        ban_entry.reason = "Spam via fetch_ban"
        guild.fetch_ban = AsyncMock(return_value=ban_entry)

        cog._cache[("789", "member_ban")] = ["100"]

        await cog.on_member_ban(guild, user)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Member Banned"
        # モデレーターなし → fields[1] が Reason
        assert "Spam via fetch_ban" in embed.fields[1].value


# ---------------------------------------------------------------------------
# TestOnMemberUnban
# ---------------------------------------------------------------------------


class TestOnMemberUnban:
    """on_member_unban イベントのテスト。"""

    @pytest.mark.asyncio
    async def test_ignores_bots(self) -> None:
        cog = _make_cog()
        user = MagicMock(spec=discord.User)
        user.bot = True
        guild = MagicMock(spec=discord.Guild)
        await cog.on_member_unban(guild, user)

    @pytest.mark.asyncio
    async def test_sends_embed_with_moderator(self) -> None:
        """audit log からモデレーター情報を取得して表示する。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        user = MagicMock(spec=discord.User)
        user.id = 12345
        user.bot = False
        user.display_avatar = MagicMock()
        user.display_avatar.url = "https://cdn.example.com/avatar.png"

        # audit log エントリ (unban)
        entry = MagicMock()
        entry.target = MagicMock()
        entry.target.id = 12345
        entry.user = MagicMock()
        entry.user.id = 66666
        entry.created_at = datetime.now(UTC)

        async def _unban_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            yield entry

        guild.audit_logs = _unban_audit

        cog._cache[("789", "member_unban")] = ["100"]

        await cog.on_member_unban(guild, user)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Member Unbanned"
        assert "<@66666>" in embed.fields[1].value  # Unbanned By


# ---------------------------------------------------------------------------
# TestOnMemberUpdate
# ---------------------------------------------------------------------------


class TestOnMemberUpdate:
    """on_member_update イベントのテスト。"""

    @pytest.mark.asyncio
    async def test_ignores_bots(self) -> None:
        cog = _make_cog()
        before = _make_member(is_bot=True)
        after = _make_member(is_bot=True)
        await cog.on_member_update(before, after)

    @pytest.mark.asyncio
    async def test_role_change(self) -> None:
        """ロール変更を検知して Embed を送信する。"""
        cog = _make_cog()
        guild, ch = _make_guild()

        role_a = MagicMock(spec=discord.Role)
        role_a.name = "RoleA"
        role_a.mention = "<@&111>"
        role_b = MagicMock(spec=discord.Role)
        role_b.name = "RoleB"
        role_b.mention = "<@&222>"

        before = _make_member()
        before.guild = guild
        before.roles = [role_a]

        after = _make_member()
        after.guild = guild
        after.roles = [role_a, role_b]
        after.nick = before.nick  # No nickname change

        cog._cache[("789", "role_change")] = ["100"]

        await cog.on_member_update(before, after)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Member Roles Updated"
        assert "+ <@&222>" in embed.fields[1].value

    @pytest.mark.asyncio
    async def test_nickname_change(self) -> None:
        """ニックネーム変更を検知して Embed を送信する。"""
        cog = _make_cog()
        guild, ch = _make_guild()

        before = _make_member()
        before.guild = guild
        before.nick = "OldNick"

        after = _make_member()
        after.guild = guild
        after.nick = "NewNick"
        after.roles = before.roles  # No role change

        cog._cache[("789", "nickname_change")] = ["100"]

        await cog.on_member_update(before, after)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Nickname Changed"
        assert "OldNick" in embed.fields[1].value
        assert "NewNick" in embed.fields[2].value


# ---------------------------------------------------------------------------
# TestOnMemberTimeout
# ---------------------------------------------------------------------------


class TestOnMemberTimeout:
    """タイムアウト検出のテスト。"""

    @pytest.mark.asyncio
    async def test_timeout_detected(self) -> None:
        """timed_out_until が設定されたら timeout ログを送信する。"""
        cog = _make_cog()
        guild, ch = _make_guild()

        before = _make_member()
        before.guild = guild
        before.timed_out_until = None

        after = _make_member()
        after.guild = guild
        after.timed_out_until = datetime(2026, 3, 10, tzinfo=UTC)
        after.roles = before.roles  # No role change
        after.nick = before.nick  # No nickname change

        # audit_logs mock
        entry = MagicMock()
        entry.target = MagicMock()
        entry.target.id = after.id
        entry.user = MagicMock()
        entry.user.id = 88888
        entry.reason = "Calm down"
        entry.created_at = datetime.now(UTC)

        async def _audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            yield entry

        guild.audit_logs = _audit

        cog._cache[("789", "member_timeout")] = ["100"]

        await cog.on_member_update(before, after)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Member Timed Out"
        assert "<@88888>" in embed.fields[1].value
        assert "Calm down" in embed.fields[3].value


# ---------------------------------------------------------------------------
# TestOnGuildChannelCreate / Delete
# ---------------------------------------------------------------------------


class TestChannelEvents:
    """チャンネル作成/削除イベントのテスト。"""

    @pytest.mark.asyncio
    async def test_channel_create(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        channel = MagicMock(spec=discord.TextChannel)
        channel.guild = guild
        channel.name = "new-channel"
        channel.type = discord.ChannelType.text
        channel.category = None

        cog._cache[("789", "channel_create")] = ["100"]

        await cog.on_guild_channel_create(channel)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Channel Created"
        assert "new-channel" in embed.fields[0].value

    @pytest.mark.asyncio
    async def test_channel_delete(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        channel = MagicMock(spec=discord.TextChannel)
        channel.guild = guild
        channel.name = "deleted-channel"
        channel.type = discord.ChannelType.text
        channel.category = None

        cog._cache[("789", "channel_delete")] = ["100"]

        await cog.on_guild_channel_delete(channel)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Channel Deleted"


# ---------------------------------------------------------------------------
# TestOnVoiceStateUpdate
# ---------------------------------------------------------------------------


class TestOnVoiceStateUpdate:
    """on_voice_state_update イベントのテスト。"""

    @pytest.mark.asyncio
    async def test_ignores_bots(self) -> None:
        cog = _make_cog()
        member = _make_member(is_bot=True)
        before = MagicMock(spec=discord.VoiceState)
        after = MagicMock(spec=discord.VoiceState)
        await cog.on_voice_state_update(member, before, after)

    @pytest.mark.asyncio
    async def test_join(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        member = _make_member()
        member.guild = guild

        before = MagicMock(spec=discord.VoiceState)
        before.channel = None
        after = MagicMock(spec=discord.VoiceState)
        after.channel = MagicMock()
        after.channel.id = 200

        cog._cache[("789", "voice_state")] = ["100"]

        await cog.on_voice_state_update(member, before, after)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Joined Voice Channel"

    @pytest.mark.asyncio
    async def test_leave(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        member = _make_member()
        member.guild = guild

        before = MagicMock(spec=discord.VoiceState)
        before.channel = MagicMock()
        before.channel.id = 200
        after = MagicMock(spec=discord.VoiceState)
        after.channel = None

        cog._cache[("789", "voice_state")] = ["100"]

        await cog.on_voice_state_update(member, before, after)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Left Voice Channel"

    @pytest.mark.asyncio
    async def test_move(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        member = _make_member()
        member.guild = guild

        before = MagicMock(spec=discord.VoiceState)
        before.channel = MagicMock()
        before.channel.id = 200
        after = MagicMock(spec=discord.VoiceState)
        after.channel = MagicMock()
        after.channel.id = 300

        cog._cache[("789", "voice_state")] = ["100"]

        await cog.on_voice_state_update(member, before, after)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Moved Voice Channel"

    @pytest.mark.asyncio
    async def test_mute_ignored(self) -> None:
        """ミュート等の状態変更はスキップされる。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        member = _make_member()
        member.guild = guild

        same_channel = MagicMock()
        same_channel.id = 200
        before = MagicMock(spec=discord.VoiceState)
        before.channel = same_channel
        after = MagicMock(spec=discord.VoiceState)
        after.channel = same_channel

        cog._cache[("789", "voice_state")] = ["100"]

        await cog.on_voice_state_update(member, before, after)
        ch.send.assert_not_called()


# ---------------------------------------------------------------------------
# TestSendLog
# ---------------------------------------------------------------------------


class TestSendLog:
    """_send_log の共通テスト。"""

    @pytest.mark.asyncio
    async def test_handles_forbidden(self) -> None:
        """権限不足でも例外を上げない。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        ch.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), ""))

        cog._cache[("789", "message_delete")] = ["100"]

        embed = discord.Embed(title="Test")
        await cog._send_log(guild, "message_delete", embed)
        # No exception raised

    @pytest.mark.asyncio
    async def test_handles_missing_channel(self) -> None:
        """チャンネルが見つからなくても例外を上げない。"""
        cog = _make_cog()
        guild, _ = _make_guild()
        guild.get_channel = MagicMock(return_value=None)

        cog._cache[("789", "message_delete")] = ["100"]

        embed = discord.Embed(title="Test")
        await cog._send_log(guild, "message_delete", embed)
        # No exception raised


# ---------------------------------------------------------------------------
# TestRefreshCache
# ---------------------------------------------------------------------------


class TestRefreshCache:
    """キャッシュ更新のテスト。"""

    @pytest.mark.asyncio
    async def test_refresh_cache(self) -> None:
        """DB から設定を読み込んでキャッシュする。"""
        cog = _make_cog()
        guild = MagicMock()
        guild.id = 789
        cog.bot.guilds = [guild]

        mock_config = MagicMock()
        mock_config.event_type = "message_delete"
        mock_config.channel_id = "100"

        with patch(
            "src.cogs.eventlog.get_enabled_event_log_configs",
            return_value=[mock_config],
        ):
            await cog._refresh_cache()

        assert cog._cache == {("789", "message_delete"): ["100"]}


# ---------------------------------------------------------------------------
# TestInviteCache
# ---------------------------------------------------------------------------


class TestInviteCache:
    """招待キャッシュ操作のテスト。"""

    @pytest.mark.asyncio
    async def test_on_invite_create(self) -> None:
        """招待作成時にキャッシュに追加される。"""
        cog = _make_cog()
        invite = MagicMock()
        invite.guild = MagicMock()
        invite.guild.id = 789
        invite.code = "inv001"
        invite.uses = 0
        invite.inviter = MagicMock()
        invite.inviter.id = 11111
        invite.inviter.name = "Creator"

        await cog.on_invite_create(invite)

        assert "inv001" in cog._invite_cache[789]
        assert cog._invite_cache[789]["inv001"].inviter_id == 11111

    @pytest.mark.asyncio
    async def test_on_invite_create_no_guild(self) -> None:
        """guild がない招待は無視する。"""
        cog = _make_cog()
        invite = MagicMock()
        invite.guild = None

        await cog.on_invite_create(invite)
        assert cog._invite_cache == {}

    @pytest.mark.asyncio
    async def test_on_invite_delete(self) -> None:
        """招待削除時にキャッシュから削除される。"""
        from src.cogs.eventlog import _InviteData

        cog = _make_cog()
        cog._invite_cache[789] = {
            "inv002": _InviteData("inv002", 5, 11111, "User"),
        }

        invite = MagicMock()
        invite.guild = MagicMock()
        invite.guild.id = 789
        invite.code = "inv002"

        await cog.on_invite_delete(invite)
        assert "inv002" not in cog._invite_cache[789]

    @pytest.mark.asyncio
    async def test_on_invite_delete_no_guild(self) -> None:
        """guild がない招待は無視する。"""
        cog = _make_cog()
        invite = MagicMock()
        invite.guild = None

        await cog.on_invite_delete(invite)

    @pytest.mark.asyncio
    async def test_cache_guild_invites_forbidden(self) -> None:
        """権限なしでもエラーにならない。"""
        cog = _make_cog()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 789
        guild.invites = AsyncMock(side_effect=discord.Forbidden(MagicMock(), ""))

        await cog._cache_guild_invites(guild)
        # No error raised, cache unchanged


# ---------------------------------------------------------------------------
# TestDetectUsedInvite
# ---------------------------------------------------------------------------


class TestDetectUsedInvite:
    """_detect_used_invite のテスト。"""

    @pytest.mark.asyncio
    async def test_vanity_url_fallback(self) -> None:
        """通常招待で特定できない場合、vanity URL を返す。"""
        cog = _make_cog()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 789
        guild.invites = AsyncMock(return_value=[])
        vanity = MagicMock()
        guild.vanity_invite = AsyncMock(return_value=vanity)

        result = await cog._detect_used_invite(guild)
        assert result == "Vanity URL"

    @pytest.mark.asyncio
    async def test_expired_invite_detected(self) -> None:
        """max_uses に達して消えた招待を検出する。"""
        from src.cogs.eventlog import _InviteData

        cog = _make_cog()
        # キャッシュにはあるが、新しい招待一覧にはない
        cog._invite_cache[789] = {
            "expired": _InviteData("expired", 4, 22222, "Inviter"),
        }

        guild = MagicMock(spec=discord.Guild)
        guild.id = 789
        guild.invites = AsyncMock(return_value=[])
        guild.vanity_invite = AsyncMock(return_value=None)

        result = await cog._detect_used_invite(guild)
        assert result is not None
        assert "<@22222>" in result
        assert "expired" in result
        assert "Total: 4" in result

    @pytest.mark.asyncio
    async def test_invites_forbidden(self) -> None:
        """招待取得権限なしで None を返す。"""
        cog = _make_cog()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 789
        guild.invites = AsyncMock(side_effect=discord.Forbidden(MagicMock(), ""))

        result = await cog._detect_used_invite(guild)
        assert result is None

    @pytest.mark.asyncio
    async def test_invite_without_inviter(self) -> None:
        """招待者なし (Bot 招待等) の場合はコードのみ表示。"""
        from src.cogs.eventlog import _InviteData

        cog = _make_cog()
        cog._invite_cache[789] = {
            "inv003": _InviteData("inv003", 0, None, None),
        }

        invite = MagicMock()
        invite.code = "inv003"
        invite.uses = 1
        invite.inviter = None

        guild = MagicMock(spec=discord.Guild)
        guild.id = 789
        guild.invites = AsyncMock(return_value=[invite])
        guild.vanity_invite = AsyncMock(return_value=None)

        result = await cog._detect_used_invite(guild)
        assert result is not None
        assert "inv003" in result
        assert "<@" not in result

    @pytest.mark.asyncio
    async def test_total_uses_sums_all_invites(self) -> None:
        """同じ招待者の複数招待の合計使用回数が表示される。"""
        from src.cogs.eventlog import _InviteData

        cog = _make_cog()
        cog._invite_cache[789] = {
            "inv_a": _InviteData("inv_a", 5, 11111, "User"),
            "inv_b": _InviteData("inv_b", 3, 11111, "User"),
        }

        inv_a = MagicMock()
        inv_a.code = "inv_a"
        inv_a.uses = 6
        inv_a.inviter = MagicMock()
        inv_a.inviter.id = 11111
        inv_a.inviter.name = "User"

        inv_b = MagicMock()
        inv_b.code = "inv_b"
        inv_b.uses = 3
        inv_b.inviter = MagicMock()
        inv_b.inviter.id = 11111
        inv_b.inviter.name = "User"

        guild = MagicMock(spec=discord.Guild)
        guild.id = 789
        guild.invites = AsyncMock(return_value=[inv_a, inv_b])

        result = await cog._detect_used_invite(guild)
        assert result is not None
        assert "<@11111>" in result
        assert "Total: 9" in result


# ---------------------------------------------------------------------------
# TestAuditLogFallback
# ---------------------------------------------------------------------------


class TestAuditLogFallback:
    """audit log Forbidden 時のフォールバックテスト。"""

    @pytest.mark.asyncio
    async def test_ban_audit_forbidden_falls_back_to_fetch_ban(self) -> None:
        """audit log Forbidden でも fetch_ban で理由取得。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        user = MagicMock(spec=discord.User)
        user.id = 12345
        user.bot = False
        user.display_avatar = MagicMock()
        user.display_avatar.url = "https://cdn.example.com/avatar.png"

        async def _forbidden_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            raise discord.Forbidden(MagicMock(), "")
            yield  # noqa: RET504

        guild.audit_logs = _forbidden_audit

        ban_entry = MagicMock()
        ban_entry.reason = "Reason from fetch_ban"
        guild.fetch_ban = AsyncMock(return_value=ban_entry)

        cog._cache[("789", "member_ban")] = ["100"]

        await cog.on_member_ban(guild, user)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert "Reason from fetch_ban" in embed.fields[1].value

    @pytest.mark.asyncio
    async def test_message_delete_audit_forbidden(self) -> None:
        """audit log Forbidden でもメッセージ削除ログは送信される。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        msg = _make_message()
        msg.guild = guild

        async def _forbidden_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            raise discord.Forbidden(MagicMock(), "")
            yield  # noqa: RET504

        guild.audit_logs = _forbidden_audit

        cog._cache[("789", "message_delete")] = ["100"]

        await cog.on_message_delete(msg)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Message Deleted"
        # Deleted By なし (Forbidden なので)
        field_names = [f.name for f in embed.fields]
        assert "Deleted By" not in field_names

    @pytest.mark.asyncio
    async def test_kick_audit_forbidden_falls_back_to_leave(self) -> None:
        """audit log Forbidden で kick 判定できない場合は leave ログ。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        member = _make_member()
        member.guild = guild

        async def _forbidden_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            raise discord.Forbidden(MagicMock(), "")
            yield  # noqa: RET504

        guild.audit_logs = _forbidden_audit

        cog._cache[("789", "member_kick")] = ["100"]
        cog._cache[("789", "member_leave")] = ["100"]

        await cog.on_member_remove(member)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Member Left"

    @pytest.mark.asyncio
    async def test_unban_audit_forbidden(self) -> None:
        """unban audit log Forbidden でもログは送信される。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        user = MagicMock(spec=discord.User)
        user.id = 12345
        user.bot = False
        user.display_avatar = MagicMock()
        user.display_avatar.url = "https://cdn.example.com/avatar.png"

        async def _forbidden_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            raise discord.Forbidden(MagicMock(), "")
            yield  # noqa: RET504

        guild.audit_logs = _forbidden_audit

        cog._cache[("789", "member_unban")] = ["100"]

        await cog.on_member_unban(guild, user)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Member Unbanned"
        field_names = [f.name for f in embed.fields]
        assert "Unbanned By" not in field_names

    @pytest.mark.asyncio
    async def test_timeout_audit_forbidden(self) -> None:
        """timeout audit log Forbidden でもログは送信される。"""
        cog = _make_cog()
        guild, ch = _make_guild()

        before = _make_member()
        before.guild = guild
        before.timed_out_until = None

        after = _make_member()
        after.guild = guild
        after.timed_out_until = datetime(2026, 3, 10, tzinfo=UTC)
        after.roles = before.roles
        after.nick = before.nick

        async def _forbidden_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            raise discord.Forbidden(MagicMock(), "")
            yield  # noqa: RET504

        guild.audit_logs = _forbidden_audit

        cog._cache[("789", "member_timeout")] = ["100"]

        await cog.on_member_update(before, after)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Member Timed Out"
        field_names = [f.name for f in embed.fields]
        assert "Timed Out By" not in field_names

    @pytest.mark.asyncio
    async def test_fetch_ban_not_found(self) -> None:
        """fetch_ban で NotFound でもログは送信される。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        user = MagicMock(spec=discord.User)
        user.id = 12345
        user.bot = False
        user.display_avatar = MagicMock()
        user.display_avatar.url = "https://cdn.example.com/avatar.png"

        async def _empty_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            return
            yield  # noqa: RET504

        guild.audit_logs = _empty_audit
        guild.fetch_ban = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))

        cog._cache[("789", "member_ban")] = ["100"]

        await cog.on_member_ban(guild, user)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Member Banned"
        reason_field = next(f for f in embed.fields if f.name == "Reason")
        assert reason_field.value == "No reason provided"


# ---------------------------------------------------------------------------
# TestNoConfigSkips
# ---------------------------------------------------------------------------


class TestNoConfigSkips:
    """設定なしでスキップされるテスト。"""

    @pytest.mark.asyncio
    async def test_role_change_no_config(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()

        role_a = MagicMock(spec=discord.Role)
        role_a.name = "RoleA"
        role_b = MagicMock(spec=discord.Role)
        role_b.name = "RoleB"

        before = _make_member()
        before.guild = guild
        before.roles = [role_a]

        after = _make_member()
        after.guild = guild
        after.roles = [role_a, role_b]
        after.nick = before.nick

        await cog.on_member_update(before, after)
        ch.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_nickname_change_no_config(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()

        before = _make_member()
        before.guild = guild
        before.nick = "Old"

        after = _make_member()
        after.guild = guild
        after.nick = "New"
        after.roles = before.roles

        await cog.on_member_update(before, after)
        ch.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_timeout_no_config(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()

        before = _make_member()
        before.guild = guild
        before.timed_out_until = None

        after = _make_member()
        after.guild = guild
        after.timed_out_until = datetime(2026, 3, 10, tzinfo=UTC)
        after.roles = before.roles
        after.nick = before.nick

        await cog.on_member_update(before, after)
        ch.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_member_ban_no_config(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        user = MagicMock(spec=discord.User)
        user.id = 12345
        user.bot = False

        await cog.on_member_ban(guild, user)
        ch.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_member_unban_no_config(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        user = MagicMock(spec=discord.User)
        user.id = 12345
        user.bot = False

        await cog.on_member_unban(guild, user)
        ch.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_channel_create_no_config(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        channel = MagicMock(spec=discord.TextChannel)
        channel.guild = guild

        await cog.on_guild_channel_create(channel)
        ch.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_voice_state_no_config(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        member = _make_member()
        member.guild = guild

        before = MagicMock(spec=discord.VoiceState)
        before.channel = None
        after = MagicMock(spec=discord.VoiceState)
        after.channel = MagicMock()
        after.channel.id = 200

        await cog.on_voice_state_update(member, before, after)
        ch.send.assert_not_called()


# ---------------------------------------------------------------------------
# TestCogLifecycle
# ---------------------------------------------------------------------------


class TestCogLifecycle:
    """cog_load / cog_unload / on_ready のテスト。"""

    @pytest.mark.asyncio
    async def test_cog_load_starts_task(self) -> None:
        cog = _make_cog()
        cog._sync_cache_task = MagicMock()
        await cog.cog_load()
        cog._sync_cache_task.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_cog_unload_cancels_task(self) -> None:
        cog = _make_cog()
        cog._sync_cache_task = MagicMock()
        await cog.cog_unload()
        cog._sync_cache_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_ready_refreshes_invite_cache(self) -> None:
        cog = _make_cog()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 789
        guild.invites = AsyncMock(return_value=[])
        cog.bot.guilds = [guild]
        await cog.on_ready()
        guild.invites.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_cache_task_handles_exception(self) -> None:
        """_sync_cache_task は例外を握りつぶす。"""
        cog = _make_cog()
        with patch.object(cog, "_refresh_cache", side_effect=RuntimeError("DB error")):
            # Should not raise
            await cog._sync_cache_task()

    @pytest.mark.asyncio
    async def test_setup_function(self) -> None:
        """setup 関数が Bot に cog を追加する。"""
        from src.cogs.eventlog import setup

        bot = MagicMock(spec=commands.Bot)
        bot.add_cog = AsyncMock()
        await setup(bot)
        bot.add_cog.assert_called_once()


# ---------------------------------------------------------------------------
# TestSendLogHTTPException
# ---------------------------------------------------------------------------


class TestSendLogHTTPException:
    """_send_log の HTTPException ハンドリング。"""

    @pytest.mark.asyncio
    async def test_handles_http_exception(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        ch.send = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "Server error")
        )

        cog._cache[("789", "message_delete")] = ["100"]
        embed = discord.Embed(title="Test")
        await cog._send_log(guild, "message_delete", embed)
        # No exception raised


# ---------------------------------------------------------------------------
# TestMessageEditEdgeCases
# ---------------------------------------------------------------------------


class TestMessageEditEdgeCases:
    """on_message_edit のエッジケース。"""

    @pytest.mark.asyncio
    async def test_empty_content(self) -> None:
        """空コンテンツは (empty) で表示される。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        before = _make_message(content="")
        after = _make_message(content="New content")
        before.content = ""
        after.content = "New content"
        before.guild = guild
        after.guild = guild

        cog._cache[("789", "message_edit")] = ["100"]

        await cog.on_message_edit(before, after)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.fields[2].value == "(empty)"

    @pytest.mark.asyncio
    async def test_long_content_truncated(self) -> None:
        """長い編集内容は切り詰められる。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        before = _make_message(content="x" * 2000)
        after = _make_message(content="y" * 2000)
        before.guild = guild
        after.guild = guild

        cog._cache[("789", "message_edit")] = ["100"]

        await cog.on_message_edit(before, after)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert len(embed.fields[2].value) <= 1024
        assert len(embed.fields[3].value) <= 1024

    @pytest.mark.asyncio
    async def test_no_jump_url(self) -> None:
        """jump_url がない場合は Jump フィールドなし。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        before = _make_message(content="Old")
        after = _make_message(content="New")
        after.jump_url = ""
        before.guild = guild
        after.guild = guild

        cog._cache[("789", "message_edit")] = ["100"]

        await cog.on_message_edit(before, after)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        field_names = [f.name for f in embed.fields]
        assert "Jump" not in field_names

    @pytest.mark.asyncio
    async def test_no_display_avatar(self) -> None:
        """display_avatar がない場合もエラーなし。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        before = _make_message(content="Old")
        after = _make_message(content="New")
        after.author.display_avatar = None
        before.guild = guild
        after.guild = guild

        cog._cache[("789", "message_edit")] = ["100"]

        await cog.on_message_edit(before, after)
        ch.send.assert_called_once()


# ---------------------------------------------------------------------------
# TestLeaveLogEdgeCases
# ---------------------------------------------------------------------------


class TestLeaveLogEdgeCases:
    """leave ログのエッジケース。"""

    @pytest.mark.asyncio
    async def test_no_joined_at(self) -> None:
        """joined_at がない場合は Joined At フィールドなし。"""
        cog = _make_cog()
        guild, ch = _make_guild()

        async def _empty_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            return
            yield  # noqa: RET504

        guild.audit_logs = _empty_audit
        member = _make_member()
        member.guild = guild
        member.joined_at = None

        cog._cache[("789", "member_leave")] = ["100"]

        await cog.on_member_remove(member)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        field_names = [f.name for f in embed.fields]
        assert "Joined At" not in field_names

    @pytest.mark.asyncio
    async def test_long_roles_truncated(self) -> None:
        """大量のロールは切り詰められる。"""
        cog = _make_cog()
        guild, ch = _make_guild()

        async def _empty_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            return
            yield  # noqa: RET504

        guild.audit_logs = _empty_audit
        member = _make_member()
        member.guild = guild
        # 大量のロールを追加
        roles = []
        for i in range(200):
            role = MagicMock(spec=discord.Role)
            role.name = f"VeryLongRoleName{i:03d}"
            role.mention = f"<@&{i}>"
            roles.append(role)
        member.roles = roles

        cog._cache[("789", "member_leave")] = ["100"]

        await cog.on_member_remove(member)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        roles_field = next(f for f in embed.fields if f.name == "Roles")
        assert len(roles_field.value) <= 1024

    @pytest.mark.asyncio
    async def test_no_display_avatar(self) -> None:
        """display_avatar がない場合もエラーなし。"""
        cog = _make_cog()
        guild, ch = _make_guild()

        async def _empty_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            return
            yield  # noqa: RET504

        guild.audit_logs = _empty_audit
        member = _make_member()
        member.guild = guild
        member.display_avatar = None

        cog._cache[("789", "member_leave")] = ["100"]

        await cog.on_member_remove(member)
        ch.send.assert_called_once()


# ---------------------------------------------------------------------------
# TestChannelWithCategory
# ---------------------------------------------------------------------------


class TestChannelWithCategory:
    """チャンネルにカテゴリがある場合のテスト。"""

    @pytest.mark.asyncio
    async def test_channel_create_with_category(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        channel = MagicMock(spec=discord.TextChannel)
        channel.guild = guild
        channel.name = "new-channel"
        channel.type = discord.ChannelType.text
        channel.category = MagicMock()
        channel.category.name = "General"

        cog._cache[("789", "channel_create")] = ["100"]

        await cog.on_guild_channel_create(channel)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Channel Created"
        field_names = [f.name for f in embed.fields]
        assert "Category" in field_names
        cat_field = next(f for f in embed.fields if f.name == "Category")
        assert cat_field.value == "General"

    @pytest.mark.asyncio
    async def test_channel_delete_with_category(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        channel = MagicMock(spec=discord.TextChannel)
        channel.guild = guild
        channel.name = "deleted-channel"
        channel.type = discord.ChannelType.text
        channel.category = MagicMock()
        channel.category.name = "Archive"

        cog._cache[("789", "channel_delete")] = ["100"]

        await cog.on_guild_channel_delete(channel)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Channel Deleted"
        field_names = [f.name for f in embed.fields]
        assert "Category" in field_names

    @pytest.mark.asyncio
    async def test_channel_delete_no_config(self) -> None:
        """設定なしでスキップ。"""
        cog = _make_cog()
        guild, ch = _make_guild()
        channel = MagicMock(spec=discord.TextChannel)
        channel.guild = guild

        await cog.on_guild_channel_delete(channel)
        ch.send.assert_not_called()


# ---------------------------------------------------------------------------
# TestDisplayAvatarBranches
# ---------------------------------------------------------------------------


class TestDisplayAvatarBranches:
    """display_avatar が None の場合のブランチテスト。"""

    @pytest.mark.asyncio
    async def test_member_join_no_avatar(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        guild.invites = AsyncMock(return_value=[])
        guild.vanity_invite = AsyncMock(return_value=None)
        member = _make_member()
        member.guild = guild
        member.display_avatar = None

        cog._cache[("789", "member_join")] = ["100"]
        await cog.on_member_join(member)
        ch.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_kick_no_avatar(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()

        entry = MagicMock()
        entry.target = MagicMock()
        entry.target.id = 12345
        entry.user = MagicMock()
        entry.user.id = 99999
        entry.reason = None
        entry.created_at = datetime.now(UTC)

        async def _kick_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            yield entry

        guild.audit_logs = _kick_audit
        member = _make_member()
        member.guild = guild
        member.display_avatar = None

        cog._cache[("789", "member_kick")] = ["100"]
        await cog.on_member_remove(member)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert embed.title == "Member Kicked"

    @pytest.mark.asyncio
    async def test_ban_no_avatar(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        user = MagicMock(spec=discord.User)
        user.id = 12345
        user.bot = False
        user.display_avatar = None

        async def _empty_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            return
            yield  # noqa: RET504

        guild.audit_logs = _empty_audit
        guild.fetch_ban = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))

        cog._cache[("789", "member_ban")] = ["100"]
        await cog.on_member_ban(guild, user)
        ch.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_unban_no_avatar(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        user = MagicMock(spec=discord.User)
        user.id = 12345
        user.bot = False
        user.display_avatar = None

        async def _empty_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            return
            yield  # noqa: RET504

        guild.audit_logs = _empty_audit

        cog._cache[("789", "member_unban")] = ["100"]
        await cog.on_member_unban(guild, user)
        ch.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_no_avatar(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()

        before = _make_member()
        before.guild = guild
        before.timed_out_until = None

        after = _make_member()
        after.guild = guild
        after.timed_out_until = datetime(2026, 3, 10, tzinfo=UTC)
        after.roles = before.roles
        after.nick = before.nick
        after.display_avatar = None

        async def _empty_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            return
            yield  # noqa: RET504

        guild.audit_logs = _empty_audit

        cog._cache[("789", "member_timeout")] = ["100"]
        await cog.on_member_update(before, after)
        ch.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_role_change_no_avatar(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()

        role_a = MagicMock(spec=discord.Role)
        role_a.name = "RoleA"
        role_a.mention = "<@&111>"
        role_b = MagicMock(spec=discord.Role)
        role_b.name = "RoleB"
        role_b.mention = "<@&222>"

        before = _make_member()
        before.guild = guild
        before.roles = [role_a]

        after = _make_member()
        after.guild = guild
        after.roles = [role_a, role_b]
        after.nick = before.nick
        after.display_avatar = None

        cog._cache[("789", "role_change")] = ["100"]
        await cog.on_member_update(before, after)
        ch.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_nickname_change_no_avatar(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()

        before = _make_member()
        before.guild = guild
        before.nick = "Old"

        after = _make_member()
        after.guild = guild
        after.nick = "New"
        after.roles = before.roles
        after.display_avatar = None

        cog._cache[("789", "nickname_change")] = ["100"]
        await cog.on_member_update(before, after)
        ch.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_voice_state_no_avatar(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        member = _make_member()
        member.guild = guild
        member.display_avatar = None

        before = MagicMock(spec=discord.VoiceState)
        before.channel = None
        after = MagicMock(spec=discord.VoiceState)
        after.channel = MagicMock()
        after.channel.id = 200

        cog._cache[("789", "voice_state")] = ["100"]
        await cog.on_voice_state_update(member, before, after)
        ch.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_message_delete_no_avatar(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        msg = _make_message()
        msg.guild = guild
        msg.author.display_avatar = None

        async def _empty_audit(*_a: object, **_kw: object):  # type: ignore[no-untyped-def]
            return
            yield  # noqa: RET504

        guild.audit_logs = _empty_audit

        cog._cache[("789", "message_delete")] = ["100"]
        await cog.on_message_delete(msg)
        ch.send.assert_called_once()


# ---------------------------------------------------------------------------
# TestVanityURLForbidden
# ---------------------------------------------------------------------------


class TestMessageEditNoConfig:
    """message_edit 設定なしでスキップ。"""

    @pytest.mark.asyncio
    async def test_skips_no_config(self) -> None:
        cog = _make_cog()
        before = _make_message(content="Old")
        after = _make_message(content="New")
        await cog.on_message_edit(before, after)


class TestMemberJoinNoConfig:
    """member_join 設定なしでスキップ。"""

    @pytest.mark.asyncio
    async def test_skips_no_config(self) -> None:
        cog = _make_cog()
        member = _make_member()
        await cog.on_member_join(member)


class TestRoleChangeRemovedRole:
    """ロール削除の検出テスト。"""

    @pytest.mark.asyncio
    async def test_removed_role(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()

        role_a = MagicMock(spec=discord.Role)
        role_a.name = "RoleA"
        role_a.mention = "<@&111>"
        role_b = MagicMock(spec=discord.Role)
        role_b.name = "RoleB"
        role_b.mention = "<@&222>"

        before = _make_member()
        before.guild = guild
        before.roles = [role_a, role_b]

        after = _make_member()
        after.guild = guild
        after.roles = [role_a]
        after.nick = before.nick

        cog._cache[("789", "role_change")] = ["100"]

        await cog.on_member_update(before, after)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert "× <@&222>" in embed.fields[1].value


class TestVanityURLForbidden:
    """vanity URL Forbidden のテスト。"""

    @pytest.mark.asyncio
    async def test_vanity_invite_forbidden(self) -> None:
        """vanity_invite が Forbidden でも None を返す。"""
        cog = _make_cog()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 789
        guild.invites = AsyncMock(return_value=[])
        guild.vanity_invite = AsyncMock(side_effect=discord.Forbidden(MagicMock(), ""))

        result = await cog._detect_used_invite(guild)
        assert result is None


# ===========================================================================
# Message Purge
# ===========================================================================


class TestOnBulkMessageDelete:
    """on_bulk_message_delete のテスト。"""

    @pytest.mark.asyncio
    async def test_logs_purge(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        cog._cache[("789", "message_purge")] = ["100"]

        msg1 = MagicMock(spec=discord.Message)
        msg1.guild = guild
        msg1.channel = MagicMock()
        msg1.channel.id = 555
        msg1.author = MagicMock()
        msg1.author.bot = False
        msg1.author.name = "user1"

        msg2 = MagicMock(spec=discord.Message)
        msg2.guild = guild
        msg2.channel = msg1.channel
        msg2.author = MagicMock()
        msg2.author.bot = False
        msg2.author.name = "user2"

        await cog.on_bulk_message_delete([msg1, msg2])
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert "Purged" in embed.title

    @pytest.mark.asyncio
    async def test_skips_empty(self) -> None:
        cog = _make_cog()
        await cog.on_bulk_message_delete([])

    @pytest.mark.asyncio
    async def test_skips_no_config(self) -> None:
        cog = _make_cog()
        msg = MagicMock(spec=discord.Message)
        msg.guild = MagicMock()
        msg.guild.id = 789
        msg.channel = MagicMock()
        msg.author = MagicMock()
        msg.author.bot = False
        await cog.on_bulk_message_delete([msg])


# ===========================================================================
# Channel Update
# ===========================================================================


class TestOnGuildChannelUpdate:
    """on_guild_channel_update のテスト。"""

    @pytest.mark.asyncio
    async def test_logs_name_change(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        cog._cache[("789", "channel_update")] = ["100"]

        before = MagicMock(spec=discord.TextChannel)
        before.name = "old-name"
        before.guild = guild

        after = MagicMock(spec=discord.TextChannel)
        after.name = "new-name"
        after.guild = guild
        after.id = 555

        await cog.on_guild_channel_update(before, after)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert "Updated" in embed.title

    @pytest.mark.asyncio
    async def test_skips_no_changes(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        cog._cache[("789", "channel_update")] = ["100"]

        before = MagicMock(spec=discord.TextChannel)
        before.name = "same"
        before.topic = "topic"
        before.slowmode_delay = 0
        before.nsfw = False
        before.guild = guild
        after = MagicMock(spec=discord.TextChannel)
        after.name = "same"
        after.topic = "topic"
        after.slowmode_delay = 0
        after.nsfw = False
        after.guild = guild

        await cog.on_guild_channel_update(before, after)
        ch.send.assert_not_called()


# ===========================================================================
# Role Create / Delete / Update
# ===========================================================================


class TestOnGuildRoleCreate:
    @pytest.mark.asyncio
    async def test_logs_role_create(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        cog._cache[("789", "role_create")] = ["100"]

        role = MagicMock(spec=discord.Role)
        role.guild = guild
        role.name = "NewRole"
        role.mention = "@NewRole"
        role.color = MagicMock()
        role.color.value = 0xFF0000

        await cog.on_guild_role_create(role)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert "Created" in embed.title


class TestOnGuildRoleDelete:
    @pytest.mark.asyncio
    async def test_logs_role_delete(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        cog._cache[("789", "role_delete")] = ["100"]

        role = MagicMock(spec=discord.Role)
        role.guild = guild
        role.name = "OldRole"
        role.color = MagicMock()
        role.color.value = 0
        role.members = []

        await cog.on_guild_role_delete(role)
        ch.send.assert_called_once()


class TestOnGuildRoleUpdate:
    @pytest.mark.asyncio
    async def test_logs_name_change(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        cog._cache[("789", "role_update")] = ["100"]

        before = MagicMock(spec=discord.Role)
        before.name = "OldName"
        before.color = MagicMock()
        before.color.value = 0
        before.hoist = False
        before.mentionable = False
        before.permissions = MagicMock()
        before.guild = guild

        after = MagicMock(spec=discord.Role)
        after.name = "NewName"
        after.color = before.color
        after.hoist = False
        after.mentionable = False
        after.permissions = before.permissions
        after.guild = guild
        after.mention = "@NewName"

        await cog.on_guild_role_update(before, after)
        ch.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_no_changes(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        cog._cache[("789", "role_update")] = ["100"]

        role = MagicMock(spec=discord.Role)
        role.name = "Same"
        role.color = MagicMock()
        role.color.value = 0
        role.hoist = False
        role.mentionable = False
        role.permissions = MagicMock()
        role.guild = guild
        role.mention = "@Same"

        await cog.on_guild_role_update(role, role)
        ch.send.assert_not_called()


# ===========================================================================
# Invite Create / Delete (with logging)
# ===========================================================================


class TestInviteCreateLog:
    @pytest.mark.asyncio
    async def test_logs_invite_create(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        cog._cache[("789", "invite_create")] = ["100"]
        cog.bot.get_guild = MagicMock(return_value=guild)

        invite = MagicMock(spec=discord.Invite)
        invite.guild = MagicMock()
        invite.guild.id = 789
        invite.code = "abc123"
        invite.uses = 0
        invite.inviter = MagicMock()
        invite.inviter.id = 11111
        invite.inviter.name = "inviter"
        invite.channel = MagicMock()
        invite.channel.id = 222
        invite.max_age = 3600
        invite.max_uses = 10

        await cog.on_invite_create(invite)
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert "Created" in embed.title


class TestInviteDeleteLog:
    @pytest.mark.asyncio
    async def test_logs_invite_delete(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        cog._cache[("789", "invite_delete")] = ["100"]
        cog.bot.get_guild = MagicMock(return_value=guild)

        invite = MagicMock(spec=discord.Invite)
        invite.guild = MagicMock()
        invite.guild.id = 789
        invite.code = "abc123"
        invite.channel = MagicMock()
        invite.channel.id = 222

        await cog.on_invite_delete(invite)
        ch.send.assert_called_once()


# ===========================================================================
# Thread Create / Delete / Update
# ===========================================================================


class TestOnThreadCreate:
    @pytest.mark.asyncio
    async def test_logs_thread_create(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        cog._cache[("789", "thread_create")] = ["100"]

        thread = MagicMock(spec=discord.Thread)
        thread.guild = guild
        thread.name = "new-thread"
        thread.parent = MagicMock()
        thread.parent.id = 555
        thread.owner = MagicMock()
        thread.owner.id = 11111
        thread.owner.name = "creator"

        await cog.on_thread_create(thread)
        ch.send.assert_called_once()


class TestOnThreadDelete:
    @pytest.mark.asyncio
    async def test_logs_thread_delete(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        cog._cache[("789", "thread_delete")] = ["100"]

        thread = MagicMock(spec=discord.Thread)
        thread.guild = guild
        thread.name = "old-thread"
        thread.parent = MagicMock()
        thread.parent.id = 555

        await cog.on_thread_delete(thread)
        ch.send.assert_called_once()


class TestOnThreadUpdate:
    @pytest.mark.asyncio
    async def test_logs_name_change(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        cog._cache[("789", "thread_update")] = ["100"]

        before = MagicMock(spec=discord.Thread)
        before.name = "old"
        before.archived = False
        before.locked = False
        before.slowmode_delay = 0
        before.guild = guild

        after = MagicMock(spec=discord.Thread)
        after.name = "new"
        after.archived = False
        after.locked = False
        after.slowmode_delay = 0
        after.guild = guild
        after.id = 666

        await cog.on_thread_update(before, after)
        ch.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_no_changes(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        cog._cache[("789", "thread_update")] = ["100"]

        thread = MagicMock(spec=discord.Thread)
        thread.name = "same"
        thread.archived = False
        thread.locked = False
        thread.slowmode_delay = 0
        thread.guild = guild

        await cog.on_thread_update(thread, thread)
        ch.send.assert_not_called()


# ===========================================================================
# Server Update
# ===========================================================================


class TestOnGuildUpdate:
    @pytest.mark.asyncio
    async def test_logs_name_change(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        cog._cache[("789", "server_update")] = ["100"]

        before = MagicMock(spec=discord.Guild)
        before.id = 789
        before.name = "Old Server"
        before.icon = None
        before.banner = None
        before.description = None
        before.verification_level = MagicMock()
        before.verification_level.name = "low"
        before.default_notifications = MagicMock()
        before.default_notifications.name = "all"
        before.afk_channel = None
        before.system_channel = None

        after = MagicMock(spec=discord.Guild)
        after.id = 789
        after.name = "New Server"
        after.icon = None
        after.banner = None
        after.description = None
        after.verification_level = before.verification_level
        after.default_notifications = before.default_notifications
        after.afk_channel = None
        after.system_channel = None
        after.get_channel = guild.get_channel

        await cog.on_guild_update(before, after)
        ch.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_no_changes(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        cog._cache[("789", "server_update")] = ["100"]

        g = MagicMock(spec=discord.Guild)
        g.id = 789
        g.name = "Same"
        g.icon = None
        g.banner = None
        g.description = None
        g.verification_level = MagicMock()
        g.default_notifications = MagicMock()
        g.afk_channel = None
        g.system_channel = None
        g.get_channel = guild.get_channel

        await cog.on_guild_update(g, g)
        ch.send.assert_not_called()


# ===========================================================================
# Emoji Update
# ===========================================================================


class TestOnGuildEmojisUpdate:
    @pytest.mark.asyncio
    async def test_logs_emoji_added(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        cog._cache[("789", "emoji_update")] = ["100"]

        emoji = MagicMock(spec=discord.Emoji)
        emoji.id = 1
        emoji.name = "pepe"

        await cog.on_guild_emojis_update(guild, (), (emoji,))
        ch.send.assert_called_once()
        embed = ch.send.call_args.kwargs["embed"]
        assert "Updated" in embed.title

    @pytest.mark.asyncio
    async def test_logs_emoji_removed(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        cog._cache[("789", "emoji_update")] = ["100"]

        emoji = MagicMock(spec=discord.Emoji)
        emoji.id = 1
        emoji.name = "pepe"

        await cog.on_guild_emojis_update(guild, (emoji,), ())
        ch.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_no_changes(self) -> None:
        cog = _make_cog()
        guild, ch = _make_guild()
        cog._cache[("789", "emoji_update")] = ["100"]

        emoji = MagicMock(spec=discord.Emoji)
        emoji.id = 1
        emoji.name = "same"

        await cog.on_guild_emojis_update(guild, (emoji,), (emoji,))
        ch.send.assert_not_called()
