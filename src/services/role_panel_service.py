"""RolePanel, RolePanelItem の DB 操作。"""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import RolePanel, RolePanelItem

__all__ = [
    "add_role_panel_item",
    "create_role_panel",
    "delete_role_panel",
    "delete_role_panel_by_message_id",
    "delete_role_panels_by_channel",
    "delete_role_panels_by_guild",
    "get_all_role_panels",
    "get_role_panel",
    "get_role_panel_by_message_id",
    "get_role_panel_item_by_emoji",
    "get_role_panel_items",
    "get_role_panels_by_channel",
    "get_role_panels_by_guild",
    "remove_role_panel_item",
    "update_role_panel",
]


# =============================================================================
# RolePanel (ロールパネル) 操作
# =============================================================================


async def create_role_panel(
    session: AsyncSession,
    guild_id: str,
    channel_id: str,
    panel_type: str,
    title: str,
    description: str | None = None,
    color: int | None = None,
    remove_reaction: bool = False,
    use_embed: bool = True,
) -> RolePanel:
    """ロールパネルを作成する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        channel_id: パネルを送信するチャンネルの ID
        panel_type: パネルの種類 ("button" または "reaction")
        title: パネルのタイトル
        description: パネルの説明文
        color: Embed の色
        remove_reaction: リアクション自動削除フラグ (リアクション式のみ)
        use_embed: メッセージ形式フラグ (True: Embed, False: テキスト)

    Returns:
        作成された RolePanel オブジェクト
    """
    panel = RolePanel(
        guild_id=guild_id,
        channel_id=channel_id,
        panel_type=panel_type,
        title=title,
        description=description,
        color=color,
        remove_reaction=remove_reaction,
        use_embed=use_embed,
    )
    session.add(panel)
    await session.commit()
    await session.refresh(panel)
    return panel


async def get_role_panel(
    session: AsyncSession,
    panel_id: int,
) -> RolePanel | None:
    """パネル ID からロールパネルを取得する。

    Args:
        session: DB セッション
        panel_id: パネルの ID

    Returns:
        見つかった RolePanel、なければ None
    """
    result = await session.execute(select(RolePanel).where(RolePanel.id == panel_id))
    return result.scalar_one_or_none()


async def get_role_panel_by_message_id(
    session: AsyncSession,
    message_id: str,
) -> RolePanel | None:
    """メッセージ ID からロールパネルを取得する。

    ボタン/リアクションイベント時にパネルを特定するために使う。

    Args:
        session: DB セッション
        message_id: Discord メッセージの ID

    Returns:
        見つかった RolePanel、なければ None
    """
    result = await session.execute(
        select(RolePanel).where(RolePanel.message_id == message_id)
    )
    return result.scalar_one_or_none()


async def get_role_panels_by_guild(
    session: AsyncSession,
    guild_id: str,
) -> list[RolePanel]:
    """サーバー内の全ロールパネルを取得する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        RolePanel のリスト
    """
    result = await session.execute(
        select(RolePanel).where(RolePanel.guild_id == guild_id)
    )
    return list(result.scalars().all())


async def get_role_panels_by_channel(
    session: AsyncSession,
    channel_id: str,
) -> list[RolePanel]:
    """チャンネル内の全ロールパネルを取得する。

    Args:
        session: DB セッション
        channel_id: Discord チャンネルの ID

    Returns:
        RolePanel のリスト
    """
    result = await session.execute(
        select(RolePanel).where(RolePanel.channel_id == channel_id)
    )
    return list(result.scalars().all())


async def get_all_role_panels(
    session: AsyncSession,
) -> list[RolePanel]:
    """全てのロールパネルを取得する。

    Bot 起動時に永続 View を復元するために使う。

    Args:
        session: DB セッション

    Returns:
        全 RolePanel のリスト
    """
    result = await session.execute(select(RolePanel))
    return list(result.scalars().all())


async def update_role_panel(
    session: AsyncSession,
    panel: RolePanel,
    *,
    message_id: str | None = None,
    title: str | None = None,
    description: str | None = None,
    color: int | None = None,
    remove_reaction: bool | None = None,
) -> RolePanel:
    """ロールパネルを更新する。

    None のフィールドは変更しない。

    Args:
        session: DB セッション
        panel: 更新対象の RolePanel
        message_id: 新しいメッセージ ID
        title: 新しいタイトル
        description: 新しい説明文
        color: 新しい色
        remove_reaction: リアクション自動削除フラグ

    Returns:
        更新後の RolePanel
    """
    if message_id is not None:
        panel.message_id = message_id
    if title is not None:
        panel.title = title
    if description is not None:
        panel.description = description
    if color is not None:
        panel.color = color
    if remove_reaction is not None:
        panel.remove_reaction = remove_reaction

    await session.commit()
    return panel


async def delete_role_panel(
    session: AsyncSession,
    panel_id: int,
) -> bool:
    """ロールパネルを削除する。

    関連する RolePanelItem も CASCADE で削除される。

    Args:
        session: DB セッション
        panel_id: 削除するパネルの ID

    Returns:
        削除できたら True、見つからなければ False
    """
    result = await session.execute(select(RolePanel).where(RolePanel.id == panel_id))
    panel = result.scalar_one_or_none()
    if panel:
        await session.delete(panel)
        await session.commit()
        return True
    return False


async def delete_role_panels_by_guild(session: AsyncSession, guild_id: str) -> int:
    """指定ギルドの全ロールパネルを削除する。

    Bot がギルドから退出したときにクリーンアップとして使用。
    カスケード削除により、関連する RolePanelItem も自動削除される。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        削除したロールパネルの数
    """
    result = await session.execute(
        delete(RolePanel).where(RolePanel.guild_id == guild_id)
    )
    await session.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]


async def delete_role_panels_by_channel(session: AsyncSession, channel_id: str) -> int:
    """指定チャンネルの全ロールパネルを削除する。

    チャンネルが削除されたときにクリーンアップとして使用。
    カスケード削除により、関連する RolePanelItem も自動削除される。

    Args:
        session: DB セッション
        channel_id: Discord チャンネルの ID

    Returns:
        削除したロールパネルの数
    """
    result = await session.execute(
        delete(RolePanel).where(RolePanel.channel_id == channel_id)
    )
    await session.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]


async def delete_role_panel_by_message_id(
    session: AsyncSession, message_id: str
) -> bool:
    """指定メッセージIDのロールパネルを削除する。

    パネルメッセージが削除されたときにクリーンアップとして使用。
    カスケード削除により、関連する RolePanelItem も自動削除される。

    Args:
        session: DB セッション
        message_id: Discord メッセージの ID

    Returns:
        削除した場合は True、パネルが存在しなかった場合は False
    """
    result = await session.execute(
        select(RolePanel).where(RolePanel.message_id == message_id)
    )
    panel = result.scalar_one_or_none()
    if panel:
        await session.delete(panel)
        await session.commit()
        return True
    return False


# =============================================================================
# RolePanelItem (ロールパネルアイテム) 操作
# =============================================================================


async def add_role_panel_item(
    session: AsyncSession,
    panel_id: int,
    role_id: str,
    emoji: str,
    label: str | None = None,
    style: str = "secondary",
) -> RolePanelItem:
    """ロールパネルにアイテム (ロール) を追加する。

    Args:
        session: DB セッション
        panel_id: パネルの ID
        role_id: 付与するロールの Discord ID
        emoji: ボタン/リアクションに使用する絵文字
        label: ボタンのラベル (ボタン式のみ)
        style: ボタンのスタイル

    Returns:
        作成された RolePanelItem

    Raises:
        sqlalchemy.exc.IntegrityError: 同じ絵文字が既に存在する場合
            (UniqueConstraint "uq_panel_emoji" 違反)
    """
    # 現在の最大 position を取得
    result = await session.execute(
        select(func.coalesce(func.max(RolePanelItem.position), -1)).where(
            RolePanelItem.panel_id == panel_id
        )
    )
    next_position = result.scalar_one() + 1

    item = RolePanelItem(
        panel_id=panel_id,
        role_id=role_id,
        emoji=emoji,
        label=label,
        style=style,
        position=next_position,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def get_role_panel_items(
    session: AsyncSession,
    panel_id: int,
) -> list[RolePanelItem]:
    """パネルに設定されたロールアイテムを取得する。

    position 順にソートして返す。

    Args:
        session: DB セッション
        panel_id: パネルの ID

    Returns:
        RolePanelItem のリスト (position 順)
    """
    result = await session.execute(
        select(RolePanelItem)
        .where(RolePanelItem.panel_id == panel_id)
        .order_by(RolePanelItem.position)
    )
    return list(result.scalars().all())


async def get_role_panel_item_by_emoji(
    session: AsyncSession,
    panel_id: int,
    emoji: str,
) -> RolePanelItem | None:
    """絵文字からロールパネルアイテムを取得する。

    Args:
        session: DB セッション
        panel_id: パネルの ID
        emoji: 検索する絵文字

    Returns:
        見つかった RolePanelItem、なければ None
    """
    result = await session.execute(
        select(RolePanelItem).where(
            RolePanelItem.panel_id == panel_id,
            RolePanelItem.emoji == emoji,
        )
    )
    return result.scalar_one_or_none()


async def remove_role_panel_item(
    session: AsyncSession,
    panel_id: int,
    emoji: str,
) -> bool:
    """ロールパネルからアイテムを削除する。

    Args:
        session: DB セッション
        panel_id: パネルの ID
        emoji: 削除するアイテムの絵文字

    Returns:
        削除できたら True、見つからなければ False
    """
    item = await get_role_panel_item_by_emoji(session, panel_id, emoji)
    if item:
        await session.delete(item)
        await session.commit()
        return True
    return False
