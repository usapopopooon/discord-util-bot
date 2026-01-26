"""Entry point for Ephemeral VC bot."""

import asyncio

from src.bot import EphemeralVCBot
from src.config import settings


async def main() -> None:
    """Run the bot."""
    bot = EphemeralVCBot()
    async with bot:
        await bot.start(settings.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
