"""Discord bot class definition.

Bot 本体のクラス定義。起動時の初期化処理（DB・Cog・View の復元）を担う。

Examples:
    基本的な使い方::

        from src.bot import EphemeralVCBot
        from src.config import settings

        bot = EphemeralVCBot()
        async with bot:
            await bot.start(settings.discord_token)

See Also:
    - :mod:`src.main`: エントリーポイント
    - :mod:`src.cogs`: 各機能 Cog
    - discord.py: https://discordpy.readthedocs.io/

Notes:
    - 起動前に Alembic マイグレーションを実行すること
    - Discord Developer Portal で必要な Intents を有効化すること
"""

import logging

import discord
from discord.ext import commands

from src.database.engine import async_session
from src.services.common_service import (
    get_bot_activity,
    get_site_settings,
)

logger = logging.getLogger(__name__)


def make_activity(activity_type: str, text: str) -> discord.BaseActivity:
    """アクティビティタイプと文言から discord.BaseActivity を生成する。

    Args:
        activity_type: playing / listening / watching / competing。
        text: 表示テキスト。

    Returns:
        対応する discord.BaseActivity インスタンス。
    """
    if activity_type == "listening":
        return discord.Activity(type=discord.ActivityType.listening, name=text)
    if activity_type == "watching":
        return discord.Activity(type=discord.ActivityType.watching, name=text)
    if activity_type == "competing":
        return discord.Activity(type=discord.ActivityType.competing, name=text)
    return discord.Game(name=text)


class EphemeralVCBot(commands.Bot):
    """Bot 本体。

    discord.py の commands.Bot を継承し、bump リマインダー、sticky メッセージ、
    ロールパネル、チケット、自動リアクション等の機能を提供する。

    Attributes:
        command_prefix (str): テキストコマンドの接頭辞 ("!")。
            この Bot ではスラッシュコマンドを主に使用。
        intents (discord.Intents): Bot が受け取るイベントの種類。

    Notes:
        必要な Intents:

        - guilds: サーバー情報 (ギルド) の取得
        - members: メンバー情報の取得 (特権 Intent、Portal 有効化必須)
        - message_content: メッセージ内容の取得 (bump 検知用)

    Examples:
        Bot の起動::

            bot = EphemeralVCBot()
            async with bot:
                await bot.start(settings.discord_token)

    See Also:
        - :meth:`setup_hook`: 起動前の初期化処理
        - :meth:`on_ready`: 起動完了時の処理
        - :class:`discord.ext.commands.Bot`: 基底クラス
    """

    def __init__(self) -> None:
        """Bot インスタンスを初期化する。

        Intents を設定し、親クラスを初期化する。
        Discord Developer Portal の Bot 設定で同じ Intents を
        有効にする必要がある。

        Raises:
            discord.LoginFailure: トークンが無効な場合 (start() 時)。
            discord.PrivilegedIntentsRequired: 特権 Intent が無効な場合。

        See Also:
            - Discord Developer Portal: https://discord.com/developers/applications
        """
        # --- Intents (Bot が受け取るイベントの種類) を設定 ---
        # Discord は Bot が必要なイベントだけ受け取るよう Intents で制御する。
        # Developer Portal の Bot 設定でも同じ Intents を有効にする必要がある。
        intents = discord.Intents.default()
        intents.guilds = True  # サーバー情報 (ギルド) を取得する
        intents.members = True  # メンバー情報を取得する (特権 Intent、要 Portal 有効化)
        intents.message_content = True  # メッセージ内容を取得する (bump 検知用)

        # --- アクティビティ (プレゼンス) を設定 ---
        # discord.Game = 「〜をプレイ中」タイプのアクティビティ
        # コンストラクタで設定することで、接続直後から表示される
        activity = discord.Game(name="お菓子を食べています")

        # command_prefix: テキストコマンドの接頭辞 (例: !help)
        # この Bot ではスラッシュコマンドを使うので、テキストコマンドはほぼ使わない
        super().__init__(
            command_prefix="!",
            intents=intents,
            activity=activity,
        )

    async def setup_hook(self) -> None:
        """Bot 起動前に呼ばれるフック。Cog・スラッシュコマンドの初期化を行う。

        discord.py が内部的に呼び出す。Cog の読み込みとスラッシュコマンドの
        同期を行う。

        Raises:
            discord.ExtensionError: Cog の読み込みに失敗した場合。
            sqlalchemy.exc.OperationalError: DB 接続に失敗した場合。
            discord.HTTPException: Discord API へのリクエストに失敗した場合。

        See Also:
            - :meth:`on_ready`: 起動完了時の処理
        """
        extensions = [
            "src.cogs.admin",
            "src.cogs.health",
            "src.cogs.bump",
            "src.cogs.sticky",
            "src.cogs.role_panel",
            "src.cogs.automod",
            "src.cogs.ticket",
            "src.cogs.join_role",
            "src.cogs.chatrole",
            "src.cogs.auto_reaction",
            "src.cogs.eventlog",
            "src.cogs.watchdog",
        ]
        for ext in extensions:
            try:
                await self.load_extension(ext)
                logger.info("Loaded extension: %s", ext)
            except commands.ExtensionError as e:
                logger.exception("Failed to load extension %s: %s", ext, e)
                raise  # 起動時に Cog 読み込みに失敗したら例外を上げて停止

        # タイムゾーン設定を DB から読み込み
        async with async_session() as session:
            site = await get_site_settings(session)
            if site:
                from src.utils import set_timezone_offset

                set_timezone_offset(site.timezone_offset)
                logger.info("Timezone offset loaded: UTC%+d", site.timezone_offset)

        # スラッシュコマンドを Discord に登録する
        try:
            synced = await self.tree.sync()
            logger.info("Synced %d slash commands", len(synced))
        except discord.HTTPException as e:
            logger.exception("Failed to sync slash commands: %s", e)
            raise

    async def on_ready(self) -> None:
        """Bot が Discord に接続完了したときに呼ばれる。

        Bot のステータス (プレゼンス) を再設定し、起動ログを出力する。

        Returns:
            None

        Notes:
            - on_ready は再接続時にも呼ばれることがある
            - 冪等な処理のみを行うこと (何度呼ばれても問題ない処理)
            - ステータスは「お菓子を食べています」に設定される
            - アクティビティはコンストラクタでも設定されているが、
              再接続時にリセットされる可能性があるため、ここでも再設定する

        Examples:
            on_ready は自動で呼ばれるため、直接呼び出す必要はない::

                # Discord 接続完了時に自動実行される
                # Logged in as BotName (ID: 123456789)
                # ------

        See Also:
            - :meth:`setup_hook`: 起動前の初期化処理
            - :meth:`discord.Client.change_presence`: プレゼンス変更
        """
        # Bot のステータスを DB から読み込んで設定する
        # DB にレコードがない場合はデフォルト値を使用する
        activity: discord.BaseActivity = discord.Game(name="お菓子を食べています")
        try:
            async with async_session() as session:
                bot_activity = await get_bot_activity(session)
                if bot_activity:
                    activity = make_activity(
                        bot_activity.activity_type, bot_activity.activity_text
                    )
        except Exception:
            logger.exception("Failed to load bot activity from DB")
        await self.change_presence(activity=activity)

        if self.user:
            print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("------")
