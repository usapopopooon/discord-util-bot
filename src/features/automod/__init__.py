"""AutoMod feature entrypoints."""

from src.cogs.automod import AutoModCog
from src.services.automod_service import *  # noqa: F401,F403
from src.web.routes.api_automod import router as api_router

__all__ = ["AutoModCog", "api_router"]
