"""Welcome feature entrypoints."""

from typing import TYPE_CHECKING, Any

from src.features.welcome.presentation import (
    WELCOME_EMBED_COLOR,
    WELCOME_PLACEHOLDERS,
    WelcomeRenderInputs,
    build_welcome_banner_input,
    build_welcome_embed,
    build_welcome_render_inputs,
    build_welcome_status_message,
    format_message_content,
)
from src.services.welcome_banner_service import WelcomeBannerInput, WelcomeBannerService
from src.services.welcome_service import *  # noqa: F401,F403

if TYPE_CHECKING:
    from src.cogs.welcome import WelcomeCog

__all__ = [
    "WELCOME_EMBED_COLOR",
    "WELCOME_PLACEHOLDERS",
    "WelcomeBannerInput",
    "WelcomeBannerService",
    "WelcomeCog",
    "WelcomeRenderInputs",
    "build_welcome_banner_input",
    "build_welcome_embed",
    "build_welcome_render_inputs",
    "build_welcome_status_message",
    "format_message_content",
]


def __getattr__(name: str) -> Any:
    """Cog との循環 import を避けながら facade から遅延公開する。"""
    if name == "WelcomeCog":
        from src.cogs.welcome import WelcomeCog

        return WelcomeCog
    raise AttributeError(name)
