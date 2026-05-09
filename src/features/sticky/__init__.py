"""Sticky feature entrypoints.

Feature package facade to enable package-by-feature migration while
keeping existing module paths stable.
"""

from src.cogs.sticky import StickyCog
from src.services.sticky_service import *  # noqa: F401,F403
from src.web.routes.api_sticky import router as api_router

__all__ = ["StickyCog", "api_router"]
