"""Discord event log embeds matching kakuzato-bot's presentation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Protocol

import discord

from src.cogs._eventlog_helpers import create_event_embed, truncate_content

_JST = timezone(timedelta(hours=9))
_BACKTICK = chr(96)
_URL_PATTERN = re.compile(r"https?://\S+")
_USER_MENTION_PATTERN = re.compile(r"<@!?\d+>")
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".svg")


@dataclass(frozen=True, slots=True)
class InviteDetails:
    """Invite information displayed on a member-join log."""

    kind: str
    code: str | None = None
    inviter_id: int | None = None
    inviter_total_uses: int | None = None
    uses: int | None = None


class _ChannelLike(Protocol):
    id: int


def _inline_code(value: object) -> str:
    return f"{_BACKTICK}{str(value).replace(_BACKTICK, '')}{_BACKTICK}"


def _code_block(value: str | None, fallback: str, max_len: int = 1000) -> str:
    content = value if value else fallback
    content = content.replace(_BACKTICK * 3, f"{_BACKTICK} {_BACKTICK} {_BACKTICK}")
    return f"{_BACKTICK * 3}text\n{truncate_content(content, max_len)}\n{_BACKTICK * 3}"


def _format_jst(dt: datetime) -> str:
    return f"{dt.astimezone(_JST):%Y/%m/%d %H:%M:%S} JST"


def _format_timestamp(dt: datetime | None) -> str:
    if not isinstance(dt, datetime):
        return "不明"
    return f"{_format_jst(dt)} (<t:{int(dt.timestamp())}:R>)"


def _format_user(user: discord.User | discord.Member | None) -> str:
    if user is None:
        return "不明"
    tag = str(user)
    if tag.startswith("<MagicMock") or tag.startswith("<AsyncMock"):
        tag = user.name
    return f"<@{user.id}> ({tag})\nID: {_inline_code(user.id)}"


def _format_channel(channel: _ChannelLike | None) -> str:
    if channel is None:
        return "不明"
    return f"<#{channel.id}>\nID: {_inline_code(channel.id)}"


def _format_boolean(value: bool) -> str:
    return "はい" if value else "いいえ"


def _format_bytes(size: object) -> str:
    if not isinstance(size, int):
        size = 0
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.2f} MiB"
    if size >= 1024:
        return f"{size / 1024:.2f} KiB"
    return f"{size} B"


def _format_attachment(attachment: discord.Attachment) -> str:
    filename = attachment.filename
    if not isinstance(filename, str):
        filename = "attachment"
    label = filename.replace("[", r"\[").replace("]", r"\]")
    return f"[{label}]({attachment.url}) ({_format_bytes(attachment.size)})"


def _format_attachment_metadata(attachment: discord.Attachment) -> str:
    dimensions = ""
    if isinstance(attachment.width, int) and isinstance(attachment.height, int):
        dimensions = f", {attachment.width}x{attachment.height}"
    filename = attachment.filename
    if not isinstance(filename, str):
        filename = "attachment"
    attachment_id = attachment.id if isinstance(attachment.id, int) else "unknown"
    content_type = attachment.content_type
    if not isinstance(content_type, str):
        content_type = "unknown"
    return (
        f"{filename}: ID={attachment_id}, "
        f"type={content_type}, "
        f"size={_format_bytes(attachment.size)}{dimensions}"
    )


def _is_image_attachment(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    filename = attachment.filename if isinstance(attachment.filename, str) else ""
    return content_type.startswith("image/") or filename.lower().endswith(
        _IMAGE_EXTENSIONS
    )


def _add_audit_fields(
    embed: discord.Embed,
    actor_id: int | None,
    reason: str | None,
    *,
    actor_label: str,
    show_unknown: bool = False,
) -> None:
    if actor_id is not None:
        actor = f"<@{actor_id}>\nID: {_inline_code(actor_id)}"
        embed.add_field(name=actor_label, value=actor, inline=True)
    elif show_unknown:
        embed.add_field(
            name=actor_label,
            value="不明 (Audit Log 取得不可)",
            inline=True,
        )
    embed.add_field(
        name="理由",
        value=_code_block(reason, "なし / 取得不可", 900),
        inline=False,
    )


def message_deleted_embed(
    message: discord.Message,
    actor_id: int | None,
    reason: str | None,
) -> discord.Embed:
    embed = create_event_embed("メッセージ削除", "message_delete")
    embed.add_field(name="投稿者", value=_format_user(message.author), inline=True)
    embed.add_field(
        name="チャンネル", value=_format_channel(message.channel), inline=True
    )
    embed.add_field(name="メッセージID", value=_inline_code(message.id), inline=True)
    embed.add_field(
        name="投稿日時", value=_format_timestamp(message.created_at), inline=True
    )
    embed.add_field(
        name="本文",
        value=_code_block(message.content, "(本文なし / 取得不可)"),
        inline=False,
    )
    _add_audit_fields(
        embed,
        actor_id,
        reason,
        actor_label="削除した人",
        show_unknown=True,
    )
    attachments = list(message.attachments)
    if attachments:
        embed.add_field(
            name="添付ファイル",
            value=truncate_content("\n".join(map(_format_attachment, attachments))),
            inline=False,
        )
        embed.add_field(
            name="添付メタデータ",
            value=truncate_content(
                "\n".join(map(_format_attachment_metadata, attachments))
            ),
            inline=False,
        )
        first_image = next(
            (item for item in attachments if _is_image_attachment(item)), None
        )
        if first_image is not None:
            embed.set_image(url=first_image.url)
    if message.author.display_avatar:
        embed.set_thumbnail(url=message.author.display_avatar.url)
    return embed


def messages_purged_embed(
    messages: list[discord.Message],
    actor_id: int | None,
    reason: str | None,
) -> discord.Embed:
    channel = messages[0].channel
    authors = list(dict.fromkeys(str(message.author) for message in messages))
    embed = create_event_embed("メッセージ一括削除", "message_purge")
    embed.add_field(name="チャンネル", value=_format_channel(channel), inline=True)
    embed.add_field(name="削除数", value=str(len(messages)), inline=True)
    embed.add_field(
        name="投稿者",
        value=truncate_content(", ".join(authors)) if authors else "不明",
        inline=False,
    )
    embed.add_field(
        name="メッセージID",
        value=truncate_content(", ".join(_inline_code(item.id) for item in messages)),
        inline=False,
    )
    created = [
        item.created_at for item in messages if isinstance(item.created_at, datetime)
    ]
    if created:
        embed.add_field(
            name="投稿日時範囲",
            value=(
                f"{_format_timestamp(min(created))} - {_format_timestamp(max(created))}"
            ),
            inline=False,
        )
    _add_audit_fields(
        embed,
        actor_id,
        reason,
        actor_label="削除した人",
        show_unknown=True,
    )
    return embed


def message_edited_embed(
    before: discord.Message,
    after: discord.Message,
) -> discord.Embed | None:
    before_urls = {item.url for item in before.attachments}
    after_urls = {item.url for item in after.attachments}
    if before.content == after.content and before_urls == after_urls:
        return None

    embed = create_event_embed("メッセージ編集", "message_edit")
    embed.add_field(name="投稿者", value=_format_user(after.author), inline=True)
    embed.add_field(
        name="チャンネル", value=_format_channel(after.channel), inline=True
    )
    embed.add_field(name="メッセージID", value=_inline_code(after.id), inline=True)
    embed.add_field(
        name="投稿日時", value=_format_timestamp(after.created_at), inline=True
    )
    embed.add_field(
        name="編集日時",
        value=_format_timestamp(after.edited_at or datetime.now(UTC)),
        inline=True,
    )
    embed.add_field(
        name="編集前",
        value=_code_block(before.content, "(本文なし / 取得不可)"),
        inline=False,
    )
    embed.add_field(
        name="編集後",
        value=_code_block(after.content, "(本文なし / 取得不可)"),
        inline=False,
    )
    _add_set_changes(embed, "URL変更", _URL_PATTERN, before.content, after.content)
    _add_set_changes(
        embed,
        "メンション変更",
        _USER_MENTION_PATTERN,
        before.content,
        after.content,
    )
    added = [item for item in after.attachments if item.url not in before_urls]
    removed = [item for item in before.attachments if item.url not in after_urls]
    changes = [
        *[f"+ {_format_attachment(item)}" for item in added],
        *[f"- {_format_attachment(item)}" for item in removed],
    ]
    if changes:
        embed.add_field(
            name="添付ファイル変更",
            value=truncate_content("\n".join(changes)),
            inline=False,
        )
    if after.jump_url:
        embed.add_field(
            name="ジャンプ",
            value=f"[メッセージを開く]({after.jump_url})",
            inline=False,
        )
    if after.author.display_avatar:
        embed.set_thumbnail(url=after.author.display_avatar.url)
    return embed


def _add_set_changes(
    embed: discord.Embed,
    label: str,
    pattern: re.Pattern[str],
    before: str | None,
    after: str | None,
) -> None:
    before_values = set(pattern.findall(before or ""))
    after_values = set(pattern.findall(after or ""))
    lines = [
        *[f"+ {item}" for item in sorted(after_values - before_values)],
        *[f"- {item}" for item in sorted(before_values - after_values)],
    ]
    if lines:
        embed.add_field(
            name=label, value=truncate_content("\n".join(lines)), inline=False
        )


def member_joined_embed(
    member: discord.Member, invite: InviteDetails | None
) -> discord.Embed:
    age_days = (datetime.now(UTC) - member.created_at).days
    joined_at = member.joined_at or datetime.now(UTC)
    embed = create_event_embed("メンバー参加", "member_join")
    embed.add_field(name="ユーザー", value=_format_user(member), inline=True)
    embed.add_field(
        name="アカウント作成", value=_format_timestamp(member.created_at), inline=True
    )
    embed.add_field(name="アカウント年齢", value=f"{age_days}日", inline=True)
    embed.add_field(name="参加日時", value=_format_timestamp(joined_at), inline=True)
    embed.add_field(
        name="現在のメンバー数", value=str(member.guild.member_count), inline=True
    )
    if invite is not None:
        _add_invite_details(embed, invite)
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    return embed


def _add_invite_details(embed: discord.Embed, invite: InviteDetails) -> None:
    if invite.kind == "vanity":
        value = (
            f"Vanity URL ({_inline_code(invite.code)})" if invite.code else "Vanity URL"
        )
        embed.add_field(name="参加元", value=value, inline=True)
        if invite.uses is not None:
            embed.add_field(
                name="Vanity URL使用回数", value=str(invite.uses), inline=True
            )
        return
    embed.add_field(
        name="招待コード", value=_inline_code(invite.code or ""), inline=True
    )
    inviter = (
        f"<@{invite.inviter_id}>\nID: {_inline_code(invite.inviter_id)}"
        if invite.inviter_id is not None
        else "不明"
    )
    embed.add_field(name="招待作成者", value=inviter, inline=True)
    if invite.inviter_total_uses is not None:
        embed.add_field(
            name="作成者の招待使用回数",
            value=str(invite.inviter_total_uses),
            inline=True,
        )


def member_left_embed(member: discord.Member) -> discord.Embed:
    roles = ", ".join(
        f"{role.mention} ({role.name})"
        for role in member.roles
        if role.id != member.guild.id and role.name != "@everyone"
    )
    embed = create_event_embed("メンバー退出", "member_leave")
    embed.add_field(name="ユーザー", value=_format_user(member), inline=True)
    embed.add_field(
        name="参加日時", value=_format_timestamp(member.joined_at), inline=True
    )
    embed.add_field(
        name="保持していたロール",
        value=truncate_content(roles or "なし"),
        inline=False,
    )
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    return embed


def moderated_member_embed(
    title: str,
    event_type: str,
    member: discord.User | discord.Member,
    actor_id: int | None,
    reason: str | None,
    *,
    until: datetime | None = None,
) -> discord.Embed:
    embed = create_event_embed(title, event_type)
    embed.add_field(name="対象ユーザー", value=_format_user(member), inline=True)
    if until is not None:
        embed.add_field(name="期限", value=_format_timestamp(until), inline=True)
    _add_audit_fields(embed, actor_id, reason, actor_label="実行者", show_unknown=True)
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    return embed


def member_roles_changed_embed(
    before: discord.Member,
    after: discord.Member,
    actor_id: int | None,
    reason: str | None,
) -> discord.Embed | None:
    before_ids = {role.id for role in before.roles}
    after_ids = {role.id for role in after.roles}
    added = [
        role
        for role in after.roles
        if role.id not in before_ids and role.id != after.guild.id
    ]
    removed = [
        role
        for role in before.roles
        if role.id not in after_ids and role.id != after.guild.id
    ]
    if not added and not removed:
        return None
    changes = [
        *[f"+ {role.mention} ({role.name}) ID: {role.id}" for role in added],
        *[f"- {role.mention} ({role.name}) ID: {role.id}" for role in removed],
    ]
    embed = create_event_embed("メンバーロール変更", "role_change")
    embed.add_field(name="対象ユーザー", value=_format_user(after), inline=True)
    embed.add_field(
        name="変更内容", value=truncate_content("\n".join(changes)), inline=False
    )
    _add_audit_fields(embed, actor_id, reason, actor_label="実行者", show_unknown=True)
    if after.display_avatar:
        embed.set_thumbnail(url=after.display_avatar.url)
    return embed


def nickname_changed_embed(
    before: discord.Member,
    after: discord.Member,
    actor_id: int | None,
    reason: str | None,
) -> discord.Embed | None:
    if before.nick == after.nick:
        return None
    embed = create_event_embed("ニックネーム変更", "nickname_change")
    embed.add_field(name="対象ユーザー", value=_format_user(after), inline=True)
    embed.add_field(name="変更前", value=before.nick or "(なし)", inline=True)
    embed.add_field(name="変更後", value=after.nick or "(なし)", inline=True)
    _add_audit_fields(embed, actor_id, reason, actor_label="実行者")
    if after.display_avatar:
        embed.set_thumbnail(url=after.display_avatar.url)
    return embed


_CHANNEL_TYPE_LABELS: dict[discord.ChannelType, str] = {
    discord.ChannelType.text: "テキスト",
    discord.ChannelType.news: "アナウンス",
    discord.ChannelType.voice: "ボイス",
    discord.ChannelType.stage_voice: "ステージ",
    discord.ChannelType.category: "カテゴリ",
    discord.ChannelType.forum: "フォーラム",
    discord.ChannelType.media: "メディア",
}


def _format_channel_type(channel_type: discord.ChannelType) -> str:
    return _CHANNEL_TYPE_LABELS.get(channel_type, f"不明 ({channel_type.value})")


def channel_embed(
    title: str,
    event_type: str,
    channel: discord.abc.GuildChannel,
    actor_id: int | None,
    reason: str | None,
) -> discord.Embed:
    embed = create_event_embed(title, event_type)
    embed.add_field(name="チャンネル", value=_format_channel(channel), inline=True)
    embed.add_field(name="種別", value=_format_channel_type(channel.type), inline=True)
    embed.add_field(
        name="作成日時", value=_format_timestamp(channel.created_at), inline=True
    )
    topic = getattr(channel, "topic", None)
    if isinstance(topic, str) and topic:
        embed.add_field(
            name="トピック", value=_code_block(topic, "(なし)"), inline=False
        )
    _add_audit_fields(embed, actor_id, reason, actor_label="実行者", show_unknown=True)
    return embed


def _push_change(changes: list[str], label: str, before: object, after: object) -> None:
    before_text = _format_change_value(before)
    after_text = _format_change_value(after)
    if before_text != after_text:
        changes.append(f"**{label}:** {before_text} -> {after_text}")


def _format_change_value(value: object) -> str:
    if value is None or value == "":
        return "(なし)"
    if isinstance(value, bool):
        return _format_boolean(value)
    return str(value)


def _format_bitrate(value: object) -> str:
    return (
        f"{round(value / 1000)} kbps" if isinstance(value, int) and value else "(なし)"
    )


def _format_user_limit(value: object) -> str:
    if not isinstance(value, int):
        return "(なし)"
    return "無制限" if value == 0 else f"{value}人"


def channel_updated_embed(
    before: discord.abc.GuildChannel,
    after: discord.abc.GuildChannel,
    actor_id: int | None,
    reason: str | None,
) -> discord.Embed | None:
    changes: list[str] = []
    _push_change(changes, "名前", before.name, after.name)
    _push_change(
        changes,
        "トピック",
        getattr(before, "topic", None),
        getattr(after, "topic", None),
    )
    _push_change(
        changes,
        "低速モード",
        f"{getattr(before, 'slowmode_delay', 0)}s",
        f"{getattr(after, 'slowmode_delay', 0)}s",
    )
    _push_change(
        changes,
        "NSFW",
        _format_boolean(bool(getattr(before, "nsfw", False))),
        _format_boolean(bool(getattr(after, "nsfw", False))),
    )
    _push_change(
        changes,
        "カテゴリ",
        getattr(getattr(before, "category", None), "name", None),
        getattr(getattr(after, "category", None), "name", None),
    )
    _push_change(
        changes,
        "Bitrate",
        _format_bitrate(getattr(before, "bitrate", None)),
        _format_bitrate(getattr(after, "bitrate", None)),
    )
    _push_change(
        changes,
        "人数上限",
        _format_user_limit(getattr(before, "user_limit", None)),
        _format_user_limit(getattr(after, "user_limit", None)),
    )
    before_overwrites = _format_permission_overwrites(before)
    after_overwrites = _format_permission_overwrites(after)
    overwrite_changed = before_overwrites != after_overwrites
    if overwrite_changed:
        changes.append("**権限上書き:** 変更あり")
    if not changes:
        return None
    embed = create_event_embed("チャンネル更新", "channel_update")
    embed.add_field(name="チャンネル", value=_format_channel(after), inline=True)
    embed.add_field(name="種別", value=_format_channel_type(after.type), inline=True)
    embed.add_field(
        name="変更内容", value=truncate_content("\n".join(changes)), inline=False
    )
    if overwrite_changed and after_overwrites:
        embed.add_field(
            name="権限上書き (変更後)",
            value=truncate_content(after_overwrites),
            inline=False,
        )
    _add_audit_fields(embed, actor_id, reason, actor_label="実行者", show_unknown=True)
    return embed


_PERMISSION_LABELS = {
    "create_instant_invite": "招待を作成",
    "kick_members": "メンバーをキック",
    "ban_members": "メンバーをBAN",
    "administrator": "管理者",
    "manage_channels": "チャンネル管理",
    "manage_guild": "サーバー管理",
    "add_reactions": "リアクションを追加",
    "view_audit_log": "監査ログを表示",
    "priority_speaker": "優先スピーカー",
    "stream": "配信",
    "read_messages": "チャンネルを見る",
    "view_channel": "チャンネルを見る",
    "send_messages": "メッセージを送信",
    "send_tts_messages": "TTSメッセージを送信",
    "manage_messages": "メッセージ管理",
    "embed_links": "埋め込みリンク",
    "attach_files": "ファイル添付",
    "read_message_history": "メッセージ履歴を読む",
    "mention_everyone": "@everyone/@here",
    "external_emojis": "外部絵文字を使用",
    "view_guild_insights": "サーバーインサイトを表示",
    "connect": "ボイス接続",
    "speak": "発言",
    "mute_members": "メンバーをミュート",
    "deafen_members": "メンバーのスピーカーをミュート",
    "move_members": "メンバーを移動",
    "use_voice_activation": "音声検出を使用",
    "change_nickname": "ニックネーム変更",
    "manage_nicknames": "ニックネーム管理",
    "manage_roles": "ロール管理",
    "manage_webhooks": "Webhook管理",
    "manage_expressions": "絵文字/スタンプ/サウンド管理",
    "manage_emojis_and_stickers": "絵文字とスタンプ管理",
    "use_application_commands": "アプリコマンドを使用",
    "request_to_speak": "スピーカー参加をリクエスト",
    "manage_events": "イベント管理",
    "manage_threads": "スレッド管理",
    "create_public_threads": "公開スレッド作成",
    "create_private_threads": "プライベートスレッド作成",
    "external_stickers": "外部スタンプを使用",
    "send_messages_in_threads": "スレッドでメッセージ送信",
    "use_embedded_activities": "アクティビティを使用",
    "moderate_members": "メンバーをタイムアウト",
    "view_creator_monetization_analytics": "収益化分析を表示",
    "use_soundboard": "サウンドボードを使用",
    "create_expressions": "絵文字/スタンプ/サウンド作成",
    "create_events": "イベント作成",
    "use_external_sounds": "外部サウンドを使用",
    "send_voice_messages": "ボイスメッセージ送信",
    "set_voice_channel_status": "ボイスチャンネルステータス設定",
    "send_polls": "投票を送信",
    "use_external_apps": "外部アプリを使用",
}


def _format_permissions(permissions: object) -> str:
    if not isinstance(permissions, discord.Permissions):
        return "不明"
    names = [
        _PERMISSION_LABELS.get(name, name) for name, enabled in permissions if enabled
    ]
    if names:
        return ", ".join(names)
    if permissions.value == 0:
        return "なし"
    return f"不明な権限 (bitfield: {_inline_code(permissions.value)})"


def _format_permission_overwrites(channel: discord.abc.GuildChannel) -> str | None:
    overwrites = channel.overwrites
    if not overwrites:
        return None
    lines: list[str] = []
    for target, overwrite in overwrites.items():
        allow, deny = overwrite.pair()
        if isinstance(target, discord.Role):
            target_text = (
                f"{target.mention} ({target.name}, ロール, "
                f"ID: {_inline_code(target.id)})"
            )
        elif isinstance(target, discord.Member):
            target_text = (
                f"<@{target.id}> ({target}, メンバー, ID: {_inline_code(target.id)})"
            )
        else:
            target_text = f"{_inline_code(target.id)} (種別不明)"
        lines.append(
            f"- 対象: {target_text} / 許可: {_format_permissions(allow)} / "
            f"拒否: {_format_permissions(deny)}"
        )
    return "\n".join(lines)


def role_embed(
    title: str,
    event_type: str,
    role: discord.Role,
    actor_id: int | None,
    reason: str | None,
) -> discord.Embed:
    embed = create_event_embed(title, event_type)
    embed.add_field(
        name="ロール",
        value=f"{role.mention} ({role.name})\nID: {_inline_code(role.id)}",
        inline=True,
    )
    embed.add_field(name="色", value=f"#{role.color.value:06x}", inline=True)
    embed.add_field(
        name="作成日時", value=_format_timestamp(role.created_at), inline=True
    )
    embed.add_field(
        name="設定",
        value=(
            f"表示分離: {_format_boolean(role.hoist)} / "
            f"メンション可能: {_format_boolean(role.mentionable)}"
        ),
        inline=False,
    )
    embed.add_field(
        name="権限",
        value=truncate_content(_format_permissions(role.permissions)),
        inline=False,
    )
    _add_audit_fields(embed, actor_id, reason, actor_label="実行者", show_unknown=True)
    return embed


def role_updated_embed(
    before: discord.Role,
    after: discord.Role,
    actor_id: int | None,
    reason: str | None,
) -> discord.Embed | None:
    changes: list[str] = []
    _push_change(changes, "名前", before.name, after.name)
    _push_change(
        changes, "色", f"#{before.color.value:06x}", f"#{after.color.value:06x}"
    )
    _push_change(
        changes, "表示分離", _format_boolean(before.hoist), _format_boolean(after.hoist)
    )
    _push_change(
        changes,
        "メンション可能",
        _format_boolean(before.mentionable),
        _format_boolean(after.mentionable),
    )
    if before.permissions != after.permissions:
        added = [
            _PERMISSION_LABELS.get(name, name)
            for name, enabled in after.permissions
            if enabled and not getattr(before.permissions, name)
        ]
        removed = [
            _PERMISSION_LABELS.get(name, name)
            for name, enabled in before.permissions
            if enabled and not getattr(after.permissions, name)
        ]
        lines = []
        if added:
            lines.append(f"+ {', '.join(added)}")
        if removed:
            lines.append(f"- {', '.join(removed)}")
        changes.append(f"**権限:**\n{'\n'.join(lines)}")
    if not changes:
        return None
    embed = create_event_embed("ロール更新", "role_update")
    embed.add_field(
        name="ロール",
        value=f"{after.mention} ({after.name})\nID: {_inline_code(after.id)}",
        inline=True,
    )
    embed.add_field(
        name="変更内容", value=truncate_content("\n".join(changes)), inline=False
    )
    _add_audit_fields(embed, actor_id, reason, actor_label="実行者", show_unknown=True)
    return embed


def voice_state_embed(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> discord.Embed | None:
    if before.channel == after.channel:
        return None
    if member.bot:
        return None
    if before.channel is None and after.channel is not None:
        embed = create_event_embed("ボイス参加", "voice_state")
        embed.add_field(name="ユーザー", value=_format_user(member), inline=True)
        embed.add_field(
            name="参加先", value=_format_channel(after.channel), inline=True
        )
        embed.add_field(
            name="現在人数", value=str(len(after.channel.members)), inline=True
        )
        return embed
    if before.channel is not None and after.channel is None:
        embed = create_event_embed("ボイス退出", "voice_state")
        embed.add_field(name="ユーザー", value=_format_user(member), inline=True)
        embed.add_field(
            name="退出元", value=_format_channel(before.channel), inline=True
        )
        embed.add_field(
            name="現在人数", value=str(len(before.channel.members)), inline=True
        )
        return embed
    if before.channel is not None and after.channel is not None:
        embed = create_event_embed("ボイス移動", "voice_state")
        embed.add_field(name="ユーザー", value=_format_user(member), inline=True)
        embed.add_field(
            name="移動元", value=_format_channel(before.channel), inline=True
        )
        embed.add_field(
            name="移動先", value=_format_channel(after.channel), inline=True
        )
        return embed
    return None


def invite_created_embed(invite: discord.Invite) -> discord.Embed:
    embed = create_event_embed("招待作成", "invite_create")
    embed.add_field(name="コード", value=_inline_code(invite.code), inline=True)
    embed.add_field(name="URL", value=invite.url, inline=False)
    if invite.inviter:
        embed.add_field(name="作成者", value=_format_user(invite.inviter), inline=True)
    if invite.channel:
        embed.add_field(
            name="チャンネル", value=_format_channel(invite.channel), inline=True
        )
    embed.add_field(
        name="作成日時", value=_format_timestamp(invite.created_at), inline=True
    )
    embed.add_field(
        name="有効期限",
        value=_format_timestamp(invite.expires_at) if invite.expires_at else "無期限",
        inline=True,
    )
    embed.add_field(
        name="最大使用回数",
        value=str(invite.max_uses) if invite.max_uses else "無制限",
        inline=True,
    )
    embed.add_field(
        name="現在の使用回数",
        value="不明" if invite.uses is None else str(invite.uses),
        inline=True,
    )
    embed.add_field(
        name="一時メンバー", value=_format_boolean(bool(invite.temporary)), inline=True
    )
    return embed


def invite_deleted_embed(
    invite: discord.Invite,
    actor_id: int | None,
    reason: str | None,
) -> discord.Embed:
    embed = create_event_embed("招待削除", "invite_delete")
    embed.add_field(name="コード", value=_inline_code(invite.code), inline=True)
    if invite.channel:
        embed.add_field(
            name="チャンネル", value=_format_channel(invite.channel), inline=True
        )
    embed.add_field(name="URL", value=invite.url, inline=False)
    _add_audit_fields(embed, actor_id, reason, actor_label="実行者", show_unknown=True)
    return embed


def thread_embed(
    title: str,
    event_type: str,
    thread: discord.Thread,
    actor_id: int | None,
    reason: str | None,
) -> discord.Embed:
    embed = create_event_embed(title, event_type)
    embed.add_field(name="スレッド", value=_format_channel(thread), inline=True)
    embed.add_field(
        name="親チャンネル", value=_format_channel(thread.parent), inline=True
    )
    embed.add_field(
        name="作成日時", value=_format_timestamp(thread.created_at), inline=True
    )
    embed.add_field(
        name="アーカイブ", value=_format_boolean(thread.archived), inline=True
    )
    embed.add_field(name="ロック", value=_format_boolean(thread.locked), inline=True)
    if thread.owner_id:
        embed.add_field(
            name="作成者",
            value=f"<@{thread.owner_id}>\nID: {_inline_code(thread.owner_id)}",
            inline=True,
        )
    _add_audit_fields(
        embed,
        actor_id,
        reason,
        actor_label="実行者",
        show_unknown=event_type == "thread_delete",
    )
    return embed


def thread_updated_embed(
    before: discord.Thread,
    after: discord.Thread,
    actor_id: int | None,
    reason: str | None,
) -> discord.Embed | None:
    changes: list[str] = []
    _push_change(changes, "名前", before.name, after.name)
    _push_change(
        changes,
        "アーカイブ",
        _format_boolean(before.archived),
        _format_boolean(after.archived),
    )
    _push_change(
        changes, "ロック", _format_boolean(before.locked), _format_boolean(after.locked)
    )
    _push_change(
        changes, "低速モード", f"{before.slowmode_delay}s", f"{after.slowmode_delay}s"
    )
    _push_change(
        changes,
        "自動アーカイブ",
        before.auto_archive_duration,
        after.auto_archive_duration,
    )
    if not changes:
        return None
    embed = create_event_embed("スレッド更新", "thread_update")
    embed.add_field(name="スレッド", value=_format_channel(after), inline=True)
    embed.add_field(
        name="変更内容", value=truncate_content("\n".join(changes)), inline=False
    )
    _add_audit_fields(embed, actor_id, reason, actor_label="実行者", show_unknown=True)
    return embed


_VERIFICATION_LABELS = {
    "none": "なし",
    "low": "低 (メール認証)",
    "medium": "中 (登録後5分以上)",
    "high": "高 (参加後10分以上)",
    "highest": "最高 (電話番号認証)",
}
_NOTIFICATION_LABELS = {
    "all_messages": "すべてのメッセージ",
    "only_mentions": "メンションのみ",
}
_CONTENT_FILTER_LABELS = {
    "disabled": "無効",
    "no_role": "ロールなしメンバーのみ",
    "all_members": "全メンバー",
}
_MFA_LABELS = {
    "none": "なし",
    "disabled": "なし",
    "elevated": "管理操作に2FA必須",
}


def _enum_label(value: object, labels: dict[str, str]) -> str:
    name = getattr(value, "name", None)
    return labels.get(str(name), f"不明 ({getattr(value, 'value', value)})")


def guild_updated_embed(
    before: discord.Guild,
    after: discord.Guild,
    actor_id: int | None,
    reason: str | None,
) -> discord.Embed | None:
    changes: list[str] = []
    _push_change(changes, "名前", before.name, after.name)
    _push_change(changes, "説明", before.description, after.description)
    _push_change(
        changes,
        "認証レベル",
        _enum_label(before.verification_level, _VERIFICATION_LABELS),
        _enum_label(after.verification_level, _VERIFICATION_LABELS),
    )
    _push_change(
        changes,
        "通知設定",
        _enum_label(before.default_notifications, _NOTIFICATION_LABELS),
        _enum_label(after.default_notifications, _NOTIFICATION_LABELS),
    )
    _push_change(
        changes,
        "コンテンツフィルター",
        _enum_label(before.explicit_content_filter, _CONTENT_FILTER_LABELS),
        _enum_label(after.explicit_content_filter, _CONTENT_FILTER_LABELS),
    )
    _push_change(
        changes,
        "MFAレベル",
        _enum_label(before.mfa_level, _MFA_LABELS),
        _enum_label(after.mfa_level, _MFA_LABELS),
    )
    _push_change(
        changes, "優先ロケール", before.preferred_locale, after.preferred_locale
    )
    _push_change(
        changes,
        "AFKチャンネル",
        getattr(before.afk_channel, "name", None),
        getattr(after.afk_channel, "name", None),
    )
    _push_change(
        changes,
        "システムチャンネル",
        getattr(before.system_channel, "name", None),
        getattr(after.system_channel, "name", None),
    )
    _push_change(
        changes,
        "ルールチャンネル",
        getattr(before.rules_channel, "name", None),
        getattr(after.rules_channel, "name", None),
    )
    _push_change(
        changes,
        "公開アップデートチャンネル",
        getattr(before.public_updates_channel, "name", None),
        getattr(after.public_updates_channel, "name", None),
    )
    if before.icon != after.icon:
        changes.append("**アイコン:** 変更あり")
    if before.banner != after.banner:
        changes.append("**バナー:** 変更あり")
    if not changes:
        return None
    embed = create_event_embed("サーバー設定更新", "server_update")
    embed.add_field(
        name="サーバー",
        value=f"{after.name}\nID: {_inline_code(after.id)}",
        inline=True,
    )
    embed.add_field(
        name="変更内容", value=truncate_content("\n".join(changes)), inline=False
    )
    _add_audit_fields(embed, actor_id, reason, actor_label="実行者", show_unknown=True)
    return embed


def emoji_embed(
    title: str,
    emoji: discord.Emoji,
    details: str | None,
    actor_id: int | None,
    reason: str | None,
) -> discord.Embed:
    embed = create_event_embed(title, "emoji_update")
    embed.add_field(
        name="絵文字",
        value=(
            f"{emoji} ({_inline_code(f':{emoji.name}:')})\nID: {_inline_code(emoji.id)}"
        ),
        inline=True,
    )
    embed.add_field(
        name="作成日時", value=_format_timestamp(emoji.created_at), inline=True
    )
    embed.add_field(
        name="設定",
        value=(
            f"アニメーション: {_format_boolean(emoji.animated)} / "
            f"管理対象: {_format_boolean(emoji.managed)}"
        ),
        inline=False,
    )
    if details:
        embed.add_field(name="変更内容", value=truncate_content(details), inline=False)
    _add_audit_fields(embed, actor_id, reason, actor_label="実行者", show_unknown=True)
    embed.set_thumbnail(url=str(emoji.url))
    return embed
