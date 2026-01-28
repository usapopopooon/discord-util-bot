"""Admin slash commands placeholder.

管理者用コマンドの Cog。
/vc lobby は voice.py に統合されました。
"""

from discord.ext import commands


class AdminCog(commands.Cog):
    """管理者用コマンドの Cog (将来の拡張用)。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


async def setup(bot: commands.Bot) -> None:
    """Cog を Bot に登録する関数。bot.load_extension() から呼ばれる。"""
    await bot.add_cog(AdminCog(bot))
