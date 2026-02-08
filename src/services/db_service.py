"""Database service functions with side effects.

データベースの CRUD (Create, Read, Update, Delete) 操作を提供する。
各関数は AsyncSession を受け取り、SQL クエリを実行する。

Examples:
    基本的な使い方::

        from src.database.engine import async_session
        from src.services.db_service import get_lobby_by_channel_id

        async with async_session() as session:
            lobby = await get_lobby_by_channel_id(session, "123456")
            if lobby:
                print(f"Found lobby: {lobby.id}")

    トランザクション内での複数操作::

        async with async_session() as session:
            lobby = await create_lobby(session, guild_id, channel_id)
            voice_session = await create_voice_session(
                session,
                lobby_id=lobby.id,
                channel_id=new_channel_id,
                owner_id=user_id,
                name="New Room",
            )

See Also:
    - :mod:`src.database.models`: テーブル定義
    - :mod:`src.database.engine`: データベース接続設定
    - SQLAlchemy AsyncSession: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html

Notes:
    - 各関数は session.commit() を内部で呼び出す
    - エラー時は session.rollback() を呼び出し元で行う必要がある
    - 複数操作をトランザクションで束ねる場合は、commit を最後にまとめる
"""

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    AutoBanConfig,
    AutoBanLog,
    AutoBanRule,
    BanLog,
    BumpConfig,
    BumpReminder,
    DiscordChannel,
    DiscordGuild,
    DiscordRole,
    JoinRoleAssignment,
    JoinRoleConfig,
    Lobby,
    RolePanel,
    RolePanelItem,
    StickyMessage,
    Ticket,
    TicketCategory,
    TicketPanel,
    TicketPanelCategory,
    VoiceSession,
    VoiceSessionMember,
)

# =============================================================================
# Lobby (ロビー) 操作
# =============================================================================


async def get_lobby_by_channel_id(
    session: AsyncSession, channel_id: str
) -> Lobby | None:
    """チャンネル ID からロビーを取得する。

    ユーザーが VC に参加したとき、そのチャンネルがロビーかどうかを
    判定するために使う。

    Args:
        session (AsyncSession): DB セッション。
        channel_id (str): 調べたい Discord チャンネルの ID (文字列)。

    Returns:
        Lobby | None: ロビーが見つかれば Lobby オブジェクト、なければ None。

    Raises:
        sqlalchemy.exc.MultipleResultsFound: 同じ channel_id のレコードが
            複数存在する場合 (通常は発生しない、ユニーク制約あり)。

    Examples:
        ロビー判定::

            async with async_session() as session:
                lobby = await get_lobby_by_channel_id(session, channel_id)
                if lobby:
                    # ロビーに参加した → 一時 VC を作成
                    pass
                else:
                    # 通常の VC に参加した
                    pass

    See Also:
        - :func:`create_lobby`: ロビー作成
        - :class:`src.database.models.Lobby`: ロビーモデル
    """
    # select(Lobby) → SELECT * FROM lobbies
    # .where(...) → WHERE lobby_channel_id = :channel_id
    result = await session.execute(
        select(Lobby).where(Lobby.lobby_channel_id == channel_id)
    )
    # scalar_one_or_none: 結果が1行なら返す、0行なら None、2行以上ならエラー
    return result.scalar_one_or_none()


async def get_lobbies_by_guild(session: AsyncSession, guild_id: str) -> list[Lobby]:
    """サーバー (guild) に属する全ロビーを取得する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        ロビーのリスト (0件なら空リスト)
    """
    result = await session.execute(select(Lobby).where(Lobby.guild_id == guild_id))
    # scalars().all() で全行を取得し、list() でリストに変換
    return list(result.scalars().all())


async def create_lobby(
    session: AsyncSession,
    guild_id: str,
    lobby_channel_id: str,
    category_id: str | None = None,
    default_user_limit: int = 0,
) -> Lobby:
    """新しいロビーを DB に登録する。

    /lobby コマンドで VC を作成した後に呼ばれる。

    Args:
        session (AsyncSession): DB セッション。
        guild_id (str): Discord サーバーの ID。
        lobby_channel_id (str): ロビーとして登録する VC の ID。
        category_id (str | None): 一時 VC を配置するカテゴリの ID。
            None なら同カテゴリ。
        default_user_limit (int): デフォルトの人数制限 (0 = 無制限)。

    Returns:
        Lobby: 作成された Lobby オブジェクト (id が自動採番される)。

    Raises:
        sqlalchemy.exc.IntegrityError: 同じ lobby_channel_id が既に存在する場合。

    Notes:
        - commit() を内部で呼び出す
        - refresh() で自動採番された id を取得

    Examples:
        ロビー作成::

            async with async_session() as session:
                lobby = await create_lobby(
                    session,
                    guild_id="123456789",
                    lobby_channel_id="987654321",
                    default_user_limit=10,
                )
                print(f"Created lobby with ID: {lobby.id}")

    See Also:
        - :func:`delete_lobby`: ロビー削除
        - :func:`get_lobby_by_channel_id`: ロビー取得
    """
    lobby = Lobby(
        guild_id=guild_id,
        lobby_channel_id=lobby_channel_id,
        category_id=category_id,
        default_user_limit=default_user_limit,
    )
    # session.add(): セッションにオブジェクトを追加 (INSERT 予約)
    session.add(lobby)
    # commit(): 実際に DB に書き込む (INSERT 実行)
    await session.commit()
    # refresh(): DB から最新の値を読み直す (自動採番された id を取得)
    await session.refresh(lobby)
    return lobby


async def delete_lobby(session: AsyncSession, lobby_id: int) -> bool:
    """ロビーを削除する。

    Args:
        session: DB セッション
        lobby_id: 削除するロビーの ID

    Returns:
        削除できたら True、見つからなければ False
    """
    result = await session.execute(select(Lobby).where(Lobby.id == lobby_id))
    lobby = result.scalar_one_or_none()
    if lobby:
        # session.delete() + commit() で DELETE 文を実行
        await session.delete(lobby)
        await session.commit()
        return True
    return False


async def delete_lobbies_by_guild(session: AsyncSession, guild_id: str) -> int:
    """指定ギルドの全ロビーを削除する。

    Bot がギルドから退出したときにクリーンアップとして使用。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        削除したロビーの数
    """
    result = await session.execute(delete(Lobby).where(Lobby.guild_id == guild_id))
    await session.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]


async def get_all_lobbies(session: AsyncSession) -> list[Lobby]:
    """全てのロビーを取得する。

    Args:
        session: DB セッション

    Returns:
        全ロビーのリスト
    """
    result = await session.execute(select(Lobby))
    return list(result.scalars().all())


# =============================================================================
# VoiceSession (一時 VC セッション) 操作
# =============================================================================


async def get_voice_session(
    session: AsyncSession, channel_id: str
) -> VoiceSession | None:
    """チャンネル ID から VC セッションを取得する。

    チャンネルが一時 VC かどうかの判定や、オーナー情報の取得に使う。

    Args:
        session: DB セッション
        channel_id: Discord VC のチャンネル ID

    Returns:
        セッションが見つかれば VoiceSession、なければ None
    """
    result = await session.execute(
        select(VoiceSession).where(VoiceSession.channel_id == channel_id)
    )
    return result.scalar_one_or_none()


async def get_all_voice_sessions(session: AsyncSession) -> list[VoiceSession]:
    """全てのアクティブな VC セッションを取得する。

    Bot 起動時に永続 View を復元するために使う。

    Args:
        session: DB セッション

    Returns:
        全 VoiceSession のリスト
    """
    result = await session.execute(select(VoiceSession))
    return list(result.scalars().all())


async def create_voice_session(
    session: AsyncSession,
    lobby_id: int,
    channel_id: str,
    owner_id: str,
    name: str,
    user_limit: int = 0,
) -> VoiceSession:
    """新しい VC セッションを DB に登録する。

    ユーザーがロビーに参加し、一時 VC が作成された直後に呼ばれる。

    Args:
        session (AsyncSession): DB セッション。
        lobby_id (int): 親ロビーの ID。
        channel_id (str): 作成された一時 VC の ID。
        owner_id (str): チャンネルオーナーの Discord ユーザー ID。
        name (str): チャンネル名。
        user_limit (int): 人数制限 (0 = 無制限)。

    Returns:
        VoiceSession: 作成された VoiceSession オブジェクト。

    Raises:
        sqlalchemy.exc.IntegrityError: 同じ channel_id が既に存在する場合、
            または存在しない lobby_id を指定した場合。

    Notes:
        - commit() を内部で呼び出す
        - 作成後、オーナーを VoiceSessionMember として追加する必要がある

    Examples:
        セッション作成::

            async with async_session() as session:
                voice_session = await create_voice_session(
                    session,
                    lobby_id=lobby.id,
                    channel_id=str(channel.id),
                    owner_id=str(member.id),
                    name=f"{member.display_name}'s channel",
                )
                # オーナーをメンバーとして追加
                await add_voice_session_member(
                    session, voice_session.id, str(member.id)
                )

    See Also:
        - :func:`delete_voice_session`: セッション削除
        - :func:`update_voice_session`: セッション更新
        - :func:`add_voice_session_member`: メンバー追加
    """
    voice_session = VoiceSession(
        lobby_id=lobby_id,
        channel_id=channel_id,
        owner_id=owner_id,
        name=name,
        user_limit=user_limit,
    )
    session.add(voice_session)
    await session.commit()
    await session.refresh(voice_session)
    return voice_session


async def update_voice_session(
    session: AsyncSession,
    voice_session: VoiceSession,
    *,
    name: str | None = None,
    user_limit: int | None = None,
    is_locked: bool | None = None,
    is_hidden: bool | None = None,
    owner_id: str | None = None,
) -> VoiceSession:
    """VC セッションの情報を更新する。

    コントロールパネルのボタン操作 (名前変更、ロック、非表示、オーナー譲渡)
    で呼ばれる。None のフィールドは変更しない。

    Args:
        session (AsyncSession): DB セッション。
        voice_session (VoiceSession): 更新対象の VoiceSession オブジェクト。
        name (str | None): 新しいチャンネル名 (None なら変更しない)。
        user_limit (int | None): 新しい人数制限 (None なら変更しない)。
        is_locked (bool | None): 新しいロック状態 (None なら変更しない)。
        is_hidden (bool | None): 新しい非表示状態 (None なら変更しない)。
        owner_id (str | None): 新しいオーナー ID (None なら変更しない)。

    Returns:
        VoiceSession: 更新後の VoiceSession オブジェクト。

    Notes:
        - キーワード引数のみ受け付ける (``*`` による区切り)
        - 部分更新パターン: None のフィールドは変更しない
        - commit() を内部で呼び出す

    Examples:
        ロック状態のみ変更::

            async with async_session() as session:
                voice_session = await get_voice_session(session, channel_id)
                voice_session = await update_voice_session(
                    session,
                    voice_session,
                    is_locked=True,
                )

        複数フィールドを同時に変更::

            voice_session = await update_voice_session(
                session,
                voice_session,
                name="New Name",
                user_limit=5,
                is_hidden=True,
            )

    See Also:
        - :func:`get_voice_session`: セッション取得
        - :class:`src.database.models.VoiceSession`: セッションモデル
    """
    # None でないフィールドだけ更新する (部分更新パターン)
    if name is not None:
        voice_session.name = name
    if user_limit is not None:
        voice_session.user_limit = user_limit
    if is_locked is not None:
        voice_session.is_locked = is_locked
    if is_hidden is not None:
        voice_session.is_hidden = is_hidden
    if owner_id is not None:
        voice_session.owner_id = owner_id

    # SQLAlchemy はオブジェクトの変更を自動検知するので、
    # commit() だけで UPDATE 文が実行される
    await session.commit()
    return voice_session


async def delete_voice_session(session: AsyncSession, channel_id: str) -> bool:
    """VC セッションを削除する。

    一時 VC から全員が退出したとき、チャンネル削除と一緒に呼ばれる。

    Args:
        session: DB セッション
        channel_id: 削除する VC のチャンネル ID

    Returns:
        削除できたら True、見つからなければ False
    """
    result = await session.execute(
        select(VoiceSession).where(VoiceSession.channel_id == channel_id)
    )
    voice_session = result.scalar_one_or_none()
    if voice_session:
        await session.delete(voice_session)
        await session.commit()
        return True
    return False


async def delete_voice_sessions_by_guild(session: AsyncSession, guild_id: str) -> int:
    """指定ギルドの全 VC セッションを削除する。

    Bot がギルドから退出したときにクリーンアップとして使用。
    Lobby テーブルを経由して該当ギルドのセッションを検索。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        削除したセッションの数
    """
    # Lobby 経由で該当ギルドの VoiceSession を削除 (サブクエリ使用)
    result = await session.execute(
        delete(VoiceSession).where(
            VoiceSession.lobby_id.in_(
                select(Lobby.id).where(Lobby.guild_id == guild_id)
            )
        )
    )
    await session.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]


# =============================================================================
# VoiceSessionMember (VC メンバー) 操作
# =============================================================================


async def add_voice_session_member(
    session: AsyncSession,
    voice_session_id: int,
    user_id: str,
) -> VoiceSessionMember:
    """VC セッションにメンバーを追加する。

    ユーザーが一時 VC に参加したときに呼ばれる。
    既に存在する場合は既存のレコードを返す (参加時刻は更新しない)。

    Args:
        session: DB セッション
        voice_session_id: VC セッションの ID
        user_id: メンバーの Discord ユーザー ID

    Returns:
        作成または既存の VoiceSessionMember オブジェクト
    """
    # 既存のレコードがあるか確認
    result = await session.execute(
        select(VoiceSessionMember).where(
            VoiceSessionMember.voice_session_id == voice_session_id,
            VoiceSessionMember.user_id == user_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    # 新規作成
    member = VoiceSessionMember(
        voice_session_id=voice_session_id,
        user_id=user_id,
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


async def remove_voice_session_member(
    session: AsyncSession,
    voice_session_id: int,
    user_id: str,
) -> bool:
    """VC セッションからメンバーを削除する。

    ユーザーが一時 VC から退出したときに呼ばれる。

    Args:
        session: DB セッション
        voice_session_id: VC セッションの ID
        user_id: メンバーの Discord ユーザー ID

    Returns:
        削除できたら True、見つからなければ False
    """
    result = await session.execute(
        select(VoiceSessionMember).where(
            VoiceSessionMember.voice_session_id == voice_session_id,
            VoiceSessionMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if member:
        await session.delete(member)
        await session.commit()
        return True
    return False


async def get_voice_session_members_ordered(
    session: AsyncSession,
    voice_session_id: int,
) -> list[VoiceSessionMember]:
    """VC セッションのメンバーを参加順 (古い順) で取得する。

    オーナー引き継ぎ時の優先順位を決定するために使う。

    Args:
        session: DB セッション
        voice_session_id: VC セッションの ID

    Returns:
        参加時刻が古い順にソートされた VoiceSessionMember のリスト
    """
    result = await session.execute(
        select(VoiceSessionMember)
        .where(VoiceSessionMember.voice_session_id == voice_session_id)
        .order_by(VoiceSessionMember.joined_at, VoiceSessionMember.user_id)
    )
    return list(result.scalars().all())


# =============================================================================
# BumpReminder (bump リマインダー) 操作
# =============================================================================


async def upsert_bump_reminder(
    session: AsyncSession,
    guild_id: str,
    channel_id: str,
    service_name: str,
    remind_at: datetime,
) -> BumpReminder:
    """bump リマインダーを作成または更新する。

    同じ guild_id + service_name の組み合わせが既に存在する場合は上書きする。
    UPSERT (INSERT or UPDATE) パターンを実装。

    Args:
        session (AsyncSession): DB セッション。
        guild_id (str): Discord サーバーの ID。
        channel_id (str): リマインド通知を送信するチャンネルの ID。
        service_name (str): サービス名 ("DISBOARD" または "ディス速報")。
        remind_at (datetime): リマインドを送信する予定時刻 (UTC)。

    Returns:
        BumpReminder: 作成または更新された BumpReminder オブジェクト。

    Notes:
        - 既存レコードがある場合は channel_id と remind_at のみ更新
        - is_enabled と role_id は既存の値を保持
        - commit() を内部で呼び出す

    Examples:
        bump 検知後のリマインダー設定::

            from datetime import UTC, datetime, timedelta

            async with async_session() as session:
                remind_at = datetime.now(UTC) + timedelta(hours=2)
                reminder = await upsert_bump_reminder(
                    session,
                    guild_id=str(guild.id),
                    channel_id=str(channel.id),
                    service_name="DISBOARD",
                    remind_at=remind_at,
                )

    See Also:
        - :func:`get_due_bump_reminders`: 期限切れリマインダー取得
        - :func:`clear_bump_reminder`: リマインダーのクリア
        - :class:`src.database.models.BumpReminder`: リマインダーモデル
    """
    # 既存のレコードを検索
    result = await session.execute(
        select(BumpReminder).where(
            BumpReminder.guild_id == guild_id,
            BumpReminder.service_name == service_name,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # 既存レコードを更新
        existing.channel_id = channel_id
        existing.remind_at = remind_at
        await session.commit()
        return existing

    # 新規作成
    reminder = BumpReminder(
        guild_id=guild_id,
        channel_id=channel_id,
        service_name=service_name,
        remind_at=remind_at,
    )
    session.add(reminder)
    await session.commit()
    await session.refresh(reminder)
    return reminder


async def get_due_bump_reminders(
    session: AsyncSession,
    now: datetime,
) -> list[BumpReminder]:
    """送信予定時刻を過ぎた有効な bump リマインダーを取得する。

    Args:
        session: DB セッション
        now: 現在時刻 (UTC)

    Returns:
        remind_at <= now かつ is_enabled = True の BumpReminder のリスト
    """
    result = await session.execute(
        select(BumpReminder).where(
            BumpReminder.remind_at <= now,
            BumpReminder.remind_at.isnot(None),
            BumpReminder.is_enabled.is_(True),
        )
    )
    return list(result.scalars().all())


async def clear_bump_reminder(session: AsyncSession, reminder_id: int) -> bool:
    """bump リマインダーの remind_at をクリアする。

    リマインド送信後に呼ばれる。レコードは削除せず、remind_at を None にする。

    Args:
        session: DB セッション
        reminder_id: クリアするリマインダーの ID

    Returns:
        クリアできたら True、見つからなければ False
    """
    result = await session.execute(
        select(BumpReminder).where(BumpReminder.id == reminder_id)
    )
    reminder = result.scalar_one_or_none()
    if reminder:
        reminder.remind_at = None
        await session.commit()
        return True
    return False


async def get_bump_reminder(
    session: AsyncSession,
    guild_id: str,
    service_name: str,
) -> BumpReminder | None:
    """guild_id と service_name で bump リマインダーを取得する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        service_name: サービス名 ("DISBOARD" または "ディス速報")

    Returns:
        見つかった BumpReminder、なければ None
    """
    result = await session.execute(
        select(BumpReminder).where(
            BumpReminder.guild_id == guild_id,
            BumpReminder.service_name == service_name,
        )
    )
    return result.scalar_one_or_none()


async def toggle_bump_reminder(
    session: AsyncSession,
    guild_id: str,
    service_name: str,
) -> bool:
    """bump リマインダーの有効/無効を切り替える。

    レコードが存在しない場合は無効状態で新規作成する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        service_name: サービス名 ("DISBOARD" または "ディス速報")

    Returns:
        切り替え後の is_enabled 値
    """
    reminder = await get_bump_reminder(session, guild_id, service_name)

    if reminder:
        reminder.is_enabled = not reminder.is_enabled
        await session.commit()
        return reminder.is_enabled

    # レコードがない場合は無効状態で新規作成
    new_reminder = BumpReminder(
        guild_id=guild_id,
        channel_id="",  # 通知先は bump 検知時に設定される
        service_name=service_name,
        remind_at=None,
        is_enabled=False,
    )
    session.add(new_reminder)
    await session.commit()
    return False


async def update_bump_reminder_role(
    session: AsyncSession,
    guild_id: str,
    service_name: str,
    role_id: str | None,
) -> bool:
    """bump リマインダーの通知ロールを更新する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        service_name: サービス名 ("DISBOARD" または "ディス速報")
        role_id: 新しい通知ロールの ID (None ならデフォルトロールに戻す)

    Returns:
        更新できたら True、レコードが見つからなければ False
    """
    reminder = await get_bump_reminder(session, guild_id, service_name)

    if reminder:
        reminder.role_id = role_id
        await session.commit()
        return True

    return False


# =============================================================================
# BumpConfig (bump 監視設定) 操作
# =============================================================================


async def get_bump_config(
    session: AsyncSession,
    guild_id: str,
) -> BumpConfig | None:
    """ギルドの bump 監視設定を取得する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        見つかった BumpConfig、なければ None
    """
    result = await session.execute(
        select(BumpConfig).where(BumpConfig.guild_id == guild_id)
    )
    return result.scalar_one_or_none()


async def upsert_bump_config(
    session: AsyncSession,
    guild_id: str,
    channel_id: str,
) -> BumpConfig:
    """bump 監視設定を作成または更新する。

    既に設定がある場合はチャンネル ID を上書きする。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        channel_id: bump を監視するチャンネルの ID

    Returns:
        作成または更新された BumpConfig オブジェクト
    """
    existing = await get_bump_config(session, guild_id)

    if existing:
        existing.channel_id = channel_id
        await session.commit()
        return existing

    config = BumpConfig(guild_id=guild_id, channel_id=channel_id)
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


async def delete_bump_config(
    session: AsyncSession,
    guild_id: str,
) -> bool:
    """bump 監視設定を削除する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        削除できたら True、見つからなければ False
    """
    config = await get_bump_config(session, guild_id)

    if config:
        await session.delete(config)
        await session.commit()
        return True

    return False


async def delete_bump_reminders_by_guild(session: AsyncSession, guild_id: str) -> int:
    """指定ギルドの全 bump リマインダーを削除する。

    Bot がギルドから退出したときにクリーンアップとして使用。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        削除したリマインダーの数
    """
    result = await session.execute(
        delete(BumpReminder).where(BumpReminder.guild_id == guild_id)
    )
    await session.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]


async def get_all_bump_configs(session: AsyncSession) -> list[BumpConfig]:
    """全ての bump 設定を取得する。

    Args:
        session: DB セッション

    Returns:
        全 bump 設定のリスト
    """
    result = await session.execute(select(BumpConfig))
    return list(result.scalars().all())


# =============================================================================
# StickyMessage (sticky メッセージ) 操作
# =============================================================================


async def get_sticky_message(
    session: AsyncSession,
    channel_id: str,
) -> StickyMessage | None:
    """チャンネルの sticky メッセージ設定を取得する。

    Args:
        session: DB セッション
        channel_id: Discord チャンネルの ID

    Returns:
        見つかった StickyMessage、なければ None
    """
    result = await session.execute(
        select(StickyMessage).where(StickyMessage.channel_id == channel_id)
    )
    return result.scalar_one_or_none()


async def create_sticky_message(
    session: AsyncSession,
    channel_id: str,
    guild_id: str,
    title: str,
    description: str,
    color: int | None = None,
    cooldown_seconds: int = 5,
    message_type: str = "embed",
) -> StickyMessage:
    """sticky メッセージを作成する。

    既に同じチャンネルに設定がある場合は上書きする。

    Args:
        session: DB セッション
        channel_id: Discord チャンネルの ID
        guild_id: Discord サーバーの ID
        title: embed のタイトル (text の場合は空文字)
        description: embed の説明文 / text の本文
        color: embed の色 (16進数の整数値)
        cooldown_seconds: 再投稿までの最小間隔 (秒)
        message_type: メッセージの種類 ("embed" または "text")

    Returns:
        作成または更新された StickyMessage オブジェクト
    """
    existing = await get_sticky_message(session, channel_id)

    if existing:
        existing.guild_id = guild_id
        existing.title = title
        existing.description = description
        existing.color = color
        existing.cooldown_seconds = cooldown_seconds
        existing.message_type = message_type
        existing.message_id = None  # 新規設定なのでリセット
        existing.last_posted_at = None
        await session.commit()
        return existing

    sticky = StickyMessage(
        channel_id=channel_id,
        guild_id=guild_id,
        title=title,
        description=description,
        color=color,
        cooldown_seconds=cooldown_seconds,
        message_type=message_type,
    )
    session.add(sticky)
    await session.commit()
    await session.refresh(sticky)
    return sticky


async def update_sticky_message_id(
    session: AsyncSession,
    channel_id: str,
    message_id: str | None,
    last_posted_at: datetime | None = None,
) -> bool:
    """sticky メッセージの message_id と last_posted_at を更新する。

    新しい sticky メッセージを投稿した後に呼び出す。

    Args:
        session: DB セッション
        channel_id: Discord チャンネルの ID
        message_id: 投稿したメッセージの ID (削除する場合は None)
        last_posted_at: 投稿日時 (None なら更新しない)

    Returns:
        更新できたら True、見つからなければ False
    """
    sticky = await get_sticky_message(session, channel_id)

    if sticky:
        sticky.message_id = message_id
        if last_posted_at is not None:
            sticky.last_posted_at = last_posted_at
        await session.commit()
        return True

    return False


async def delete_sticky_message(
    session: AsyncSession,
    channel_id: str,
) -> bool:
    """sticky メッセージ設定を削除する。

    Args:
        session: DB セッション
        channel_id: Discord チャンネルの ID

    Returns:
        削除できたら True、見つからなければ False
    """
    sticky = await get_sticky_message(session, channel_id)

    if sticky:
        await session.delete(sticky)
        await session.commit()
        return True

    return False


async def delete_sticky_messages_by_guild(session: AsyncSession, guild_id: str) -> int:
    """指定ギルドの全 sticky メッセージを削除する。

    Bot がギルドから退出したときにクリーンアップとして使用。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        削除した sticky メッセージの数
    """
    result = await session.execute(
        delete(StickyMessage).where(StickyMessage.guild_id == guild_id)
    )
    await session.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]


async def get_all_sticky_messages(
    session: AsyncSession,
) -> list[StickyMessage]:
    """全ての sticky メッセージ設定を取得する。

    Bot 起動時に既存の sticky メッセージを復元するために使用する。

    Args:
        session: DB セッション

    Returns:
        全ての StickyMessage のリスト
    """
    result = await session.execute(select(StickyMessage))
    return list(result.scalars().all())


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


# =============================================================================
# DiscordRole (Discord ロールキャッシュ) 操作
# =============================================================================


async def upsert_discord_role(
    session: AsyncSession,
    guild_id: str,
    role_id: str,
    role_name: str,
    color: int = 0,
    position: int = 0,
) -> DiscordRole:
    """Discord ロール情報を作成または更新する。

    同じ guild_id + role_id の組み合わせが既に存在する場合は上書きする。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        role_id: Discord ロールの ID
        role_name: ロール名
        color: ロールの色 (16進数の整数値)
        position: ロールの表示順序

    Returns:
        作成または更新された DiscordRole オブジェクト
    """
    result = await session.execute(
        select(DiscordRole).where(
            DiscordRole.guild_id == guild_id,
            DiscordRole.role_id == role_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.role_name = role_name
        existing.color = color
        existing.position = position
        await session.commit()
        return existing

    role = DiscordRole(
        guild_id=guild_id,
        role_id=role_id,
        role_name=role_name,
        color=color,
        position=position,
    )
    session.add(role)
    await session.commit()
    await session.refresh(role)
    return role


async def delete_discord_role(
    session: AsyncSession,
    guild_id: str,
    role_id: str,
) -> bool:
    """Discord ロール情報を削除する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        role_id: Discord ロールの ID

    Returns:
        削除できたら True、見つからなければ False
    """
    result = await session.execute(
        select(DiscordRole).where(
            DiscordRole.guild_id == guild_id,
            DiscordRole.role_id == role_id,
        )
    )
    role = result.scalar_one_or_none()
    if role:
        await session.delete(role)
        await session.commit()
        return True
    return False


async def delete_discord_roles_by_guild(
    session: AsyncSession,
    guild_id: str,
) -> int:
    """サーバーの全ロール情報を削除する。

    Bot がサーバーから退出したときに呼ばれる。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        削除したレコード数
    """
    result = await session.execute(
        delete(DiscordRole).where(DiscordRole.guild_id == guild_id)
    )
    await session.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]


async def get_discord_roles_by_guild(
    session: AsyncSession,
    guild_id: str,
) -> list[DiscordRole]:
    """サーバーの全ロール情報を取得する。

    position の降順 (上位ロールから) でソートして返す。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        DiscordRole のリスト (position 降順)
    """
    result = await session.execute(
        select(DiscordRole)
        .where(DiscordRole.guild_id == guild_id)
        .order_by(DiscordRole.position.desc())
    )
    return list(result.scalars().all())


# =============================================================================
# DiscordGuild (Discord ギルドキャッシュ) 操作
# =============================================================================


async def upsert_discord_guild(
    session: AsyncSession,
    guild_id: str,
    guild_name: str,
    icon_hash: str | None = None,
    member_count: int = 0,
) -> DiscordGuild:
    """Discord ギルド情報を作成または更新する。

    同じ guild_id が既に存在する場合は上書きする。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        guild_name: サーバー名
        icon_hash: サーバーアイコンのハッシュ
        member_count: メンバー数 (概算)

    Returns:
        作成または更新された DiscordGuild オブジェクト
    """
    result = await session.execute(
        select(DiscordGuild).where(DiscordGuild.guild_id == guild_id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.guild_name = guild_name
        existing.icon_hash = icon_hash
        existing.member_count = member_count
        await session.commit()
        return existing

    guild = DiscordGuild(
        guild_id=guild_id,
        guild_name=guild_name,
        icon_hash=icon_hash,
        member_count=member_count,
    )
    session.add(guild)
    await session.commit()
    await session.refresh(guild)
    return guild


async def delete_discord_guild(
    session: AsyncSession,
    guild_id: str,
) -> bool:
    """Discord ギルド情報を削除する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        削除できたら True、見つからなければ False
    """
    result = await session.execute(
        select(DiscordGuild).where(DiscordGuild.guild_id == guild_id)
    )
    guild = result.scalar_one_or_none()
    if guild:
        await session.delete(guild)
        await session.commit()
        return True
    return False


async def get_all_discord_guilds(
    session: AsyncSession,
) -> list[DiscordGuild]:
    """全てのキャッシュ済みギルド情報を取得する。

    ギルド名でソートして返す。

    Args:
        session: DB セッション

    Returns:
        DiscordGuild のリスト (ギルド名順)
    """
    result = await session.execute(
        select(DiscordGuild).order_by(DiscordGuild.guild_name)
    )
    return list(result.scalars().all())


# =============================================================================
# DiscordChannel (Discord チャンネルキャッシュ) 操作
# =============================================================================


async def upsert_discord_channel(
    session: AsyncSession,
    guild_id: str,
    channel_id: str,
    channel_name: str,
    channel_type: int = 0,
    position: int = 0,
    category_id: str | None = None,
) -> DiscordChannel:
    """Discord チャンネル情報を作成または更新する。

    同じ guild_id + channel_id の組み合わせが既に存在する場合は上書きする。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        channel_id: Discord チャンネルの ID
        channel_name: チャンネル名
        channel_type: チャンネルタイプ (0=text, 5=news, etc.)
        position: チャンネルの表示順序
        category_id: 親カテゴリの ID

    Returns:
        作成または更新された DiscordChannel オブジェクト
    """
    result = await session.execute(
        select(DiscordChannel).where(
            DiscordChannel.guild_id == guild_id,
            DiscordChannel.channel_id == channel_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.channel_name = channel_name
        existing.channel_type = channel_type
        existing.position = position
        existing.category_id = category_id
        await session.commit()
        return existing

    channel = DiscordChannel(
        guild_id=guild_id,
        channel_id=channel_id,
        channel_name=channel_name,
        channel_type=channel_type,
        position=position,
        category_id=category_id,
    )
    session.add(channel)
    await session.commit()
    await session.refresh(channel)
    return channel


async def delete_discord_channel(
    session: AsyncSession,
    guild_id: str,
    channel_id: str,
) -> bool:
    """Discord チャンネル情報を削除する。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID
        channel_id: Discord チャンネルの ID

    Returns:
        削除できたら True、見つからなければ False
    """
    result = await session.execute(
        select(DiscordChannel).where(
            DiscordChannel.guild_id == guild_id,
            DiscordChannel.channel_id == channel_id,
        )
    )
    channel = result.scalar_one_or_none()
    if channel:
        await session.delete(channel)
        await session.commit()
        return True
    return False


async def delete_discord_channels_by_guild(
    session: AsyncSession,
    guild_id: str,
) -> int:
    """サーバーの全チャンネル情報を削除する。

    Bot がサーバーから退出したときに呼ばれる。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        削除したレコード数
    """
    result = await session.execute(
        delete(DiscordChannel).where(DiscordChannel.guild_id == guild_id)
    )
    await session.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]


async def get_discord_channels_by_guild(
    session: AsyncSession,
    guild_id: str,
) -> list[DiscordChannel]:
    """サーバーの全チャンネル情報を取得する。

    position 順でソートして返す。

    Args:
        session: DB セッション
        guild_id: Discord サーバーの ID

    Returns:
        DiscordChannel のリスト (position 順)
    """
    result = await session.execute(
        select(DiscordChannel)
        .where(DiscordChannel.guild_id == guild_id)
        .order_by(DiscordChannel.position)
    )
    return list(result.scalars().all())


# =============================================================================
# AutoBan (自動 BAN) 操作
# =============================================================================


async def get_all_autoban_rules(
    session: AsyncSession,
) -> list[AutoBanRule]:
    """全 autoban ルールを取得する。"""
    result = await session.execute(
        select(AutoBanRule).order_by(AutoBanRule.guild_id, AutoBanRule.created_at)
    )
    return list(result.scalars().all())


async def get_autoban_rules_by_guild(
    session: AsyncSession, guild_id: str
) -> list[AutoBanRule]:
    """サーバーの全 autoban ルールを取得する。"""
    result = await session.execute(
        select(AutoBanRule).where(AutoBanRule.guild_id == guild_id)
    )
    return list(result.scalars().all())


async def get_enabled_autoban_rules_by_guild(
    session: AsyncSession, guild_id: str
) -> list[AutoBanRule]:
    """サーバーの有効な autoban ルールを取得する。"""
    result = await session.execute(
        select(AutoBanRule).where(
            AutoBanRule.guild_id == guild_id,
            AutoBanRule.is_enabled.is_(True),
        )
    )
    return list(result.scalars().all())


async def get_autoban_rule(session: AsyncSession, rule_id: int) -> AutoBanRule | None:
    """ルール ID から autoban ルールを取得する。"""
    result = await session.execute(select(AutoBanRule).where(AutoBanRule.id == rule_id))
    return result.scalar_one_or_none()


async def create_autoban_rule(
    session: AsyncSession,
    guild_id: str,
    rule_type: str,
    action: str = "ban",
    pattern: str | None = None,
    use_wildcard: bool = False,
    threshold_hours: int | None = None,
    threshold_seconds: int | None = None,
) -> AutoBanRule:
    """新しい autoban ルールを作成する。"""
    rule = AutoBanRule(
        guild_id=guild_id,
        rule_type=rule_type,
        action=action,
        pattern=pattern,
        use_wildcard=use_wildcard,
        threshold_hours=threshold_hours,
        threshold_seconds=threshold_seconds,
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


async def delete_autoban_rule(session: AsyncSession, rule_id: int) -> bool:
    """autoban ルールを削除する。"""
    rule = await get_autoban_rule(session, rule_id)
    if rule:
        await session.delete(rule)
        await session.commit()
        return True
    return False


async def toggle_autoban_rule(session: AsyncSession, rule_id: int) -> bool | None:
    """autoban ルールの有効/無効を切り替える。新しい状態を返す。"""
    rule = await get_autoban_rule(session, rule_id)
    if rule:
        rule.is_enabled = not rule.is_enabled
        await session.commit()
        return rule.is_enabled
    return None


async def update_autoban_rule(
    session: AsyncSession,
    rule: AutoBanRule,
    *,
    action: str | None = None,
    pattern: str | None = None,
    use_wildcard: bool | None = None,
    threshold_hours: int | None = None,
    threshold_seconds: int | None = None,
) -> AutoBanRule:
    """autoban ルールを更新する。None のフィールドは変更しない。"""
    if action is not None:
        rule.action = action
    if pattern is not None:
        rule.pattern = pattern
    if use_wildcard is not None:
        rule.use_wildcard = use_wildcard
    if threshold_hours is not None:
        rule.threshold_hours = threshold_hours
    if threshold_seconds is not None:
        rule.threshold_seconds = threshold_seconds
    await session.commit()
    return rule


async def create_autoban_log(
    session: AsyncSession,
    guild_id: str,
    user_id: str,
    username: str,
    rule_id: int,
    action_taken: str,
    reason: str,
) -> AutoBanLog:
    """autoban 実行ログを作成する。"""
    log = AutoBanLog(
        guild_id=guild_id,
        user_id=user_id,
        username=username,
        rule_id=rule_id,
        action_taken=action_taken,
        reason=reason,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log


async def get_autoban_logs_by_guild(
    session: AsyncSession, guild_id: str, limit: int = 50
) -> list[AutoBanLog]:
    """サーバーの autoban ログを取得する (新しい順)。"""
    result = await session.execute(
        select(AutoBanLog)
        .where(AutoBanLog.guild_id == guild_id)
        .order_by(AutoBanLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_all_autoban_logs(
    session: AsyncSession, limit: int = 100
) -> list[AutoBanLog]:
    """全 autoban ログを取得する (新しい順)。"""
    result = await session.execute(
        select(AutoBanLog).order_by(AutoBanLog.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def get_autoban_config(
    session: AsyncSession, guild_id: str
) -> AutoBanConfig | None:
    """ギルドの autoban 設定を取得する。"""
    result = await session.execute(
        select(AutoBanConfig).where(AutoBanConfig.guild_id == guild_id)
    )
    return result.scalar_one_or_none()


async def upsert_autoban_config(
    session: AsyncSession,
    guild_id: str,
    log_channel_id: str | None,
) -> AutoBanConfig:
    """autoban 設定を作成または更新する。"""
    existing = await get_autoban_config(session, guild_id)

    if existing:
        existing.log_channel_id = log_channel_id
        await session.commit()
        return existing

    config = AutoBanConfig(guild_id=guild_id, log_channel_id=log_channel_id)
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


async def get_all_autoban_configs(session: AsyncSession) -> list[AutoBanConfig]:
    """全 autoban 設定を取得する。"""
    result = await session.execute(select(AutoBanConfig))
    return list(result.scalars().all())


# =============================================================================
# BanLog (BAN ログ) 操作
# =============================================================================


async def create_ban_log(
    session: AsyncSession,
    guild_id: str,
    user_id: str,
    username: str,
    reason: str | None = None,
    is_autoban: bool = False,
) -> BanLog:
    """BAN ログを作成する。"""
    log = BanLog(
        guild_id=guild_id,
        user_id=user_id,
        username=username,
        reason=reason,
        is_autoban=is_autoban,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log


async def get_ban_logs(session: AsyncSession, limit: int = 100) -> list[BanLog]:
    """全 BAN ログを取得する (新しい順)。"""
    result = await session.execute(
        select(BanLog).order_by(BanLog.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


# =============================================================================
# TicketCategory (チケットカテゴリ) 操作
# =============================================================================


async def create_ticket_category(
    session: AsyncSession,
    guild_id: str,
    name: str,
    staff_role_id: str,
    discord_category_id: str | None = None,
    channel_prefix: str = "ticket-",
    form_questions: str | None = None,
    log_channel_id: str | None = None,
) -> TicketCategory:
    """チケットカテゴリを作成する。"""
    category = TicketCategory(
        guild_id=guild_id,
        name=name,
        staff_role_id=staff_role_id,
        discord_category_id=discord_category_id,
        channel_prefix=channel_prefix,
        form_questions=form_questions,
        log_channel_id=log_channel_id,
    )
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


async def get_ticket_category(
    session: AsyncSession, category_id: int
) -> TicketCategory | None:
    """カテゴリ ID からチケットカテゴリを取得する。"""
    result = await session.execute(
        select(TicketCategory).where(TicketCategory.id == category_id)
    )
    return result.scalar_one_or_none()


async def get_ticket_categories_by_guild(
    session: AsyncSession, guild_id: str
) -> list[TicketCategory]:
    """サーバーの全チケットカテゴリを取得する。"""
    result = await session.execute(
        select(TicketCategory).where(TicketCategory.guild_id == guild_id)
    )
    return list(result.scalars().all())


async def get_enabled_ticket_categories_by_guild(
    session: AsyncSession, guild_id: str
) -> list[TicketCategory]:
    """サーバーの有効なチケットカテゴリを取得する。"""
    result = await session.execute(
        select(TicketCategory).where(
            TicketCategory.guild_id == guild_id,
            TicketCategory.is_enabled.is_(True),
        )
    )
    return list(result.scalars().all())


async def delete_ticket_category(session: AsyncSession, category_id: int) -> bool:
    """チケットカテゴリを削除する。関連レコードも CASCADE で削除。"""
    category = await get_ticket_category(session, category_id)
    if category:
        await session.delete(category)
        await session.commit()
        return True
    return False


# =============================================================================
# TicketPanel (チケットパネル) 操作
# =============================================================================


async def create_ticket_panel(
    session: AsyncSession,
    guild_id: str,
    channel_id: str,
    title: str,
    description: str | None = None,
) -> TicketPanel:
    """チケットパネルを作成する。"""
    panel = TicketPanel(
        guild_id=guild_id,
        channel_id=channel_id,
        title=title,
        description=description,
    )
    session.add(panel)
    await session.commit()
    await session.refresh(panel)
    return panel


async def get_ticket_panel(session: AsyncSession, panel_id: int) -> TicketPanel | None:
    """パネル ID からチケットパネルを取得する。"""
    result = await session.execute(
        select(TicketPanel).where(TicketPanel.id == panel_id)
    )
    return result.scalar_one_or_none()


async def get_ticket_panel_by_message_id(
    session: AsyncSession, message_id: str
) -> TicketPanel | None:
    """メッセージ ID からチケットパネルを取得する。"""
    result = await session.execute(
        select(TicketPanel).where(TicketPanel.message_id == message_id)
    )
    return result.scalar_one_or_none()


async def get_all_ticket_panels(session: AsyncSession) -> list[TicketPanel]:
    """全チケットパネルを取得する。"""
    result = await session.execute(select(TicketPanel))
    return list(result.scalars().all())


async def get_ticket_panels_by_guild(
    session: AsyncSession, guild_id: str
) -> list[TicketPanel]:
    """サーバーの全チケットパネルを取得する。"""
    result = await session.execute(
        select(TicketPanel).where(TicketPanel.guild_id == guild_id)
    )
    return list(result.scalars().all())


async def update_ticket_panel(
    session: AsyncSession,
    panel: TicketPanel,
    *,
    message_id: str | None = None,
    title: str | None = None,
    description: str | None = None,
) -> TicketPanel:
    """チケットパネルを更新する。None のフィールドは変更しない。"""
    if message_id is not None:
        panel.message_id = message_id
    if title is not None:
        panel.title = title
    if description is not None:
        panel.description = description
    await session.commit()
    return panel


async def delete_ticket_panel(session: AsyncSession, panel_id: int) -> bool:
    """チケットパネルを削除する。関連レコードも CASCADE で削除。"""
    panel = await get_ticket_panel(session, panel_id)
    if panel:
        await session.delete(panel)
        await session.commit()
        return True
    return False


async def delete_ticket_panel_by_message_id(
    session: AsyncSession, message_id: str
) -> bool:
    """メッセージ ID からチケットパネルを削除する。"""
    panel = await get_ticket_panel_by_message_id(session, message_id)
    if panel:
        await session.delete(panel)
        await session.commit()
        return True
    return False


# =============================================================================
# TicketPanelCategory (パネル-カテゴリ結合) 操作
# =============================================================================


async def add_ticket_panel_category(
    session: AsyncSession,
    panel_id: int,
    category_id: int,
    button_label: str | None = None,
    button_style: str = "primary",
    button_emoji: str | None = None,
) -> TicketPanelCategory:
    """パネルにカテゴリを関連付ける。"""
    # 現在の最大 position を取得
    result = await session.execute(
        select(func.coalesce(func.max(TicketPanelCategory.position), -1)).where(
            TicketPanelCategory.panel_id == panel_id
        )
    )
    next_position = result.scalar_one() + 1

    assoc = TicketPanelCategory(
        panel_id=panel_id,
        category_id=category_id,
        button_label=button_label,
        button_style=button_style,
        button_emoji=button_emoji,
        position=next_position,
    )
    session.add(assoc)
    await session.commit()
    await session.refresh(assoc)
    return assoc


async def get_ticket_panel_categories(
    session: AsyncSession, panel_id: int
) -> list[TicketPanelCategory]:
    """パネルに関連付けられたカテゴリを position 順で取得する。"""
    result = await session.execute(
        select(TicketPanelCategory)
        .where(TicketPanelCategory.panel_id == panel_id)
        .order_by(TicketPanelCategory.position)
    )
    return list(result.scalars().all())


async def remove_ticket_panel_category(
    session: AsyncSession, panel_id: int, category_id: int
) -> bool:
    """パネルからカテゴリの関連付けを削除する。"""
    result = await session.execute(
        select(TicketPanelCategory).where(
            TicketPanelCategory.panel_id == panel_id,
            TicketPanelCategory.category_id == category_id,
        )
    )
    assoc = result.scalar_one_or_none()
    if assoc:
        await session.delete(assoc)
        await session.commit()
        return True
    return False


# =============================================================================
# Ticket (チケット) 操作
# =============================================================================


async def create_ticket(
    session: AsyncSession,
    guild_id: str,
    user_id: str,
    username: str,
    category_id: int,
    channel_id: str,
    ticket_number: int,
    form_answers: str | None = None,
) -> Ticket:
    """チケットを作成する。"""
    ticket = Ticket(
        guild_id=guild_id,
        user_id=user_id,
        username=username,
        category_id=category_id,
        channel_id=channel_id,
        ticket_number=ticket_number,
        form_answers=form_answers,
    )
    session.add(ticket)
    await session.commit()
    await session.refresh(ticket)
    return ticket


async def get_ticket(session: AsyncSession, ticket_id: int) -> Ticket | None:
    """チケット ID からチケットを取得する。"""
    result = await session.execute(select(Ticket).where(Ticket.id == ticket_id))
    return result.scalar_one_or_none()


async def get_ticket_by_channel_id(
    session: AsyncSession, channel_id: str
) -> Ticket | None:
    """チャンネル ID からチケットを取得する。"""
    result = await session.execute(
        select(Ticket).where(Ticket.channel_id == channel_id)
    )
    return result.scalar_one_or_none()


async def get_tickets_by_guild(
    session: AsyncSession,
    guild_id: str,
    status: str | None = None,
    limit: int = 100,
) -> list[Ticket]:
    """サーバーのチケットを取得する (新しい順)。"""
    query = select(Ticket).where(Ticket.guild_id == guild_id)
    if status is not None:
        query = query.where(Ticket.status == status)
    query = query.order_by(Ticket.created_at.desc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_all_tickets(
    session: AsyncSession,
    status: str | None = None,
    limit: int = 100,
) -> list[Ticket]:
    """全チケットを取得する (新しい順)。"""
    query = select(Ticket)
    if status is not None:
        query = query.where(Ticket.status == status)
    query = query.order_by(Ticket.created_at.desc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_next_ticket_number(session: AsyncSession, guild_id: str) -> int:
    """ギルドの次のチケット番号を取得する。"""
    result = await session.execute(
        select(func.max(Ticket.ticket_number)).where(Ticket.guild_id == guild_id)
    )
    max_number = result.scalar_one_or_none()
    return (max_number or 0) + 1


_UNSET: object = object()


async def update_ticket_status(
    session: AsyncSession,
    ticket: Ticket,
    *,
    status: str | None = None,
    claimed_by: str | None = None,
    closed_by: str | None = None,
    close_reason: str | None = None,
    transcript: str | None = None,
    closed_at: datetime | None = None,
    channel_id: str | None | object = _UNSET,
) -> Ticket:
    """チケットのステータスを更新する。None のフィールドは変更しない。

    channel_id はデフォルト値 _UNSET (sentinel) を使い、
    明示的に None を渡した場合のみ None に設定する。
    """
    if status is not None:
        ticket.status = status
    if claimed_by is not None:
        ticket.claimed_by = claimed_by
    if closed_by is not None:
        ticket.closed_by = closed_by
    if close_reason is not None:
        ticket.close_reason = close_reason
    if transcript is not None:
        ticket.transcript = transcript
    if closed_at is not None:
        ticket.closed_at = closed_at
    if channel_id is not _UNSET:
        ticket.channel_id = channel_id  # type: ignore[assignment]
    await session.commit()
    return ticket


# =============================================================================
# JoinRole (自動ロール付与) 操作
# =============================================================================


async def create_join_role_config(
    session: AsyncSession,
    guild_id: str,
    role_id: str,
    duration_hours: int,
) -> JoinRoleConfig:
    """JoinRole 設定を作成する。"""
    config = JoinRoleConfig(
        guild_id=guild_id,
        role_id=role_id,
        duration_hours=duration_hours,
    )
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


async def get_join_role_configs(
    session: AsyncSession, guild_id: str | None = None
) -> list[JoinRoleConfig]:
    """JoinRole 設定を取得する。guild_id 指定で絞り込み。"""
    stmt = select(JoinRoleConfig).order_by(JoinRoleConfig.id)
    if guild_id is not None:
        stmt = stmt.where(JoinRoleConfig.guild_id == guild_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_enabled_join_role_configs(
    session: AsyncSession, guild_id: str
) -> list[JoinRoleConfig]:
    """指定ギルドの有効な JoinRole 設定を取得する。"""
    stmt = (
        select(JoinRoleConfig)
        .where(JoinRoleConfig.guild_id == guild_id, JoinRoleConfig.enabled.is_(True))
        .order_by(JoinRoleConfig.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_join_role_config(session: AsyncSession, config_id: int) -> bool:
    """JoinRole 設定を削除する。"""
    stmt = delete(JoinRoleConfig).where(JoinRoleConfig.id == config_id)
    result = await session.execute(stmt)
    await session.commit()
    return int(result.rowcount) > 0  # type: ignore[attr-defined]


async def toggle_join_role_config(
    session: AsyncSession, config_id: int
) -> JoinRoleConfig | None:
    """JoinRole 設定の有効/無効を切り替える。"""
    stmt = select(JoinRoleConfig).where(JoinRoleConfig.id == config_id)
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()
    if config is None:
        return None
    config.enabled = not config.enabled
    await session.commit()
    await session.refresh(config)
    return config


async def create_join_role_assignment(
    session: AsyncSession,
    guild_id: str,
    user_id: str,
    role_id: str,
    assigned_at: datetime,
    expires_at: datetime,
) -> JoinRoleAssignment:
    """JoinRole 付与レコードを作成する。"""
    assignment = JoinRoleAssignment(
        guild_id=guild_id,
        user_id=user_id,
        role_id=role_id,
        assigned_at=assigned_at,
        expires_at=expires_at,
    )
    session.add(assignment)
    await session.commit()
    await session.refresh(assignment)
    return assignment


async def get_expired_join_role_assignments(
    session: AsyncSession, now: datetime
) -> list[JoinRoleAssignment]:
    """期限切れの JoinRole 付与レコードを取得する。"""
    stmt = (
        select(JoinRoleAssignment)
        .where(JoinRoleAssignment.expires_at <= now)
        .order_by(JoinRoleAssignment.expires_at)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_join_role_assignment(
    session: AsyncSession, assignment_id: int
) -> bool:
    """JoinRole 付与レコードを削除する。"""
    stmt = delete(JoinRoleAssignment).where(JoinRoleAssignment.id == assignment_id)
    result = await session.execute(stmt)
    await session.commit()
    return int(result.rowcount) > 0  # type: ignore[attr-defined]
