"""Role panel UI components for role assignment.

ロールパネル用の UI コンポーネント。
ボタンまたはリアクションでロールを付与/解除するパネルを提供する。

UI の構成:
  - RolePanelView: ロールボタン群 (永続 View)
  - RolePanelCreateModal: パネル作成時のタイトル入力
  - create_role_panel_embed(): Embed 生成関数
  - create_role_panel_content(): 通常テキスト生成関数
"""

import logging
import time
from typing import Any

import discord

from src.constants import DEFAULT_EMBED_COLOR
from src.database.engine import async_session
from src.database.models import RolePanel, RolePanelItem
from src.services.db_service import (
    get_role_panel_item_by_emoji,
)

logger = logging.getLogger(__name__)

# =============================================================================
# クールダウン機能 (連打対策)
# =============================================================================

# クールダウン時間 (秒)
ROLE_PANEL_COOLDOWN_SECONDS = 1.0

# ユーザーごとの最終操作時刻を記録
# key: (user_id, panel_id), value: timestamp (float)
_cooldown_cache: dict[tuple[int, int], float] = {}

# キャッシュクリーンアップ間隔
_CLEANUP_INTERVAL = 300  # 5分
_last_cleanup_time = 0.0


def _cleanup_cooldown_cache() -> None:
    """古いクールダウンエントリを削除する."""
    global _last_cleanup_time
    now = time.monotonic()

    if _last_cleanup_time > 0 and now - _last_cleanup_time < _CLEANUP_INTERVAL:
        return

    _last_cleanup_time = now
    # 1パス削除: キーのスナップショットから期限切れをその場で削除
    for key in list(_cooldown_cache):
        if now - _cooldown_cache[key] > _CLEANUP_INTERVAL:
            del _cooldown_cache[key]


def is_on_cooldown(user_id: int, panel_id: int) -> bool:
    """ユーザーがクールダウン中かどうかを確認する.

    Args:
        user_id: ユーザー ID
        panel_id: パネル ID

    Returns:
        クールダウン中なら True
    """
    _cleanup_cooldown_cache()

    key = (user_id, panel_id)
    now = time.monotonic()

    last_time = _cooldown_cache.get(key)
    if last_time is not None and now - last_time < ROLE_PANEL_COOLDOWN_SECONDS:
        return True

    # クールダウンを記録/更新
    _cooldown_cache[key] = now
    return False


def clear_cooldown_cache() -> None:
    """クールダウンキャッシュをクリアする (テスト用)."""
    global _last_cleanup_time
    _cooldown_cache.clear()
    _last_cleanup_time = 0.0


def create_role_panel_embed(
    panel: RolePanel,
    items: list[RolePanelItem],
) -> discord.Embed:
    """ロールパネルの Embed を作成する。

    Args:
        panel: RolePanel オブジェクト
        items: パネルに設定されたロールアイテムのリスト

    Returns:
        組み立てた Embed オブジェクト
    """
    embed = discord.Embed(
        title=panel.title,
        description=panel.description or "",
        color=discord.Color(panel.color)
        if panel.color
        else discord.Color(DEFAULT_EMBED_COLOR),
    )

    # リアクション式の場合はロール一覧を表示
    if panel.panel_type == "reaction" and items:
        role_list = "\n".join(f"{item.emoji} → <@&{item.role_id}>" for item in items)
        embed.add_field(
            name="ロール一覧",
            value=role_list,
            inline=False,
        )

    return embed


def create_role_panel_content(
    panel: RolePanel,
    items: list[RolePanelItem],
) -> str:
    """ロールパネルの通常テキストメッセージを作成する。

    use_embed=False の場合に使用する。

    Args:
        panel: RolePanel オブジェクト
        items: パネルに設定されたロールアイテムのリスト

    Returns:
        組み立てたテキストメッセージ
    """
    lines = [f"**{panel.title}**"]

    if panel.description:
        lines.append(panel.description)

    # リアクション式の場合はロール一覧を表示
    if panel.panel_type == "reaction" and items:
        lines.append("")  # 空行
        lines.append("**ロール一覧**")
        for item in items:
            lines.append(f"{item.emoji} → <@&{item.role_id}>")

    return "\n".join(lines)


class RoleButton(discord.ui.Button[Any]):
    """ロール付与/解除用のボタン。

    クリックするとロールをトグル (付与/解除) する。
    custom_id 形式: role_panel:{panel_id}:{item_id}
    """

    def __init__(
        self,
        panel_id: int,
        item: RolePanelItem,
    ) -> None:
        # ボタンスタイルの変換
        style_map = {
            "primary": discord.ButtonStyle.primary,
            "secondary": discord.ButtonStyle.secondary,
            "success": discord.ButtonStyle.success,
            "danger": discord.ButtonStyle.danger,
        }
        style = style_map.get(item.style, discord.ButtonStyle.secondary)

        super().__init__(
            label=item.label or "",
            emoji=item.emoji,
            style=style,
            custom_id=f"role_panel:{panel_id}:{item.id}",
        )
        self.panel_id = panel_id
        self.role_id = item.role_id

    async def callback(self, interaction: discord.Interaction) -> None:
        """ボタンがクリックされたときの処理。ロールをトグルする。"""
        if interaction.guild is None:
            await interaction.response.send_message(
                "サーバー内でのみ使用できます。", ephemeral=True
            )
            return

        # クールダウンチェック (連打対策)
        if is_on_cooldown(interaction.user.id, self.panel_id):
            await interaction.response.send_message(
                "操作が早すぎます。少し待ってから再度お試しください。",
                ephemeral=True,
            )
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "メンバー情報を取得できませんでした。", ephemeral=True
            )
            return

        role = interaction.guild.get_role(int(self.role_id))
        if role is None:
            await interaction.response.send_message(
                "ロールが見つかりませんでした。削除された可能性があります。",
                ephemeral=True,
            )
            return

        # ロールの位置チェック (Bot のロールより上のロールは付与できない)
        bot_member = interaction.guild.me
        if bot_member and role >= bot_member.top_role:
            await interaction.response.send_message(
                "Bot の権限ではこのロールを付与できません。",
                ephemeral=True,
            )
            return

        try:
            if role in member.roles:
                # ロールを持っている → 解除
                await member.remove_roles(role, reason="ロールパネルから解除")
                await interaction.response.send_message(
                    f"{role.mention} を解除しました。",
                    ephemeral=True,
                )
            else:
                # ロールを持っていない → 付与
                await member.add_roles(role, reason="ロールパネルから付与")
                await interaction.response.send_message(
                    f"{role.mention} を付与しました。",
                    ephemeral=True,
                )
        except discord.Forbidden:
            await interaction.response.send_message(
                "権限不足でロールを変更できませんでした。",
                ephemeral=True,
            )
        except discord.HTTPException as e:
            logger.error("Failed to toggle role: %s", e)
            await interaction.response.send_message(
                "ロールの変更に失敗しました。",
                ephemeral=True,
            )


class RolePanelView(discord.ui.View):
    """ロールパネルのボタン View (永続)。

    timeout=None で Bot 再起動後もボタンが動作する。
    """

    def __init__(self, panel_id: int, items: list[RolePanelItem]) -> None:
        super().__init__(timeout=None)
        self.panel_id = panel_id

        # 各ロールのボタンを追加 (Discord の制限: 最大 25 コンポーネント)
        for item in items:
            if len(self.children) >= 25:
                logger.warning("Panel %d has more than 25 items, truncating", panel_id)
                break
            self.add_item(RoleButton(panel_id, item))


class RolePanelCreateModal(discord.ui.Modal, title="ロールパネル作成"):
    """パネル作成時のタイトル・説明入力モーダル。"""

    panel_title: discord.ui.TextInput[Any] = discord.ui.TextInput(
        label="タイトル",
        placeholder="例: ロール選択",
        min_length=1,
        max_length=256,
    )

    description: discord.ui.TextInput[Any] = discord.ui.TextInput(
        label="説明文",
        placeholder="例: 好きなロールを選んでください",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=4000,  # Discord Modal TextInput limit (Embed limit is 4096)
    )

    def __init__(
        self,
        panel_type: str,
        channel_id: int,
        remove_reaction: bool = False,
        use_embed: bool = True,
    ) -> None:
        super().__init__()
        self.panel_type = panel_type
        self.channel_id = channel_id
        self.remove_reaction = remove_reaction
        self.use_embed = use_embed
        # 作成後のコールバック用 (Cog 側で設定)
        self.created_panel: RolePanel | None = None

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """モーダル送信時の処理。パネルを作成して Embed を送信する。"""
        from src.services.db_service import create_role_panel, update_role_panel

        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message(
                "サーバー内でのみ使用できます。", ephemeral=True
            )
            return

        async with async_session() as db_session:
            # パネルを DB に作成
            panel = await create_role_panel(
                db_session,
                guild_id=str(interaction.guild.id),
                channel_id=str(self.channel_id),
                panel_type=self.panel_type,
                title=str(self.panel_title.value),
                description=str(self.description.value)
                if self.description.value
                else None,
                remove_reaction=self.remove_reaction,
                use_embed=self.use_embed,
            )

            # パネルを送信
            channel = interaction.guild.get_channel(self.channel_id)
            if channel is None or not isinstance(channel, discord.TextChannel):
                await interaction.response.send_message(
                    "チャンネルが見つかりませんでした。", ephemeral=True
                )
                return

            if panel.use_embed:
                # Embed 形式
                embed = create_role_panel_embed(panel, [])
                if self.panel_type == "button":
                    view = RolePanelView(panel.id, [])
                    msg = await channel.send(embed=embed, view=view)
                else:
                    msg = await channel.send(embed=embed)
            else:
                # テキスト形式
                content = create_role_panel_content(panel, [])
                if self.panel_type == "button":
                    view = RolePanelView(panel.id, [])
                    msg = await channel.send(content=content, view=view)
                else:
                    msg = await channel.send(content=content)

            # メッセージ ID を保存
            await update_role_panel(
                db_session,
                panel,
                message_id=str(msg.id),
            )

            self.created_panel = panel

        await interaction.response.send_message(
            "ロールパネルを作成しました！\n"
            "`/rolepanel add` でロールを追加してください。",
            ephemeral=True,
        )


async def refresh_role_panel(
    channel: discord.TextChannel,
    panel: RolePanel,
    items: list[RolePanelItem],
    bot: discord.Client,
) -> bool:
    """ロールパネルのメッセージを更新する。

    Args:
        channel: パネルがあるテキストチャンネル
        panel: 更新するパネル
        items: パネルのロールアイテム
        bot: Bot クライアント (View 登録用)

    Returns:
        更新できたら True、パネルが見つからなければ False
    """
    if panel.message_id is None:
        return False

    try:
        msg = await channel.fetch_message(int(panel.message_id))
    except discord.NotFound:
        logger.warning("Role panel message %s not found", panel.message_id)
        return False
    except discord.HTTPException as e:
        logger.error("Failed to fetch role panel message: %s", e)
        return False

    if panel.use_embed:
        # Embed 形式
        embed = create_role_panel_embed(panel, items)
        if panel.panel_type == "button":
            view = RolePanelView(panel.id, items)
            bot.add_view(view)
            await msg.edit(content=None, embed=embed, view=view)
        else:
            # リアクション式: リアクションを更新
            await msg.edit(content=None, embed=embed)
            await msg.clear_reactions()
            for item in items:
                try:
                    await msg.add_reaction(item.emoji)
                except discord.HTTPException as e:
                    logger.warning("Failed to add reaction %s: %s", item.emoji, e)
    else:
        # テキスト形式
        content = create_role_panel_content(panel, items)
        if panel.panel_type == "button":
            view = RolePanelView(panel.id, items)
            bot.add_view(view)
            await msg.edit(content=content, embed=None, view=view)
        else:
            # リアクション式: リアクションを更新
            await msg.edit(content=content, embed=None)
            await msg.clear_reactions()
            for item in items:
                try:
                    await msg.add_reaction(item.emoji)
                except discord.HTTPException as e:
                    logger.warning("Failed to add reaction %s: %s", item.emoji, e)

    return True


async def handle_role_reaction(
    payload: discord.RawReactionActionEvent,
    action: str,  # "add" or "remove"
) -> None:
    """リアクション式ロールパネルのイベントを処理する。

    Args:
        payload: リアクションイベントのペイロード
        action: "add" (リアクション追加) または "remove" (リアクション削除)
    """
    # Bot 自身のリアクションは無視
    if payload.member is None and action == "add":
        return

    # クールダウンチェック (連打対策)
    # リアクションの場合は message_id を panel_id として代用
    # (実際の panel_id は DB クエリ後でないと分からないため)
    if payload.user_id and is_on_cooldown(payload.user_id, payload.message_id):
        # リアクションの場合は静かに無視 (ephemeral メッセージを送れない)
        logger.debug(
            "Rate limited reaction from user %d on message %d",
            payload.user_id,
            payload.message_id,
        )
        return

    async with async_session() as db_session:
        from src.services.db_service import get_role_panel_by_message_id

        # パネルを取得
        panel = await get_role_panel_by_message_id(db_session, str(payload.message_id))
        if panel is None or panel.panel_type != "reaction":
            return

        # 絵文字からロールを取得
        emoji_str = str(payload.emoji)
        item = await get_role_panel_item_by_emoji(db_session, panel.id, emoji_str)
        if item is None:
            return

    # ギルドとメンバーを取得
    # payload.member は add 時のみ設定される
    # remove 時は guild から取得する必要がある
    guild = None
    member = None

    if action == "add" and payload.member:
        guild = payload.member.guild
        member = payload.member
    else:
        # Bot のキャッシュからギルドを取得する必要がある
        # この関数は Cog 側で適切に呼び出す
        return

    if guild is None or member is None:
        return

    # Bot 自身は無視
    if member.bot:
        return

    role = guild.get_role(int(item.role_id))
    if role is None:
        logger.warning("Role %s not found for panel %d", item.role_id, panel.id)
        return

    try:
        if action == "add":
            if role not in member.roles:
                await member.add_roles(
                    role, reason="ロールパネル (リアクション) から付与"
                )
        else:  # remove
            if role in member.roles:
                await member.remove_roles(
                    role, reason="ロールパネル (リアクション) から解除"
                )
    except discord.Forbidden:
        logger.warning("No permission to modify role %s", role.name)
    except discord.HTTPException as e:
        logger.error("Failed to modify role: %s", e)
