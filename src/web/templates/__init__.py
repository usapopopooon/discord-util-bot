"""HTML templates using f-strings and Tailwind CSS.

This package re-exports all public template functions for backward compatibility.
"""

from src.web.templates._common import (  # noqa: F401
    _base as _base,
)
from src.web.templates._common import (
    _breadcrumb as _breadcrumb,
)
from src.web.templates._common import (
    _build_emoji_list as _build_emoji_list,
)
from src.web.templates._common import (
    _csrf_field as _csrf_field,
)
from src.web.templates._common import (
    _get_emoji_json as _get_emoji_json,
)
from src.web.templates._common import (
    _nav as _nav,
)
from src.web.templates._common import (
    _roles_to_js_array as _roles_to_js_array,
)
from src.web.templates.auth import (  # noqa: F401
    email_verification_pending_page as email_verification_pending_page,
)
from src.web.templates.auth import (
    forgot_password_page as forgot_password_page,
)
from src.web.templates.auth import (
    initial_setup_page as initial_setup_page,
)
from src.web.templates.auth import (
    login_page as login_page,
)
from src.web.templates.auth import (
    reset_password_page as reset_password_page,
)
from src.web.templates.automod import (  # noqa: F401
    automod_create_page as automod_create_page,
)
from src.web.templates.automod import (
    automod_edit_page as automod_edit_page,
)
from src.web.templates.automod import (
    automod_list_page as automod_list_page,
)
from src.web.templates.automod import (
    automod_logs_page as automod_logs_page,
)
from src.web.templates.automod import (
    automod_settings_page as automod_settings_page,
)
from src.web.templates.automod import (
    ban_logs_page as ban_logs_page,
)
from src.web.templates.bump import bump_list_page as bump_list_page  # noqa: F401
from src.web.templates.joinrole import joinrole_page as joinrole_page  # noqa: F401
from src.web.templates.lobby import (  # noqa: F401
    lobbies_list_page as lobbies_list_page,
)
from src.web.templates.misc import (  # noqa: F401
    activity_page as activity_page,
)
from src.web.templates.misc import (
    eventlog_page as eventlog_page,
)
from src.web.templates.misc import (
    health_settings_page as health_settings_page,
)
from src.web.templates.role_panel import (  # noqa: F401
    role_panel_create_page as role_panel_create_page,
)
from src.web.templates.role_panel import (
    role_panel_detail_page as role_panel_detail_page,
)
from src.web.templates.role_panel import (
    role_panels_list_page as role_panels_list_page,
)
from src.web.templates.settings import (  # noqa: F401
    dashboard_page as dashboard_page,
)
from src.web.templates.settings import (
    email_change_page as email_change_page,
)
from src.web.templates.settings import (
    maintenance_page as maintenance_page,
)
from src.web.templates.settings import (
    password_change_page as password_change_page,
)
from src.web.templates.settings import (
    settings_page as settings_page,
)
from src.web.templates.sticky import sticky_list_page as sticky_list_page  # noqa: F401
from src.web.templates.ticket import (  # noqa: F401
    ticket_detail_page as ticket_detail_page,
)
from src.web.templates.ticket import (
    ticket_list_page as ticket_list_page,
)
from src.web.templates.ticket import (
    ticket_panel_create_page as ticket_panel_create_page,
)
from src.web.templates.ticket import (
    ticket_panel_detail_page as ticket_panel_detail_page,
)
from src.web.templates.ticket import (
    ticket_panels_list_page as ticket_panels_list_page,
)
