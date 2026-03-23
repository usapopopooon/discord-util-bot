"""FastAPI web admin application.

Thin facade: creates the FastAPI app, registers middleware/routers,
and re-exports symbols from sub-modules for backward compatibility.
Route modules access symbols via ``import src.web.app as _app``.
"""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from src.database.engine import async_session
from src.database.engine import (
    check_database_connection as check_database_connection,  # noqa: F401
)
from src.database.models import SiteSettings

# ---------------------------------------------------------------------------
# Re-exports: db_helpers
# ---------------------------------------------------------------------------
from src.web.db_helpers import (  # noqa: F401
    _VALID_ACTIVITY_TYPES as _VALID_ACTIVITY_TYPES,
)
from src.web.db_helpers import (
    _get_discord_categories as _get_discord_categories,
)
from src.web.db_helpers import (
    _get_discord_guilds_and_channels as _get_discord_guilds_and_channels,
)
from src.web.db_helpers import (
    _get_discord_roles_by_guild as _get_discord_roles_by_guild,
)
from src.web.db_helpers import (
    get_db as get_db,
)
from src.web.db_helpers import (
    get_or_create_admin as get_or_create_admin,
)

# ---------------------------------------------------------------------------
# Re-exports: discord_api / email_service
# ---------------------------------------------------------------------------
from src.web.discord_api import (  # noqa: F401
    add_reactions_to_message as add_reactions_to_message,
)
from src.web.discord_api import (
    delete_discord_message as delete_discord_message,
)
from src.web.discord_api import (
    edit_role_panel_in_discord as edit_role_panel_in_discord,
)
from src.web.discord_api import (
    edit_ticket_panel_in_discord as edit_ticket_panel_in_discord,
)
from src.web.discord_api import (
    post_role_panel_to_discord as post_role_panel_to_discord,
)
from src.web.discord_api import (
    post_ticket_panel_to_discord as post_ticket_panel_to_discord,
)
from src.web.email_service import (  # noqa: F401
    send_email_change_verification as send_email_change_verification,
)

# ---------------------------------------------------------------------------
# Re-exports: jwt_auth
# ---------------------------------------------------------------------------
from src.web.jwt_auth import (  # noqa: F401
    create_jwt_token as create_jwt_token,
)
from src.web.jwt_auth import (
    get_current_user_jwt as get_current_user_jwt,
)
from src.web.jwt_auth import (
    verify_jwt_token as verify_jwt_token,
)

# ---------------------------------------------------------------------------
# Re-exports: security
# ---------------------------------------------------------------------------
from src.web.security import (  # noqa: F401
    CSRF_TOKEN_MAX_AGE_SECONDS as CSRF_TOKEN_MAX_AGE_SECONDS,
)
from src.web.security import (
    EMAIL_PATTERN as EMAIL_PATTERN,
)
from src.web.security import (
    FORM_SUBMIT_TIMES as FORM_SUBMIT_TIMES,
)
from src.web.security import (
    INIT_ADMIN_EMAIL as INIT_ADMIN_EMAIL,
)
from src.web.security import (
    INIT_ADMIN_PASSWORD as INIT_ADMIN_PASSWORD,
)
from src.web.security import (
    LOGIN_ATTEMPTS as LOGIN_ATTEMPTS,
)
from src.web.security import (
    SECRET_KEY as SECRET_KEY,
)
from src.web.security import (
    SECURE_COOKIE as SECURE_COOKIE,
)
from src.web.security import (
    SecurityHeadersMiddleware as SecurityHeadersMiddleware,
)
from src.web.security import (
    create_session_token as create_session_token,
)
from src.web.security import (
    csrf_serializer as csrf_serializer,
)
from src.web.security import (
    generate_csrf_token as generate_csrf_token,
)
from src.web.security import (
    get_current_user as get_current_user,
)
from src.web.security import (
    hash_password as hash_password,
)
from src.web.security import (
    hash_password_async as hash_password_async,
)
from src.web.security import (
    is_form_cooldown_active as is_form_cooldown_active,
)
from src.web.security import (
    is_rate_limited as is_rate_limited,
)
from src.web.security import (
    record_failed_attempt as record_failed_attempt,
)
from src.web.security import (
    record_form_submit as record_form_submit,
)
from src.web.security import (
    serializer as serializer,
)
from src.web.security import (
    validate_csrf_token as validate_csrf_token,
)
from src.web.security import (
    verify_password as verify_password,
)
from src.web.security import (
    verify_password_async as verify_password_async,
)
from src.web.security import (
    verify_session_token as verify_session_token,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Lifespan
# =============================================================================


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan handler for startup/shutdown events."""
    logger.info("Starting web admin application...")
    if not await check_database_connection():
        logger.error(
            "Database connection failed. "
            "Check DATABASE_URL and ensure the database is running."
        )
    else:
        logger.info("Database connection successful")
        try:
            async with async_session() as session:
                result = await session.execute(select(SiteSettings).limit(1))
                site = result.scalar_one_or_none()
                if site:
                    from src.utils import set_timezone_offset

                    set_timezone_offset(site.timezone_offset)
                    logger.info(
                        "Timezone offset loaded: UTC%+d",
                        site.timezone_offset,
                    )
        except Exception:
            logger.warning("Failed to load site settings from DB")
    yield
    logger.info("Shutting down web admin application...")


# =============================================================================
# App creation
# =============================================================================

app = FastAPI(title="Bot Admin", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
_cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# Router registration
# =============================================================================

from src.web.routes.api_auth import router as api_auth_router  # noqa: E402
from src.web.routes.api_automod import router as api_automod_router  # noqa: E402
from src.web.routes.api_bump import router as api_bump_router  # noqa: E402
from src.web.routes.api_eventlog import router as api_eventlog_router  # noqa: E402
from src.web.routes.api_joinrole import router as api_joinrole_router  # noqa: E402
from src.web.routes.api_lobbies import router as api_lobbies_router  # noqa: E402
from src.web.routes.api_misc import router as api_misc_router  # noqa: E402
from src.web.routes.api_rolepanel import router as api_rolepanel_router  # noqa: E402
from src.web.routes.api_settings import router as api_settings_router  # noqa: E402
from src.web.routes.api_sticky import router as api_sticky_router  # noqa: E402
from src.web.routes.api_ticket import router as api_ticket_router  # noqa: E402
from src.web.routes.auth import router as auth_router  # noqa: E402
from src.web.routes.automod import router as automod_router  # noqa: E402
from src.web.routes.bump import router as bump_router  # noqa: E402
from src.web.routes.joinrole import router as joinrole_router  # noqa: E402
from src.web.routes.lobby import router as lobby_router  # noqa: E402
from src.web.routes.misc import router as misc_router  # noqa: E402
from src.web.routes.rolepanel import router as rolepanel_router  # noqa: E402
from src.web.routes.settings import router as settings_router  # noqa: E402
from src.web.routes.sticky import router as sticky_router  # noqa: E402
from src.web.routes.ticket import router as ticket_router  # noqa: E402

app.include_router(api_auth_router)
app.include_router(api_automod_router)
app.include_router(api_lobbies_router)
app.include_router(api_sticky_router)
app.include_router(api_bump_router)
app.include_router(api_joinrole_router)
app.include_router(api_eventlog_router)
app.include_router(api_misc_router)
app.include_router(api_rolepanel_router)
app.include_router(api_settings_router)
app.include_router(api_ticket_router)
app.include_router(misc_router)
app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(lobby_router)
app.include_router(sticky_router)
app.include_router(bump_router)
app.include_router(rolepanel_router)
app.include_router(automod_router)
app.include_router(ticket_router)
app.include_router(joinrole_router)
