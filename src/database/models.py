"""SQLAlchemy database models.

データベースのテーブル構造を Python クラスで定義する。
SQLAlchemy の ORM (Object Relational Mapper) を使い、
Python オブジェクトとしてデータベースの行を操作できる。

テーブル構成:
    - admin_users: Web 管理画面のログインユーザー
    - lobbies: ロビーVC の設定 (どのチャンネルがロビーか)
    - voice_sessions: 現在アクティブな一時 VC のセッション情報
    - voice_session_members: 一時 VC の参加メンバー
    - bump_reminders: bump リマインダー
    - bump_configs: bump 監視の設定 (ギルドごと)
    - sticky_messages: sticky メッセージの設定 (チャンネルごと)

Examples:
    モデルの使用例::

        from src.database.models import Lobby, VoiceSession

        # ロビーを作成
        lobby = Lobby(
            guild_id="123456789",
            lobby_channel_id="987654321",
        )

        # セッションを作成
        session = VoiceSession(
            lobby_id=lobby.id,
            channel_id="111222333",
            owner_id="444555666",
            name="ゲーム部屋",
        )

See Also:
    - :mod:`src.services.db_service`: CRUD 操作関数
    - :mod:`src.database.engine`: データベース接続設定
    - SQLAlchemy ORM: https://docs.sqlalchemy.org/en/20/orm/
"""

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    validates,
)


def _validate_discord_id(value: str, field_name: str) -> str:
    """Discord ID (数字文字列) のバリデーション。"""
    if not isinstance(value, str) or not value.isdigit():
        msg = f"{field_name} must be a digit string, got: {value!r}"
        raise ValueError(msg)
    return value


class Base(DeclarativeBase):
    """全モデルの基底クラス。

    SQLAlchemy の DeclarativeBase を継承する。全てのテーブルクラスは
    この Base を継承することで、SQLAlchemy に「これはテーブル定義だよ」
    と認識される。

    Notes:
        - この Base.metadata を使用してテーブルを作成・削除する
        - Alembic マイグレーションもこの Base を参照する

    Examples:
        モデルクラスの定義::

            class MyTable(Base):
                __tablename__ = "my_table"

                id: Mapped[int] = mapped_column(Integer, primary_key=True)
                name: Mapped[str] = mapped_column(String, nullable=False)

    See Also:
        - :func:`src.database.engine.init_db`: テーブル初期化関数
        - SQLAlchemy DeclarativeBase: https://docs.sqlalchemy.org/en/20/orm/mapping_api.html
    """

    pass


class AdminUser(Base):
    """Web 管理画面のログインユーザーテーブル。

    管理画面へのログインに使用する認証情報を保存する。
    パスワードは bcrypt でハッシュ化して保存する。

    Attributes:
        id (int): 自動採番の主キー。
        email (str): ログイン用メールアドレス (ユニーク)。
        password_hash (str): bcrypt でハッシュ化されたパスワード。
        created_at (datetime): ユーザー作成日時 (UTC)。
        updated_at (datetime): 最終更新日時 (UTC)。
        password_changed_at (datetime | None): パスワード変更日時。
            None なら初期パスワードのまま。
        reset_token (str | None): パスワードリセット用トークン。
        reset_token_expires_at (datetime | None): リセットトークンの有効期限。
        pending_email (str | None): 確認待ちの新しいメールアドレス。
        email_change_token (str | None): メールアドレス変更確認用トークン。
        email_change_token_expires_at (datetime | None): メール変更トークンの有効期限。
        email_verified (bool): メールアドレスが確認済みかどうか。

    Notes:
        - テーブル名: ``admin_users``
        - email はユニーク制約あり
        - パスワードは平文で保存せず、必ずハッシュ化する

    Examples:
        新規ユーザー作成::

            import bcrypt

            user = AdminUser(
                email="admin@example.com",
                password_hash=bcrypt.hashpw(b"password", bcrypt.gensalt()).decode(),
            )

    See Also:
        - :mod:`src.web.auth`: 認証ロジック
    """

    __tablename__ = "admin_users"

    # id: 自動採番の主キー
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # email: ログイン用メールアドレス (ユニーク)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    # password_hash: bcrypt でハッシュ化されたパスワード
    password_hash: Mapped[str] = mapped_column(String, nullable=False)

    # created_at: ユーザー作成日時 (UTC)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    # updated_at: 最終更新日時 (UTC)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # password_changed_at: パスワード変更日時 (None なら初期パスワードのまま)
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # reset_token: パスワードリセット用トークン
    reset_token: Mapped[str | None] = mapped_column(String, nullable=True, default=None)

    # reset_token_expires_at: リセットトークンの有効期限
    reset_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # pending_email: 確認待ちの新しいメールアドレス
    pending_email: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None
    )

    # email_change_token: メールアドレス変更確認用トークン
    email_change_token: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None
    )

    # email_change_token_expires_at: メール変更トークンの有効期限
    email_change_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # email_verified: メールアドレスが確認済みかどうか (初回セットアップ用)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return f"<AdminUser(id={self.id}, email={self.email})>"


class Lobby(Base):
    """ロビーVC の設定テーブル。

    ロビーVC = ユーザーが参加すると一時 VC が自動作成されるチャンネル。
    1つのサーバー (guild) に複数のロビーを設定できる。

    Attributes:
        id (int): 自動採番の主キー。
        guild_id (str): Discord サーバーの ID。インデックス付き。
        lobby_channel_id (str): ロビーとして使う VC の ID。
            ユニーク制約あり。
        category_id (str | None): 作成された一時 VC を配置するカテゴリの ID。
            None の場合はロビーと同じカテゴリに配置。
        default_user_limit (int): 一時 VC のデフォルト人数制限。0 = 無制限。
        sessions (list[VoiceSession]): このロビーから作成された VC セッション一覧。

    Notes:
        - テーブル名: ``lobbies``
        - lobby_channel_id はユニーク (同じチャンネルを重複登録不可)
        - sessions はカスケード削除設定 (ロビー削除時にセッションも削除)

    Examples:
        ロビー作成::

            lobby = Lobby(
                guild_id="123456789",
                lobby_channel_id="987654321",
                default_user_limit=10,
            )

    See Also:
        - :class:`VoiceSession`: 一時 VC セッション
        - :func:`src.services.db_service.create_lobby`: ロビー作成関数
    """

    __tablename__ = "lobbies"

    # id: 自動採番の主キー。SQLAlchemy が自動で管理する
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # guild_id: Discord サーバーの ID。index=True で検索を高速化
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # lobby_channel_id: ロビーとして使う VC の ID。
    # unique=True で同じチャンネルを重複登録できないようにする
    lobby_channel_id: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )

    # category_id: 作成された一時 VC を配置するカテゴリの ID (任意)
    # None の場合はロビーと同じカテゴリに配置される
    category_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # default_user_limit: 一時 VC のデフォルト人数制限。0 = 無制限
    default_user_limit: Mapped[int] = mapped_column(Integer, default=0)

    # --- リレーション ---
    # このロビーから作成された VoiceSession の一覧。
    # cascade="all, delete-orphan" → ロビーを削除すると関連セッションも削除される
    sessions: Mapped[list["VoiceSession"]] = relationship(
        "VoiceSession", back_populates="lobby", cascade="all, delete-orphan"
    )

    @validates("guild_id", "lobby_channel_id")
    def _validate_ids(self, key: str, value: str) -> str:
        return _validate_discord_id(value, key)

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。print() や logger で表示される。"""
        return (
            f"<Lobby(id={self.id}, guild_id={self.guild_id}, "
            f"channel_id={self.lobby_channel_id})>"
        )


class VoiceSession(Base):
    """現在アクティブな一時 VC のセッション情報テーブル。

    ユーザーがロビーに参加するとレコードが作成され、
    全員が退出するとレコードが削除される。
    ロック状態や非表示状態などの設定もここに保存する。

    Attributes:
        id (int): 自動採番の主キー。
        lobby_id (int): 親ロビーへの外部キー。
        channel_id (str): 作成された一時 VC の Discord チャンネル ID。
            ユニーク制約あり。
        owner_id (str): チャンネルオーナーの Discord ユーザー ID。
        name (str): チャンネル名。
        user_limit (int): VC の人数制限。0 = 無制限。
        is_locked (bool): True ならチャンネルがロック (@everyone の接続拒否)。
        is_hidden (bool): True ならチャンネルが非表示 (@everyone のチャンネル表示拒否)。
        created_at (datetime): レコード作成日時 (UTC)。
        lobby (Lobby): この VC セッションが属する親ロビー。

    Notes:
        - テーブル名: ``voice_sessions``
        - channel_id はユニーク (同じチャンネルの重複レコード防止)
        - オーナーだけがコントロールパネルを操作可能
        - 全員退出時に自動削除される

    Examples:
        セッション作成::

            session = VoiceSession(
                lobby_id=1,
                channel_id="111222333",
                owner_id="444555666",
                name="ゲーム部屋",
                user_limit=5,
            )

    See Also:
        - :class:`Lobby`: 親ロビー
        - :class:`VoiceSessionMember`: 参加メンバー
        - :func:`src.services.db_service.create_voice_session`: 作成関数
    """

    __tablename__ = "voice_sessions"

    # id: 自動採番の主キー
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # lobby_id: 親ロビーへの外部キー。
    # ForeignKey("lobbies.id") で lobbies テーブルの id カラムを参照
    lobby_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lobbies.id"), nullable=False
    )

    # channel_id: 作成された一時 VC の Discord チャンネル ID
    # unique=True で同じチャンネルの重複レコードを防ぐ
    channel_id: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )

    # owner_id: チャンネルオーナーの Discord ユーザー ID
    # オーナーだけがコントロールパネルを操作できる
    owner_id: Mapped[str] = mapped_column(String, nullable=False)

    # name: チャンネル名 (例: "ユーザー名's channel")
    name: Mapped[str] = mapped_column(String, nullable=False)

    # user_limit: VC の人数制限。0 = 無制限
    user_limit: Mapped[int] = mapped_column(Integer, default=0)

    # is_locked: True ならチャンネルがロックされている (@everyone の接続を拒否)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)

    # is_hidden: True ならチャンネルが非表示 (@everyone のチャンネル表示を拒否)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)

    # created_at: レコード作成日時 (UTC)。自動で現在時刻がセットされる
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    # --- リレーション ---
    # この VC セッションが属する親ロビー。lobby.sessions の逆方向
    lobby: Mapped["Lobby"] = relationship("Lobby", back_populates="sessions")

    @validates("channel_id", "owner_id")
    def _validate_ids(self, key: str, value: str) -> str:
        return _validate_discord_id(value, key)

    @validates("user_limit")
    def _validate_user_limit(self, _key: str, value: int) -> int:
        if value < 0:
            msg = f"user_limit must be >= 0, got: {value}"
            raise ValueError(msg)
        return value

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<VoiceSession(id={self.id}, channel_id={self.channel_id}, "
            f"owner_id={self.owner_id})>"
        )


class VoiceSessionMember(Base):
    """一時 VC に参加しているメンバーの情報テーブル。

    各メンバーの参加時刻を記録し、オーナー引き継ぎ時の優先順位を決定する。
    Bot 再起動後も参加順序が保持される。

    Attributes:
        id (int): 自動採番の主キー。
        voice_session_id (int): 親 VoiceSession への外部キー。
            カスケード削除設定。
        user_id (str): メンバーの Discord ユーザー ID。インデックス付き。
        joined_at (datetime): メンバーがこの VC に参加した日時 (UTC)。

    Notes:
        - テーブル名: ``voice_session_members``
        - (voice_session_id, user_id) でユニーク制約
        - オーナー退出時、最も古い joined_at のメンバーが次のオーナーになる
        - VoiceSession 削除時に自動削除 (CASCADE)

    Examples:
        メンバー追加::

            member = VoiceSessionMember(
                voice_session_id=1,
                user_id="123456789",
            )

    See Also:
        - :class:`VoiceSession`: 親セッション
        - :func:`src.services.db_service.add_voice_session_member`: 追加関数
        - :func:`src.services.db_service.get_voice_session_members_ordered`: 参加順取得
    """

    __tablename__ = "voice_session_members"
    __table_args__ = (
        # 同じ VC セッションに同じユーザーは 1 回だけ
        UniqueConstraint("voice_session_id", "user_id", name="uq_session_user"),
    )

    # id: 自動採番の主キー
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # voice_session_id: 親 VoiceSession への外部キー
    voice_session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("voice_sessions.id", ondelete="CASCADE"), nullable=False
    )

    # user_id: メンバーの Discord ユーザー ID
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # joined_at: メンバーがこの VC に参加した日時 (UTC)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<VoiceSessionMember(id={self.id}, session_id={self.voice_session_id}, "
            f"user_id={self.user_id}, joined_at={self.joined_at})>"
        )


class BumpReminder(Base):
    """bump リマインダーテーブル。

    DISBOARD/ディス速報の bump 後、2時間後にリマインドを送信するための情報を保存。
    同じサーバー・サービスの組み合わせで1件のみ保持 (上書き更新)。

    Attributes:
        id (int): 自動採番の主キー。
        guild_id (str): Discord サーバーの ID。インデックス付き。
        channel_id (str): bump 通知を送信するチャンネルの ID。
        service_name (str): サービス名 ("DISBOARD" または "ディス速報")。
        remind_at (datetime | None): リマインドを送信する予定時刻 (UTC)。
            None なら未設定。
        is_enabled (bool): 通知が有効かどうか (デフォルト True)。
        role_id (str | None): 通知先ロールの ID。
            None の場合は "Server Bumper" ロールを自動検索。

    Notes:
        - テーブル名: ``bump_reminders``
        - (guild_id, service_name) でユニーク制約
        - bump 検知後、remind_at に 2時間後を設定
        - リマインド送信後、remind_at は None にリセット

    Examples:
        リマインダー作成::

            from datetime import UTC, datetime, timedelta

            reminder = BumpReminder(
                guild_id="123456789",
                channel_id="987654321",
                service_name="DISBOARD",
                remind_at=datetime.now(UTC) + timedelta(hours=2),
            )

    See Also:
        - :class:`BumpConfig`: bump 監視設定
        - :func:`src.services.db_service.upsert_bump_reminder`: 作成/更新関数
        - :mod:`src.cogs.bump`: bump 検知 Cog
    """

    __tablename__ = "bump_reminders"
    __table_args__ = (
        # 同じ guild + service の組み合わせは 1 件のみ
        UniqueConstraint("guild_id", "service_name", name="uq_guild_service"),
    )

    # id: 自動採番の主キー
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # guild_id: Discord サーバーの ID
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # channel_id: bump 通知を送信するチャンネルの ID
    channel_id: Mapped[str] = mapped_column(String, nullable=False)

    # service_name: サービス名 ("DISBOARD" または "ディス速報")
    service_name: Mapped[str] = mapped_column(String, nullable=False)

    # remind_at: リマインドを送信する予定時刻 (UTC)、None なら未設定
    remind_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # is_enabled: 通知が有効かどうか (デフォルト True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # role_id: 通知先ロールの ID (None の場合はデフォルトの "Server Bumper" ロール)
    role_id: Mapped[str | None] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<BumpReminder(id={self.id}, guild_id={self.guild_id}, "
            f"service={self.service_name}, remind_at={self.remind_at}, "
            f"is_enabled={self.is_enabled}, role_id={self.role_id})>"
        )


class BumpConfig(Base):
    """bump 監視の設定テーブル。

    ギルドごとに bump を監視するチャンネルを設定する。
    管理者が /bump setup コマンドで設定する。

    Attributes:
        guild_id (str): Discord サーバーの ID (主キー、1ギルド1設定)。
        channel_id (str): bump を監視するチャンネルの ID。
            リマインドもここに送信する。
        created_at (datetime): 設定作成日時 (UTC)。

    Notes:
        - テーブル名: ``bump_configs``
        - guild_id が主キー (1ギルドにつき1設定のみ)
        - /bump setup で設定、/bump disable で削除

    Examples:
        設定作成::

            config = BumpConfig(
                guild_id="123456789",
                channel_id="987654321",
            )

    See Also:
        - :class:`BumpReminder`: 個別のリマインダー
        - :func:`src.services.db_service.upsert_bump_config`: 作成/更新関数
    """

    __tablename__ = "bump_configs"

    # guild_id: Discord サーバーの ID (主キー、1ギルド1設定)
    guild_id: Mapped[str] = mapped_column(String, primary_key=True)

    # channel_id: bump を監視するチャンネルの ID (リマインドもここに送信)
    channel_id: Mapped[str] = mapped_column(String, nullable=False)

    # created_at: 設定作成日時 (UTC)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return f"<BumpConfig(guild_id={self.guild_id}, channel_id={self.channel_id})>"


class StickyMessage(Base):
    """sticky メッセージの設定テーブル。

    チャンネルごとに常に最新位置に表示される embed メッセージを設定する。
    新しいメッセージが投稿されると、古い sticky を削除して再投稿する。

    Attributes:
        channel_id (str): チャンネルの ID (主キー、1チャンネル1設定)。
        guild_id (str): Discord サーバーの ID。インデックス付き。
        message_id (str | None): 現在投稿されている sticky メッセージの ID。
            削除時に使用。
        message_type (str): メッセージの種類 ("embed" または "text")。
        title (str): embed のタイトル (text の場合は空文字)。
        description (str): embed の説明文。
        color (int | None): embed の色 (16進数の整数値、例: 0x00FF00)。
        cooldown_seconds (int): 再投稿までの最小間隔 (秒)。
        last_posted_at (datetime | None): 最後に sticky を投稿した日時。
            cooldown 計算用。
        created_at (datetime): 設定作成日時 (UTC)。

    Notes:
        - テーブル名: ``sticky_messages``
        - channel_id が主キー (1チャンネルにつき1設定のみ)
        - cooldown でスパム防止 (短時間での連続再投稿を防ぐ)
        - message_type で embed/text の切り替えが可能

    Examples:
        sticky メッセージ作成::

            sticky = StickyMessage(
                channel_id="123456789",
                guild_id="987654321",
                title="ルール",
                description="このチャンネルのルールです。",
                color=0x00FF00,
                cooldown_seconds=10,
            )

    See Also:
        - :func:`src.services.db_service.create_sticky_message`: 作成関数
        - :mod:`src.cogs.sticky`: sticky メッセージ Cog
    """

    __tablename__ = "sticky_messages"

    # channel_id: チャンネルの ID (主キー、1チャンネル1設定)
    channel_id: Mapped[str] = mapped_column(String, primary_key=True)

    # guild_id: Discord サーバーの ID
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # message_id: 現在投稿されている sticky メッセージの ID (削除用)
    message_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # message_type: メッセージの種類 ("embed" または "text")
    message_type: Mapped[str] = mapped_column(String, default="embed", nullable=False)

    # title: embed のタイトル (text の場合は空文字)
    title: Mapped[str] = mapped_column(String, nullable=False)

    # description: embed の説明文
    description: Mapped[str] = mapped_column(String, nullable=False)

    # color: embed の色 (16進数の整数値、例: 0x00FF00)
    color: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # cooldown_seconds: 再投稿までの最小間隔 (秒)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    # last_posted_at: 最後に sticky を投稿した日時 (cooldown 計算用)
    last_posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # created_at: 設定作成日時 (UTC)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    @validates("color")
    def _validate_color(self, _key: str, value: int | None) -> int | None:
        if value is not None and not (0 <= value <= 0xFFFFFF):
            msg = f"color must be 0-0xFFFFFF, got: {value}"
            raise ValueError(msg)
        return value

    @validates("cooldown_seconds")
    def _validate_cooldown(self, _key: str, value: int) -> int:
        if value < 0:
            msg = f"cooldown_seconds must be >= 0, got: {value}"
            raise ValueError(msg)
        return value

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<StickyMessage(channel_id={self.channel_id}, "
            f"guild_id={self.guild_id}, title={self.title})>"
        )


class RolePanel(Base):
    """ロールパネルの設定テーブル。

    ボタンまたはリアクションをクリックしてロールを付与/解除できるパネル。
    1つのパネルに複数のロールボタン/リアクションを設定可能。

    Attributes:
        id (int): 自動採番の主キー。
        guild_id (str): Discord サーバーの ID。インデックス付き。
        channel_id (str): パネルを送信したチャンネルの ID。
        message_id (str | None): パネルメッセージの ID。
        panel_type (str): パネルの種類 ("button" または "reaction")。
        title (str): パネルのタイトル。
        description (str | None): パネルの説明文。
        color (int | None): Embed の色 (16進数の整数値)。
        remove_reaction (bool): リアクション自動削除フラグ (リアクション式のみ)。
            True の場合、ユーザーがリアクションするとロールをトグルし、
            リアクションを自動削除してカウントを 1 に保つ。
        use_embed (bool): メッセージ形式フラグ。
            True の場合は Embed 形式、False の場合は通常テキストメッセージ。
        created_at (datetime): 作成日時 (UTC)。
        items (list[RolePanelItem]): このパネルに設定されたロール一覧。

    Notes:
        - テーブル名: ``role_panels``
        - panel_type で動作が切り替わる (ボタン式/リアクション式)
        - items はカスケード削除設定 (パネル削除時にアイテムも削除)
        - remove_reaction=True: リアクション追加でトグル、リアクション自動削除
        - remove_reaction=False: リアクション追加で付与、削除で解除 (通常動作)

    Examples:
        パネル作成::

            panel = RolePanel(
                guild_id="123456789",
                channel_id="987654321",
                panel_type="button",
                title="ロール選択",
                description="好きなロールを選んでください",
            )

    See Also:
        - :class:`RolePanelItem`: パネルに設定されたロール
        - :mod:`src.cogs.role_panel`: ロールパネル Cog
    """

    __tablename__ = "role_panels"

    # id: 自動採番の主キー
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # guild_id: Discord サーバーの ID
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # channel_id: パネルを送信したチャンネルの ID
    channel_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # message_id: パネルメッセージの ID (送信後に設定)
    message_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    # panel_type: パネルの種類 ("button" または "reaction")
    panel_type: Mapped[str] = mapped_column(String, nullable=False)

    # title: パネルのタイトル
    title: Mapped[str] = mapped_column(String, nullable=False)

    # description: パネルの説明文
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    # color: Embed の色 (16進数の整数値)
    color: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # remove_reaction: リアクション自動削除フラグ
    # True: リアクション追加でトグル、リアクション自動削除 (カウント常に 1)
    # False: リアクション追加で付与、削除で解除 (通常動作)
    remove_reaction: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # use_embed: メッセージ形式フラグ
    # True: Embed 形式 (カラー、フィールド付き)
    # False: 通常テキストメッセージ形式
    use_embed: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="1"
    )

    # created_at: 作成日時 (UTC)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    # --- リレーション ---
    # このパネルに設定されたロール一覧
    items: Mapped[list["RolePanelItem"]] = relationship(
        "RolePanelItem", back_populates="panel", cascade="all, delete-orphan"
    )

    @validates("color")
    def _validate_color(self, _key: str, value: int | None) -> int | None:
        if value is not None and not (0 <= value <= 0xFFFFFF):
            msg = f"color must be 0-0xFFFFFF, got: {value}"
            raise ValueError(msg)
        return value

    @validates("panel_type")
    def _validate_panel_type(self, _key: str, value: str) -> str:
        if value not in ("button", "reaction"):
            msg = f"panel_type must be 'button' or 'reaction', got: {value!r}"
            raise ValueError(msg)
        return value

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<RolePanel(id={self.id}, guild_id={self.guild_id}, "
            f"title={self.title}, type={self.panel_type})>"
        )


class DiscordRole(Base):
    """Discord ロール情報のキャッシュテーブル。

    Bot が参加しているサーバーのロール情報を保存し、
    Web 管理画面でロール名をセレクトボックスで選択できるようにする。
    Bot 起動時、サーバー参加時、ロール変更時に同期される。

    Attributes:
        id (int): 自動採番の主キー。
        guild_id (str): Discord サーバーの ID。インデックス付き。
        role_id (str): Discord ロールの ID。
        role_name (str): ロール名。
        color (int): ロールの色 (16進数の整数値)。
        position (int): ロールの表示順序 (高いほど上)。
        updated_at (datetime): 最終更新日時 (UTC)。

    Notes:
        - テーブル名: ``discord_roles``
        - (guild_id, role_id) でユニーク制約
        - Bot が起動時に全ギルドのロールを同期
        - ロール作成/更新/削除イベントで自動更新

    Examples:
        ロール情報保存::

            role = DiscordRole(
                guild_id="123456789",
                role_id="987654321",
                role_name="Member",
                color=0x00FF00,
                position=5,
            )

    See Also:
        - :mod:`src.cogs.role_panel`: ロールパネル Cog
        - :mod:`src.web.app`: Web 管理画面
    """

    __tablename__ = "discord_roles"
    __table_args__ = (
        # 同じギルドに同じロール ID は 1 件のみ
        UniqueConstraint("guild_id", "role_id", name="uq_guild_role"),
    )

    # id: 自動採番の主キー
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # guild_id: Discord サーバーの ID
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # role_id: Discord ロールの ID
    role_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # role_name: ロール名
    role_name: Mapped[str] = mapped_column(String, nullable=False)

    # color: ロールの色 (16進数の整数値)
    color: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # position: ロールの表示順序 (高いほど上)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # updated_at: 最終更新日時 (UTC)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<DiscordRole(id={self.id}, guild_id={self.guild_id}, "
            f"role_id={self.role_id}, name={self.role_name})>"
        )


class DiscordGuild(Base):
    """Discord ギルド情報のキャッシュテーブル。

    Bot が参加しているサーバーの情報を保存し、
    Web 管理画面でギルド名を表示できるようにする。
    Bot 起動時、サーバー参加時、サーバー情報変更時に同期される。

    Attributes:
        guild_id (str): Discord サーバーの ID (主キー)。
        guild_name (str): サーバー名。
        icon_hash (str | None): サーバーアイコンのハッシュ。
        member_count (int): メンバー数 (概算)。
        updated_at (datetime): 最終更新日時 (UTC)。

    Notes:
        - テーブル名: ``discord_guilds``
        - guild_id が主キー (1ギルド1レコード)
        - Bot 起動時に全ギルドを同期
        - ギルド更新イベントで自動更新

    Examples:
        ギルド情報保存::

            guild = DiscordGuild(
                guild_id="123456789",
                guild_name="My Server",
                member_count=100,
            )

    See Also:
        - :mod:`src.cogs.role_panel`: ロールパネル Cog
        - :mod:`src.web.app`: Web 管理画面
    """

    __tablename__ = "discord_guilds"

    # guild_id: Discord サーバーの ID (主キー)
    guild_id: Mapped[str] = mapped_column(String, primary_key=True)

    # guild_name: サーバー名
    guild_name: Mapped[str] = mapped_column(String, nullable=False)

    # icon_hash: サーバーアイコンのハッシュ (URL 生成用、None ならデフォルト)
    icon_hash: Mapped[str | None] = mapped_column(String, nullable=True)

    # member_count: メンバー数 (概算、正確ではない場合あり)
    member_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # updated_at: 最終更新日時 (UTC)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return f"<DiscordGuild(guild_id={self.guild_id}, name={self.guild_name})>"


class DiscordChannel(Base):
    """Discord チャンネル情報のキャッシュテーブル。

    Bot が参加しているサーバーのチャンネル情報を保存し、
    Web 管理画面でチャンネル名を表示できるようにする。

    Attributes:
        id (int): 自動採番の主キー。
        guild_id (str): Discord サーバーの ID。インデックス付き。
        channel_id (str): Discord チャンネルの ID。
        channel_name (str): チャンネル名。
        channel_type (int): チャンネルタイプ
            (0=text, 2=voice, 4=category, 5=news, 15=forum)。
        position (int): チャンネルの表示順序。
        category_id (str | None): 親カテゴリの ID。
        updated_at (datetime): 最終更新日時 (UTC)。

    Notes:
        - テーブル名: ``discord_channels``
        - (guild_id, channel_id) でユニーク制約
        - テキスト/ボイス/カテゴリ/アナウンス/フォーラム (type 0, 2, 4, 5, 15) を同期
        - チャンネル作成/更新/削除イベントで自動更新

    Examples:
        チャンネル情報保存::

            channel = DiscordChannel(
                guild_id="123456789",
                channel_id="987654321",
                channel_name="general",
                channel_type=0,
                position=1,
            )

    See Also:
        - :mod:`src.cogs.role_panel`: ロールパネル Cog
        - :mod:`src.web.app`: Web 管理画面
    """

    __tablename__ = "discord_channels"
    __table_args__ = (
        # 同じギルドに同じチャンネル ID は 1 件のみ
        UniqueConstraint("guild_id", "channel_id", name="uq_guild_channel"),
    )

    # id: 自動採番の主キー
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # guild_id: Discord サーバーの ID
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # channel_id: Discord チャンネルの ID
    channel_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # channel_name: チャンネル名
    channel_name: Mapped[str] = mapped_column(String, nullable=False)

    # channel_type: チャンネルタイプ (discord.ChannelType の値)
    # 0=text, 5=news, 15=forum
    channel_type: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # position: チャンネルの表示順序
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # category_id: 親カテゴリの ID (None ならカテゴリなし)
    category_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # updated_at: 最終更新日時 (UTC)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<DiscordChannel(id={self.id}, guild_id={self.guild_id}, "
            f"channel_id={self.channel_id}, name={self.channel_name})>"
        )


class RolePanelItem(Base):
    """ロールパネルに設定されたロールのテーブル。

    パネルに追加された各ロールの設定を保存する。
    ボタン式の場合はラベルとスタイル、リアクション式の場合は絵文字を使用。

    Attributes:
        id (int): 自動採番の主キー。
        panel_id (int): 親パネルへの外部キー。カスケード削除設定。
        role_id (str): 付与するロールの Discord ID。
        emoji (str): ボタン/リアクションに使用する絵文字。
        label (str | None): ボタンのラベル (ボタン式のみ)。
        style (str): ボタンのスタイル ("primary", "secondary", "success", "danger")。
        position (int): 表示順序。

    Notes:
        - テーブル名: ``role_panel_items``
        - (panel_id, emoji) でユニーク制約 (同じ絵文字の重複防止)
        - RolePanel 削除時に自動削除 (CASCADE)

    Examples:
        ロール追加::

            item = RolePanelItem(
                panel_id=1,
                role_id="111222333",
                emoji="🎮",
                label="ゲーマー",
                style="primary",
                position=0,
            )

    See Also:
        - :class:`RolePanel`: 親パネル
        - :func:`src.services.db_service.add_role_panel_item`: 追加関数
    """

    __tablename__ = "role_panel_items"
    __table_args__ = (
        # 同じパネルに同じ絵文字は 1 回だけ
        UniqueConstraint("panel_id", "emoji", name="uq_panel_emoji"),
    )

    # id: 自動採番の主キー
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # panel_id: 親パネルへの外部キー
    panel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("role_panels.id", ondelete="CASCADE"), nullable=False
    )

    # role_id: 付与するロールの Discord ID
    role_id: Mapped[str] = mapped_column(String, nullable=False)

    # emoji: ボタン/リアクションに使用する絵文字
    emoji: Mapped[str] = mapped_column(String, nullable=False)

    # label: ボタンのラベル (ボタン式のみ、リアクション式は None)
    label: Mapped[str | None] = mapped_column(String, nullable=True)

    # style: ボタンのスタイル (ボタン式のみ)
    style: Mapped[str] = mapped_column(String, default="secondary", nullable=False)

    # position: 表示順序
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # --- リレーション ---
    # このアイテムが属する親パネル
    panel: Mapped["RolePanel"] = relationship("RolePanel", back_populates="items")

    @validates("style")
    def _validate_style(self, _key: str, value: str) -> str:
        allowed = ("primary", "secondary", "success", "danger")
        if value not in allowed:
            msg = f"style must be one of {allowed}, got: {value!r}"
            raise ValueError(msg)
        return value

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<RolePanelItem(id={self.id}, panel_id={self.panel_id}, "
            f"role_id={self.role_id}, emoji={self.emoji})>"
        )


class AutoModRule(Base):
    """AutoMod ルール設定テーブル。

    新規メンバー参加時に自動 BAN/KICK/Timeout するルールを定義する。
    1つのサーバーに複数のルールを設定可能。

    Attributes:
        id (int): 自動採番の主キー。
        guild_id (str): Discord サーバーの ID。インデックス付き。
        rule_type (str): ルールの種類。
            "username_match", "account_age", "no_avatar",
            "role_acquired", "vc_join", "message_post"
        is_enabled (bool): ルールが有効かどうか (デフォルト True)。
        action (str): アクション ("ban", "kick", "timeout")。
        pattern (str | None): ユーザー名マッチング用パターン (username_match のみ)。
        use_wildcard (bool): ワイルドカード (部分一致) を使用するか (デフォルト False)。
        threshold_seconds (int | None): 時間ベースの閾値 (秒)。
            account_age: アカウント年齢の閾値 (最大 1209600 = 14日)。
            role_acquired/vc_join/message_post: JOIN後の閾値 (最大 3600 = 1時間)。
        timeout_duration_seconds (int | None): タイムアウト時間 (秒)。
            action="timeout" 時のみ使用 (最大 2419200 = 28日)。
        created_at (datetime): ルール作成日時 (UTC)。
        logs (list[AutoModLog]): このルールの実行ログ一覧。

    Notes:
        - テーブル名: ``automod_rules``
        - on_member_join, on_member_update, on_voice_state_update でルールを評価
        - rule_type に応じて使用するフィールドが異なる
    """

    __tablename__ = "automod_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    rule_type: Mapped[str] = mapped_column(String, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False, default="ban")
    pattern: Mapped[str | None] = mapped_column(String, nullable=True)
    use_wildcard: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    threshold_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    required_channel_id: Mapped[str | None] = mapped_column(String, nullable=True)
    timeout_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    logs: Mapped[list["AutoModLog"]] = relationship(
        "AutoModLog", back_populates="rule", cascade="all, delete-orphan"
    )

    @validates("rule_type")
    def _validate_rule_type(self, _key: str, value: str) -> str:
        allowed = (
            "username_match",
            "account_age",
            "no_avatar",
            "role_acquired",
            "vc_join",
            "message_post",
            "vc_without_intro",
            "msg_without_intro",
        )
        if value not in allowed:
            msg = f"rule_type must be one of {allowed}, got: {value!r}"
            raise ValueError(msg)
        return value

    @validates("action")
    def _validate_action(self, _key: str, value: str) -> str:
        if value not in ("ban", "kick", "timeout"):
            msg = f"action must be 'ban', 'kick', or 'timeout', got: {value!r}"
            raise ValueError(msg)
        return value

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<AutoModRule(id={self.id}, guild_id={self.guild_id}, "
            f"type={self.rule_type}, enabled={self.is_enabled})>"
        )


class AutoModConfig(Base):
    """AutoMod のギルドごと設定テーブル。

    ギルドごとに AutoMod のログチャンネルを設定する。

    Attributes:
        guild_id (str): Discord サーバーの ID (主キー、1ギルド1設定)。
        log_channel_id (str | None): BAN/KICK/Timeout ログ送信先チャンネルの ID。

    Notes:
        - テーブル名: ``automod_configs``
        - guild_id が主キー (1ギルドにつき1設定のみ)
    """

    __tablename__ = "automod_configs"

    guild_id: Mapped[str] = mapped_column(String, primary_key=True)
    log_channel_id: Mapped[str | None] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<AutoModConfig(guild_id={self.guild_id}, "
            f"log_channel_id={self.log_channel_id})>"
        )


class HealthConfig(Base):
    """ヘルスチェックのギルドごと設定テーブル。

    ギルドごとにハートビート/デプロイ通知の送信先チャンネルを設定する。

    Attributes:
        guild_id (str): Discord サーバーの ID (主キー、1ギルド1設定)。
        channel_id (str): ハートビート Embed 送信先チャンネルの ID。

    Notes:
        - テーブル名: ``health_configs``
        - guild_id が主キー (1ギルドにつき1設定のみ)
        - 無効化する場合はレコードを削除する
    """

    __tablename__ = "health_configs"

    guild_id: Mapped[str] = mapped_column(String, primary_key=True)
    channel_id: Mapped[str] = mapped_column(String, nullable=False)

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return f"<HealthConfig(guild_id={self.guild_id}, channel_id={self.channel_id})>"


class AutoModLog(Base):
    """AutoMod 実行ログテーブル。

    AutoMod ルールにマッチしてアクションが実行された記録を保存する。

    Attributes:
        id (int): 自動採番の主キー。
        guild_id (str): Discord サーバーの ID。インデックス付き。
        user_id (str): BAN/KICK/Timeout されたユーザーの ID。
        username (str): アクション時のユーザー名。
        rule_id (int): 適用されたルールへの外部キー。
        action_taken (str): 実行されたアクション ("banned", "kicked", "timed_out")。
        reason (str): 人間可読な理由文字列。
        created_at (datetime): 実行日時 (UTC)。
        rule (AutoModRule): 適用されたルール。

    Notes:
        - テーブル名: ``automod_logs``
        - ルール削除時にログもカスケード削除される
    """

    __tablename__ = "automod_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    username: Mapped[str] = mapped_column(String, nullable=False)
    rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("automod_rules.id", ondelete="CASCADE"), nullable=False
    )
    action_taken: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    rule: Mapped["AutoModRule"] = relationship("AutoModRule", back_populates="logs")

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<AutoModLog(id={self.id}, guild_id={self.guild_id}, "
            f"user_id={self.user_id}, action={self.action_taken})>"
        )


class AutoModIntroPost(Base):
    """AutoMod 指定チャンネル投稿追跡テーブル。

    vc_without_intro / msg_without_intro ルール用。
    メンバーが指定チャンネルに投稿したことを記録する。

    Attributes:
        id (int): 自動採番の主キー。
        guild_id (str): Discord サーバーの ID。インデックス付き。
        user_id (str): 投稿したユーザーの ID。
        channel_id (str): 投稿先チャンネルの ID。
        posted_at (datetime): 投稿日時 (UTC)。

    Notes:
        - テーブル名: ``automod_intro_posts``
        - (guild_id, user_id, channel_id) でユニーク制約
    """

    __tablename__ = "automod_intro_posts"
    __table_args__ = (
        UniqueConstraint(
            "guild_id",
            "user_id",
            "channel_id",
            name="uq_intro_guild_user_channel",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    channel_id: Mapped[str] = mapped_column(String, nullable=False)
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<AutoModIntroPost(id={self.id}, guild_id={self.guild_id}, "
            f"user_id={self.user_id}, channel_id={self.channel_id})>"
        )


class BanLog(Base):
    """BAN ログテーブル。

    Discord 上の全ての BAN (AutoMod + 手動) を記録する。

    Attributes:
        id (int): 自動採番の主キー。
        guild_id (str): Discord サーバーの ID。インデックス付き。
        user_id (str): BAN されたユーザーの ID。
        username (str): BAN 時のユーザー名。
        reason (str | None): BAN 理由 (なしの場合 None)。
        is_automod (bool): AutoMod による BAN かどうか。
        created_at (datetime): 実行日時 (UTC)。

    Notes:
        - テーブル名: ``ban_logs``
        - AutoMod / 手動 BAN を問わず全ての BAN を記録
    """

    __tablename__ = "ban_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    username: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    is_automod: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<BanLog(id={self.id}, guild_id={self.guild_id}, "
            f"user_id={self.user_id}, is_automod={self.is_automod})>"
        )


class TicketCategory(Base):
    """チケットカテゴリ設定テーブル。

    チケットの種類 (例: General Support, Bug Report) を定義する。
    各カテゴリにスタッフロール、チャンネル接頭辞、フォーム質問を設定可能。

    Attributes:
        id (int): 自動採番の主キー。
        guild_id (str): Discord サーバーの ID。インデックス付き。
        name (str): カテゴリ名。
        staff_role_id (str): チケットを閲覧できるスタッフロールの ID。
        discord_category_id (str | None): チケット配置先カテゴリ ID。
        channel_prefix (str): チケットチャンネル名の接頭辞 (default "ticket-")。
        form_questions (str | None): フォーム質問の JSON 配列 (最大5問)。
        log_channel_id (str | None): クローズログ送信先チャンネル ID。
        is_enabled (bool): カテゴリが有効かどうか (default True)。
        created_at (datetime): 作成日時 (UTC)。

    Notes:
        - テーブル名: ``ticket_categories``
        - form_questions は JSON 文字列 (例: '["お名前","内容"]')
        - Discord Modal の制限により最大5問
    """

    __tablename__ = "ticket_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    staff_role_id: Mapped[str] = mapped_column(String, nullable=False)
    discord_category_id: Mapped[str | None] = mapped_column(String, nullable=True)
    channel_prefix: Mapped[str] = mapped_column(
        String, nullable=False, default="ticket-"
    )
    form_questions: Mapped[str | None] = mapped_column(String, nullable=True)
    log_channel_id: Mapped[str | None] = mapped_column(String, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    panel_associations: Mapped[list["TicketPanelCategory"]] = relationship(
        "TicketPanelCategory", back_populates="category", cascade="all, delete-orphan"
    )
    tickets: Mapped[list["Ticket"]] = relationship(
        "Ticket", back_populates="category", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<TicketCategory(id={self.id}, guild_id={self.guild_id}, "
            f"name={self.name})>"
        )


class TicketPanel(Base):
    """チケットパネル設定テーブル。

    Discord チャンネルに送信されるパネルメッセージの設定。
    ユーザーがボタンをクリックしてチケットを作成する。

    Attributes:
        id (int): 自動採番の主キー。
        guild_id (str): Discord サーバーの ID。インデックス付き。
        channel_id (str): パネル送信先チャンネルの ID。
        message_id (str | None): Discord メッセージの ID (送信後に設定)。
        title (str): パネルのタイトル。
        description (str | None): パネルの説明文。
        created_at (datetime): 作成日時 (UTC)。

    Notes:
        - テーブル名: ``ticket_panels``
        - category_associations でカテゴリと多対多の関係
    """

    __tablename__ = "ticket_panels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    channel_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    message_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    category_associations: Mapped[list["TicketPanelCategory"]] = relationship(
        "TicketPanelCategory", back_populates="panel", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<TicketPanel(id={self.id}, guild_id={self.guild_id}, title={self.title})>"
        )


class TicketPanelCategory(Base):
    """チケットパネルとカテゴリの結合テーブル。

    パネルに表示するカテゴリボタンの設定を保持する。

    Attributes:
        id (int): 自動採番の主キー。
        panel_id (int): パネルへの外部キー。
        category_id (int): カテゴリへの外部キー。
        button_label (str | None): ボタンラベルの上書き。
        button_style (str): ボタンスタイル (default "primary")。
        button_emoji (str | None): ボタンの絵文字。
        position (int): 表示順序 (default 0)。

    Notes:
        - テーブル名: ``ticket_panel_categories``
        - (panel_id, category_id) でユニーク制約
    """

    __tablename__ = "ticket_panel_categories"
    __table_args__ = (
        UniqueConstraint("panel_id", "category_id", name="uq_ticket_panel_category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    panel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ticket_panels.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ticket_categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    button_label: Mapped[str | None] = mapped_column(String, nullable=True)
    button_style: Mapped[str] = mapped_column(String, nullable=False, default="primary")
    button_emoji: Mapped[str | None] = mapped_column(String, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    panel: Mapped["TicketPanel"] = relationship(
        "TicketPanel", back_populates="category_associations"
    )
    category: Mapped["TicketCategory"] = relationship(
        "TicketCategory", back_populates="panel_associations"
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<TicketPanelCategory(id={self.id}, panel_id={self.panel_id}, "
            f"category_id={self.category_id})>"
        )


class Ticket(Base):
    """チケットテーブル。

    ユーザーが作成したチケットの情報を保存する。

    Attributes:
        id (int): 自動採番の主キー。
        guild_id (str): Discord サーバーの ID。インデックス付き。
        channel_id (str | None): チケットチャンネルの ID (クローズ後 None)。
        user_id (str): チケット作成者の Discord ユーザー ID。
        username (str): 作成時のユーザー名。
        category_id (int): カテゴリへの外部キー。
        status (str): チケットの状態 ("open" | "claimed" | "closed")。
        claimed_by (str | None): 担当スタッフの ID。
        closed_by (str | None): クローズしたユーザーの ID。
        close_reason (str | None): クローズ理由。
        transcript (str | None): トランスクリプト全文。
        ticket_number (int): ギルド内連番。
        form_answers (str | None): フォーム回答の JSON 文字列。
        created_at (datetime): 作成日時 (UTC)。
        closed_at (datetime | None): クローズ日時 (UTC)。

    Notes:
        - テーブル名: ``tickets``
        - (guild_id, ticket_number) でユニーク制約
        - channel_id はクローズ後に None に設定
    """

    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("guild_id", "ticket_number", name="uq_guild_ticket_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    channel_id: Mapped[str | None] = mapped_column(
        String, nullable=True, unique=True, index=True
    )
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String, nullable=False)
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ticket_categories.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    claimed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    closed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    ticket_number: Mapped[int] = mapped_column(Integer, nullable=False)
    form_answers: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    category: Mapped["TicketCategory"] = relationship(
        "TicketCategory", back_populates="tickets"
    )

    @validates("status")
    def _validate_status(self, _key: str, value: str) -> str:
        allowed = ("open", "claimed", "closed")
        if value not in allowed:
            msg = f"status must be one of {allowed}, got: {value!r}"
            raise ValueError(msg)
        return value

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<Ticket(id={self.id}, guild_id={self.guild_id}, "
            f"number={self.ticket_number}, status={self.status})>"
        )


# =============================================================================
# Join Role (自動ロール付与)
# =============================================================================


class JoinRoleConfig(Base):
    """サーバーごとの Join ロール設定。

    新規メンバー参加時に自動付与するロールと期限を定義する。
    1サーバーで複数ロール設定可能。
    """

    __tablename__ = "join_role_configs"
    __table_args__ = (
        UniqueConstraint("guild_id", "role_id", name="uq_join_role_guild_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    role_id: Mapped[str] = mapped_column(String, nullable=False)
    duration_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<JoinRoleConfig(id={self.id}, guild_id={self.guild_id}, "
            f"role_id={self.role_id}, hours={self.duration_hours})>"
        )


class JoinRoleAssignment(Base):
    """付与済みロールの追跡レコード。

    期限切れ時にロールを自動削除するために使用する。
    Bot 再起動後も期限切れチェックを継続できる。
    """

    __tablename__ = "join_role_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    role_id: Mapped[str] = mapped_column(String, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return (
            f"<JoinRoleAssignment(id={self.id}, guild_id={self.guild_id}, "
            f"user_id={self.user_id}, role_id={self.role_id})>"
        )


class EventLogConfig(Base):
    """イベントログのルーティング設定テーブル。

    ギルドごとにどのイベントタイプをどのチャンネルに送信するかを定義する。
    1行 = 1つのイベントタイプ → 1つのチャンネル のマッピング。
    """

    __tablename__ = "event_log_configs"
    __table_args__ = (
        UniqueConstraint("guild_id", "event_type", name="uq_event_log_guild_event"),
    )

    VALID_EVENT_TYPES = (
        "message_delete",
        "message_edit",
        "member_join",
        "member_leave",
        "member_kick",
        "member_ban",
        "member_unban",
        "member_timeout",
        "role_change",
        "nickname_change",
        "channel_create",
        "channel_delete",
        "voice_state",
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    channel_id: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<EventLogConfig(id={self.id}, guild_id={self.guild_id}, "
            f"event_type={self.event_type}, channel_id={self.channel_id})>"
        )


class ProcessedEvent(Base):
    """重複排除テーブル (マルチインスタンス重複防止)。

    複数インスタンスが同じ Discord Gateway イベントを受信した際に、
    1 インスタンスだけが処理を実行するための重複排除レコード。
    event_key の UNIQUE 制約により、INSERT の IntegrityError で
    アトミックに重複を検出する。

    Attributes:
        id (int): 自動採番の主キー。
        event_key (str): イベントを一意に識別するキー。UNIQUE 制約付き。
        created_at (datetime): レコード作成日時 (UTC)。cleanup 用。

    Notes:
        - テーブル名: ``processed_events``
        - 古いレコードは health cog の heartbeat で定期削除される
    """

    __tablename__ = "processed_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return f"<ProcessedEvent(id={self.id}, event_key={self.event_key})>"


class BotActivity(Base):
    """Bot のアクティビティ（プレゼンス）設定。

    シングルレコードとして運用する（id=1 のみ）。
    レコードが存在しない場合はデフォルト値を使用する。

    Attributes:
        id: 自動採番の主キー。
        activity_type: アクティビティの種類
            (playing / listening / watching / competing)。
        activity_text: 表示テキスト。
        updated_at: 最終更新日時 (UTC)。
    """

    __tablename__ = "bot_activity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_type: Mapped[str] = mapped_column(
        String, nullable=False, default="playing"
    )
    activity_text: Mapped[str] = mapped_column(
        String, nullable=False, default="お菓子を食べています"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現。"""
        return (
            f"<BotActivity(id={self.id}, type={self.activity_type}, "
            f"text={self.activity_text!r})>"
        )
