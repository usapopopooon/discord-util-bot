"""HTML templates using f-strings and Tailwind CSS."""

import re
from html import escape
from typing import TYPE_CHECKING

from src.utils import format_datetime

if TYPE_CHECKING:
    from src.database.models import (
        AutoBanLog,
        AutoBanRule,
        BanLog,
        BumpConfig,
        BumpReminder,
        JoinRoleConfig,
        Lobby,
        RolePanel,
        RolePanelItem,
        StickyMessage,
        Ticket,
        TicketPanel,
        TicketPanelCategory,
    )


def _csrf_field(csrf_token: str) -> str:
    """CSRF トークンの hidden フィールドを生成する."""
    return f'<input type="hidden" name="csrf_token" value="{escape(csrf_token)}">'


def _roles_to_js_array(roles: list[tuple[str, str, int]]) -> str:
    """Discord ロールリストを JavaScript 配列文字列に変換する."""
    import json

    js_roles = [{"id": r[0], "name": r[1], "color": r[2]} for r in roles]
    return json.dumps(js_roles)


def _base(title: str, content: str) -> str:
    """Base HTML template with Tailwind CDN."""
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(title)} - Bot Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
    function postAction(url, csrfToken, confirmMsg) {{
        if (confirmMsg && !confirm(confirmMsg)) return;
        const f = document.createElement('form');
        f.method = 'POST';
        f.action = url;
        const i = document.createElement('input');
        i.type = 'hidden';
        i.name = 'csrf_token';
        i.value = csrfToken;
        f.appendChild(i);
        document.body.appendChild(f);
        f.submit();
    }}
    </script>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen">
    {content}
</body>
</html>"""


def _breadcrumb(crumbs: list[tuple[str, str | None]]) -> str:
    """パンくずリストを生成する.

    Args:
        crumbs: (label, url) のリスト。最後の要素は現在のページ (url=None)。
                最後の要素は h1 タイトルと重複するためレンダリングしない。

    Returns:
        パンくずリストの HTML
    """
    items = []
    # 最後の要素（現在のページ）は h1 タイトルとして表示されるため除外
    nav_crumbs = crumbs[:-1] if crumbs else []
    for i, (label, url) in enumerate(nav_crumbs):
        if url:
            items.append(
                f'<a href="{escape(url)}" class="text-gray-400 hover:text-white">'
                f"{escape(label)}</a>"
            )
        else:
            items.append(f'<span class="text-gray-300">{escape(label)}</span>')
        if i < len(nav_crumbs) - 1:
            items.append('<span class="text-gray-600">&gt;</span>')
    return " ".join(items)


def _nav(
    title: str,
    show_dashboard_link: bool = True,
    breadcrumbs: list[tuple[str, str | None]] | None = None,
) -> str:
    """Navigation bar component.

    Args:
        title: ページタイトル (h1)
        show_dashboard_link: Dashboard リンクを表示するか (breadcrumbs がある場合は無視)
        breadcrumbs: パンくずリスト。指定時は show_dashboard_link は無視される。
    """
    nav_content = ""
    if breadcrumbs:
        nav_content = _breadcrumb(breadcrumbs)
    elif show_dashboard_link:
        nav_content = (
            '<a href="/dashboard" class="text-gray-400 hover:text-white">'
            "&larr; Dashboard</a>"
        )
    return f"""
    <nav class="flex justify-between items-center mb-8">
        <div class="flex items-center gap-4">
            <div class="flex items-center gap-2 text-sm">
                {nav_content}
            </div>
            <h1 class="text-2xl font-bold">{escape(title)}</h1>
        </div>
        <a href="/logout"
           class="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded transition-colors">
            Logout
        </a>
    </nav>
    """


def login_page(error: str | None = None, csrf_token: str = "") -> str:
    """Login page template."""
    error_html = ""
    if error:
        error_html = f"""
        <div class="bg-red-500/20 border border-red-500 text-red-300 px-4 py-3 rounded mb-4">
            {escape(error)}
        </div>
        """

    content = f"""
    <div class="flex items-center justify-center min-h-screen">
        <div class="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-md">
            <h1 class="text-2xl font-bold text-center mb-6">Bot Admin</h1>
            {error_html}
            <form method="POST" action="/login">
                {_csrf_field(csrf_token)}
                <div class="mb-4">
                    <label for="email" class="block text-sm font-medium mb-2">
                        Email
                    </label>
                    <input
                        type="email"
                        id="email"
                        name="email"
                        required
                        class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100"
                        placeholder="Enter email"
                    >
                </div>
                <div class="mb-4">
                    <label for="password" class="block text-sm font-medium mb-2">
                        Password
                    </label>
                    <input
                        type="password"
                        id="password"
                        name="password"
                        required
                        class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100"
                        placeholder="Enter password"
                    >
                </div>
                <button
                    type="submit"
                    class="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium
                           py-2 px-4 rounded transition-colors"
                >
                    Login
                </button>
            </form>
            <!-- SMTP 未設定のため非表示
            <div class="mt-4 text-center">
                <a href="/forgot-password" class="text-blue-400 hover:text-blue-300 text-sm">
                    Forgot password?
                </a>
            </div>
            -->
        </div>
    </div>
    """
    return _base("Login", content)


def forgot_password_page(
    error: str | None = None,
    success: str | None = None,
    csrf_token: str = "",
) -> str:
    """Forgot password page template."""
    message_html = ""
    if error:
        message_html = f"""
        <div class="bg-red-500/20 border border-red-500 text-red-300 px-4 py-3 rounded mb-4">
            {escape(error)}
        </div>
        """
    elif success:
        message_html = f"""
        <div class="bg-green-500/20 border border-green-500 text-green-300 px-4 py-3 rounded mb-4">
            {escape(success)}
        </div>
        """

    content = f"""
    <div class="flex items-center justify-center min-h-screen">
        <div class="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-md">
            <h1 class="text-2xl font-bold text-center mb-6">Reset Password</h1>
            {message_html}
            <p class="text-gray-400 text-sm mb-4">
                Enter your email address and we'll send you a link to reset your password.
            </p>
            <form method="POST" action="/forgot-password">
                {_csrf_field(csrf_token)}
                <div class="mb-4">
                    <label for="email" class="block text-sm font-medium mb-2">
                        Email
                    </label>
                    <input
                        type="email"
                        id="email"
                        name="email"
                        required
                        class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100"
                        placeholder="Enter email"
                    >
                </div>
                <button
                    type="submit"
                    class="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium
                           py-2 px-4 rounded transition-colors"
                >
                    Send Reset Link
                </button>
            </form>
            <div class="mt-4 text-center">
                <a href="/login" class="text-gray-400 hover:text-white text-sm">
                    &larr; Back to login
                </a>
            </div>
        </div>
    </div>
    """
    return _base("Forgot Password", content)


def reset_password_page(
    token: str,
    error: str | None = None,
    success: str | None = None,
    csrf_token: str = "",
) -> str:
    """Reset password page template."""
    message_html = ""
    if error:
        message_html = f"""
        <div class="bg-red-500/20 border border-red-500 text-red-300 px-4 py-3 rounded mb-4">
            {escape(error)}
        </div>
        """
    elif success:
        message_html = f"""
        <div class="bg-green-500/20 border border-green-500 text-green-300 px-4 py-3 rounded mb-4">
            {escape(success)}
        </div>
        """

    content = f"""
    <div class="flex items-center justify-center min-h-screen">
        <div class="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-md">
            <h1 class="text-2xl font-bold text-center mb-6">Set New Password</h1>
            {message_html}
            <form method="POST" action="/reset-password">
                {_csrf_field(csrf_token)}
                <input type="hidden" name="token" value="{escape(token)}">
                <div class="mb-4">
                    <label for="new_password" class="block text-sm font-medium mb-2">
                        New Password
                    </label>
                    <input
                        type="password"
                        id="new_password"
                        name="new_password"
                        required
                        class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100"
                        placeholder="Enter new password"
                    >
                </div>
                <div class="mb-6">
                    <label for="confirm_password" class="block text-sm font-medium mb-2">
                        Confirm Password
                    </label>
                    <input
                        type="password"
                        id="confirm_password"
                        name="confirm_password"
                        required
                        class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100"
                        placeholder="Confirm new password"
                    >
                </div>
                <button
                    type="submit"
                    class="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium
                           py-2 px-4 rounded transition-colors"
                >
                    Reset Password
                </button>
            </form>
            <div class="mt-4 text-center">
                <a href="/login" class="text-gray-400 hover:text-white text-sm">
                    &larr; Back to login
                </a>
            </div>
        </div>
    </div>
    """
    return _base("Reset Password", content)


def dashboard_page(email: str = "Admin") -> str:
    """Dashboard page template."""
    content = f"""
    <div class="p-6">
        <nav class="flex justify-between items-center mb-8">
            <h1 class="text-2xl font-bold">Bot Admin Dashboard</h1>
            <div class="flex items-center gap-4">
                <span class="text-gray-400">Welcome, {escape(email)}</span>
                <a href="/settings"
                   class="text-gray-400 hover:text-white transition-colors">
                    Settings
                </a>
                <a href="/logout"
                   class="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded transition-colors">
                    Logout
                </a>
            </div>
        </nav>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
            <a href="/lobbies" class="bg-gray-800 p-6 rounded-lg hover:bg-gray-750 transition-colors">
                <h2 class="text-lg font-semibold mb-2">Lobbies</h2>
                <p class="text-gray-400 text-sm">Manage voice lobbies</p>
            </a>
            <a href="/sticky" class="bg-gray-800 p-6 rounded-lg hover:bg-gray-750 transition-colors">
                <h2 class="text-lg font-semibold mb-2">Sticky Messages</h2>
                <p class="text-gray-400 text-sm">Manage sticky messages</p>
            </a>
            <a href="/bump" class="bg-gray-800 p-6 rounded-lg hover:bg-gray-750 transition-colors">
                <h2 class="text-lg font-semibold mb-2">Bump Reminders</h2>
                <p class="text-gray-400 text-sm">Manage bump settings</p>
            </a>
            <a href="/rolepanels" class="bg-gray-800 p-6 rounded-lg hover:bg-gray-750 transition-colors">
                <h2 class="text-lg font-semibold mb-2">Role Panels</h2>
                <p class="text-gray-400 text-sm">View role assignment panels</p>
            </a>
            <a href="/autoban" class="bg-gray-800 p-6 rounded-lg hover:bg-gray-750 transition-colors">
                <h2 class="text-lg font-semibold mb-2">Autoban</h2>
                <p class="text-gray-400 text-sm">Manage autoban rules and logs</p>
            </a>
            <a href="/banlogs" class="bg-gray-800 p-6 rounded-lg hover:bg-gray-750 transition-colors">
                <h2 class="text-lg font-semibold mb-2">Ban Logs</h2>
                <p class="text-gray-400 text-sm">View all ban logs</p>
            </a>
            <a href="/tickets" class="bg-gray-800 p-6 rounded-lg hover:bg-gray-750 transition-colors">
                <h2 class="text-lg font-semibold mb-2">Tickets</h2>
                <p class="text-gray-400 text-sm">Manage support ticket system</p>
            </a>
            <a href="/joinrole" class="bg-gray-800 p-6 rounded-lg hover:bg-gray-750 transition-colors">
                <h2 class="text-lg font-semibold mb-2">Join Role</h2>
                <p class="text-gray-400 text-sm">Auto-assign roles on member join</p>
            </a>
            <a href="/settings/maintenance" class="bg-gray-800 p-6 rounded-lg hover:bg-gray-750 transition-colors">
                <h2 class="text-lg font-semibold mb-2">Database Maintenance</h2>
                <p class="text-gray-400 text-sm">Refresh stats and cleanup orphaned data</p>
            </a>
            <a href="/activity" class="bg-gray-800 p-6 rounded-lg hover:bg-gray-750 transition-colors">
                <h2 class="text-lg font-semibold mb-2">Bot Activity</h2>
                <p class="text-gray-400 text-sm">Change bot presence status</p>
            </a>
        </div>
    </div>
    """
    return _base("Dashboard", content)


def settings_page(
    current_email: str,
    pending_email: str | None = None,
) -> str:
    """Settings hub page template with links to email/password change."""
    pending_email_html = ""
    if pending_email:
        pending_email_html = f"""
        <div class="bg-yellow-500/20 border border-yellow-500 text-yellow-300 px-4 py-3 rounded mb-6">
            Pending email change to: <strong>{escape(pending_email)}</strong><br>
            <span class="text-sm">Please check your inbox and click the confirmation link.</span>
        </div>
        """

    content = f"""
    <div class="p-6">
        {_nav("Settings", show_dashboard_link=True)}
        <div class="max-w-md">
            {pending_email_html}
            <div class="space-y-4">
                <a href="/settings/email"
                   class="block bg-gray-800 p-6 rounded-lg hover:bg-gray-750 transition-colors">
                    <h2 class="text-lg font-semibold mb-2">Change Email</h2>
                    <p class="text-gray-400 text-sm">
                        Current: {escape(current_email)}
                    </p>
                </a>
                <a href="/settings/password"
                   class="block bg-gray-800 p-6 rounded-lg hover:bg-gray-750 transition-colors">
                    <h2 class="text-lg font-semibold mb-2">Change Password</h2>
                    <p class="text-gray-400 text-sm">
                        Update your account password
                    </p>
                </a>
                <a href="/settings/maintenance"
                   class="block bg-gray-800 p-6 rounded-lg hover:bg-gray-750 transition-colors">
                    <h2 class="text-lg font-semibold mb-2">Database Maintenance</h2>
                    <p class="text-gray-400 text-sm">
                        View DB stats and cleanup orphaned data
                    </p>
                </a>
            </div>
        </div>
    </div>
    """
    return _base("Settings", content)


def maintenance_page(
    lobby_total: int,
    lobby_orphaned: int,
    bump_total: int,
    bump_orphaned: int,
    sticky_total: int,
    sticky_orphaned: int,
    panel_total: int,
    panel_orphaned: int,
    guild_count: int,
    success: str | None = None,
    csrf_token: str = "",
) -> str:
    """Database maintenance page template."""
    message_html = ""
    if success:
        message_html = f"""
        <div class="bg-green-500/20 border border-green-500 text-green-300 px-4 py-3 rounded mb-6">
            {escape(success)}
        </div>
        """

    # 孤立データの合計
    total_orphaned = lobby_orphaned + bump_orphaned + sticky_orphaned + panel_orphaned

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Database Maintenance",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Settings", "/settings"),
                ("Database Maintenance", None),
            ],
        )
    }
        <div class="max-w-2xl">
            {message_html}
            <div class="bg-gray-800 p-6 rounded-lg mb-6">
                <h2 class="text-lg font-semibold mb-4">Database Statistics</h2>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                    <div class="bg-gray-700 p-4 rounded">
                        <p class="text-2xl font-bold">{lobby_total}</p>
                        <p class="text-gray-400 text-sm">Lobbies</p>
                        <p class="text-yellow-400 text-xs mt-1">
                            Orphaned: {lobby_orphaned}
                        </p>
                    </div>
                    <div class="bg-gray-700 p-4 rounded">
                        <p class="text-2xl font-bold">{bump_total}</p>
                        <p class="text-gray-400 text-sm">Bump Configs</p>
                        <p class="text-yellow-400 text-xs mt-1">
                            Orphaned: {bump_orphaned}
                        </p>
                    </div>
                    <div class="bg-gray-700 p-4 rounded">
                        <p class="text-2xl font-bold">{sticky_total}</p>
                        <p class="text-gray-400 text-sm">Stickies</p>
                        <p class="text-yellow-400 text-xs mt-1">
                            Orphaned: {sticky_orphaned}
                        </p>
                    </div>
                    <div class="bg-gray-700 p-4 rounded">
                        <p class="text-2xl font-bold">{panel_total}</p>
                        <p class="text-gray-400 text-sm">Role Panels</p>
                        <p class="text-yellow-400 text-xs mt-1">
                            Orphaned: {panel_orphaned}
                        </p>
                    </div>
                </div>
                <div class="mt-4 text-center">
                    <p class="text-gray-400">Active Guilds: <span class="text-white font-semibold">{
        guild_count
    }</span></p>
                </div>
            </div>

            <div class="bg-gray-800 p-6 rounded-lg">
                <h2 class="text-lg font-semibold mb-4">Actions</h2>
                <p class="text-gray-400 text-sm mb-4">
                    <strong>Refresh:</strong> Update statistics from the database.<br>
                    <strong>Cleanup:</strong> Remove records for guilds the bot is no longer a member of.
                </p>
                <div class="flex gap-4 flex-wrap">
                    <form action="/settings/maintenance/refresh" method="POST" class="inline"
                          onsubmit="return handleSubmit(this, 'Refreshing...')">
                        <input type="hidden" name="csrf_token" value="{csrf_token}" />
                        <button type="submit"
                                class="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded font-semibold
                                       transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                            Refresh Stats
                        </button>
                    </form>
                    <button type="button"
                            onclick="showCleanupModal()"
                            class="bg-red-600 hover:bg-red-700 px-6 py-2 rounded font-semibold
                                   transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            {"disabled" if total_orphaned == 0 else ""}>
                        {
        f"Cleanup {total_orphaned} Records"
        if total_orphaned > 0
        else "No Orphaned Data"
    }
                    </button>
                </div>
            </div>
        </div>
    </div>

    <!-- Cleanup Confirmation Modal -->
    <div id="cleanup-modal" class="fixed inset-0 bg-black/50 hidden items-center justify-center z-50">
        <div class="bg-gray-800 rounded-lg p-6 max-w-md mx-4 shadow-xl">
            <h3 class="text-xl font-bold mb-4 text-red-400">Confirm Cleanup</h3>
            <p class="text-gray-300 mb-4">
                The following orphaned data will be permanently deleted:
            </p>
            <div class="bg-gray-700 rounded p-4 mb-4 space-y-2 text-sm">
                {
        ""
        if lobby_orphaned == 0
        else f'<div class="flex justify-between"><span>Lobbies:</span><span class="text-yellow-400">{lobby_orphaned}</span></div>'
    }
                {
        ""
        if bump_orphaned == 0
        else f'<div class="flex justify-between"><span>Bump Configs:</span><span class="text-yellow-400">{bump_orphaned}</span></div>'
    }
                {
        ""
        if sticky_orphaned == 0
        else f'<div class="flex justify-between"><span>Stickies:</span><span class="text-yellow-400">{sticky_orphaned}</span></div>'
    }
                {
        ""
        if panel_orphaned == 0
        else f'<div class="flex justify-between"><span>Role Panels:</span><span class="text-yellow-400">{panel_orphaned}</span></div>'
    }
                <div class="border-t border-gray-600 pt-2 mt-2 flex justify-between font-semibold">
                    <span>Total:</span>
                    <span class="text-red-400">{total_orphaned}</span>
                </div>
            </div>
            <p class="text-gray-400 text-sm mb-4">
                This action cannot be undone.
            </p>
            <div class="flex gap-4 justify-end">
                <button type="button"
                        onclick="hideCleanupModal()"
                        class="bg-gray-600 hover:bg-gray-500 px-4 py-2 rounded font-semibold transition-colors">
                    Cancel
                </button>
                <form action="/settings/maintenance/cleanup" method="POST" class="inline"
                      onsubmit="return handleCleanupSubmit(this)">
                    <input type="hidden" name="csrf_token" value="{csrf_token}" />
                    <button type="submit"
                            id="confirm-cleanup-btn"
                            class="bg-red-600 hover:bg-red-700 px-4 py-2 rounded font-semibold transition-colors">
                        Delete {total_orphaned} Records
                    </button>
                </form>
            </div>
        </div>
    </div>

    <script>
    function handleSubmit(form, loadingText) {{
        const btn = form.querySelector('button[type="submit"]');
        if (btn.disabled) return false;
        btn.disabled = true;
        btn.textContent = loadingText;
        return true;
    }}

    function showCleanupModal() {{
        const modal = document.getElementById('cleanup-modal');
        modal.classList.remove('hidden');
        modal.classList.add('flex');
    }}

    function hideCleanupModal() {{
        const modal = document.getElementById('cleanup-modal');
        modal.classList.add('hidden');
        modal.classList.remove('flex');
    }}

    function handleCleanupSubmit(form) {{
        const btn = document.getElementById('confirm-cleanup-btn');
        btn.disabled = true;
        btn.textContent = 'Cleaning up...';
        return true;
    }}

    // Close modal on backdrop click
    document.getElementById('cleanup-modal').addEventListener('click', function(e) {{
        if (e.target === this) {{
            hideCleanupModal();
        }}
    }});

    // Close modal on Escape key
    document.addEventListener('keydown', function(e) {{
        if (e.key === 'Escape') {{
            hideCleanupModal();
        }}
    }});
    </script>
    """
    return _base("Maintenance", content)


def email_change_page(
    current_email: str,
    pending_email: str | None = None,
    error: str | None = None,
    success: str | None = None,
    csrf_token: str = "",
) -> str:
    """Email change page template."""
    message_html = ""
    if error:
        message_html = f"""
        <div class="bg-red-500/20 border border-red-500 text-red-300 px-4 py-3 rounded mb-4">
            {escape(error)}
        </div>
        """
    elif success:
        message_html = f"""
        <div class="bg-green-500/20 border border-green-500 text-green-300 px-4 py-3 rounded mb-4">
            {escape(success)}
        </div>
        """

    pending_email_html = ""
    if pending_email:
        pending_email_html = f"""
        <div class="bg-yellow-500/20 border border-yellow-500 text-yellow-300 px-4 py-3 rounded mb-4">
            Pending email change to: <strong>{escape(pending_email)}</strong><br>
            <span class="text-sm">Please check your inbox and click the confirmation link.</span>
        </div>
        """

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Change Email",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Settings", "/settings"),
                ("Change Email", None),
            ],
        )
    }
        <div class="max-w-md">
            <div class="bg-gray-800 p-6 rounded-lg">
                {message_html}
                {pending_email_html}
                <p class="text-gray-400 text-sm mb-4">
                    Current email: <strong>{escape(current_email)}</strong>
                </p>
                <form method="POST" action="/settings/email">
                    {_csrf_field(csrf_token)}
                    <div class="mb-6">
                        <label for="new_email" class="block text-sm font-medium mb-2">
                            New Email
                        </label>
                        <input
                            type="email"
                            id="new_email"
                            name="new_email"
                            required
                            class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                                   focus:outline-none focus:ring-2 focus:ring-blue-500
                                   text-gray-100"
                            placeholder="Enter new email address"
                        >
                    </div>
                    <button
                        type="submit"
                        class="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium
                               py-2 px-4 rounded transition-colors"
                    >
                        Send Verification Email
                    </button>
                </form>
                <p class="mt-4 text-gray-500 text-sm">
                    A verification email will be sent to the new address.
                </p>
            </div>
        </div>
    </div>
    """
    return _base("Change Email", content)


def password_change_page(
    error: str | None = None,
    success: str | None = None,
    csrf_token: str = "",
) -> str:
    """Password change page template."""
    message_html = ""
    if error:
        message_html = f"""
        <div class="bg-red-500/20 border border-red-500 text-red-300 px-4 py-3 rounded mb-4">
            {escape(error)}
        </div>
        """
    elif success:
        message_html = f"""
        <div class="bg-green-500/20 border border-green-500 text-green-300 px-4 py-3 rounded mb-4">
            {escape(success)}
        </div>
        """

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Change Password",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Settings", "/settings"),
                ("Change Password", None),
            ],
        )
    }
        <div class="max-w-md">
            <div class="bg-gray-800 p-6 rounded-lg">
                {message_html}
                <form method="POST" action="/settings/password">
                    {_csrf_field(csrf_token)}
                    <div class="mb-4">
                        <label for="new_password" class="block text-sm font-medium mb-2">
                            New Password
                        </label>
                        <input
                            type="password"
                            id="new_password"
                            name="new_password"
                            required
                            class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                                   focus:outline-none focus:ring-2 focus:ring-blue-500
                                   text-gray-100"
                            placeholder="Enter new password"
                        >
                    </div>
                    <div class="mb-6">
                        <label for="confirm_password" class="block text-sm font-medium mb-2">
                            Confirm Password
                        </label>
                        <input
                            type="password"
                            id="confirm_password"
                            name="confirm_password"
                            required
                            class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                                   focus:outline-none focus:ring-2 focus:ring-blue-500
                                   text-gray-100"
                            placeholder="Confirm new password"
                        >
                    </div>
                    <button
                        type="submit"
                        class="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium
                               py-2 px-4 rounded transition-colors"
                    >
                        Change Password
                    </button>
                </form>
                <p class="mt-4 text-gray-500 text-sm">
                    You will be logged out after changing your password.
                </p>
            </div>
        </div>
    </div>
    """
    return _base("Change Password", content)


def initial_setup_page(
    current_email: str,
    error: str | None = None,
    csrf_token: str = "",
) -> str:
    """Initial setup page template (requires email and password change)."""
    message_html = ""
    if error:
        message_html = f"""
        <div class="bg-red-500/20 border border-red-500 text-red-300 px-4 py-3 rounded mb-4">
            {escape(error)}
        </div>
        """

    content = f"""
    <div class="flex items-center justify-center min-h-screen">
        <div class="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-md">
            <h1 class="text-2xl font-bold text-center mb-6">Initial Setup</h1>
            {message_html}
            <p class="text-gray-400 text-sm mb-4">
                Please set up your email address and password to continue.
            </p>
            <form method="POST" action="/initial-setup">
                {_csrf_field(csrf_token)}
                <div class="mb-4">
                    <label for="new_email" class="block text-sm font-medium mb-2">
                        Email Address
                    </label>
                    <input
                        type="email"
                        id="new_email"
                        name="new_email"
                        value="{escape(current_email)}"
                        required
                        class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100"
                        placeholder="Enter your email address"
                    >
                    <p class="text-gray-500 text-xs mt-1">
                        A verification email will be sent to this address.
                    </p>
                </div>
                <div class="mb-4">
                    <label for="new_password" class="block text-sm font-medium mb-2">
                        New Password
                    </label>
                    <input
                        type="password"
                        id="new_password"
                        name="new_password"
                        required
                        class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100"
                        placeholder="Enter new password"
                    >
                </div>
                <div class="mb-6">
                    <label for="confirm_password" class="block text-sm font-medium mb-2">
                        Confirm Password
                    </label>
                    <input
                        type="password"
                        id="confirm_password"
                        name="confirm_password"
                        required
                        class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100"
                        placeholder="Confirm new password"
                    >
                </div>
                <button
                    type="submit"
                    class="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium
                           py-2 px-4 rounded transition-colors"
                >
                    Continue
                </button>
            </form>
        </div>
    </div>
    """
    return _base("Initial Setup", content)


def email_verification_pending_page(
    pending_email: str,
    error: str | None = None,
    success: str | None = None,
    csrf_token: str = "",
) -> str:
    """Email verification pending page template."""
    message_html = ""
    if error:
        message_html = f"""
        <div class="bg-red-500/20 border border-red-500 text-red-300 px-4 py-3 rounded mb-4">
            {escape(error)}
        </div>
        """
    elif success:
        message_html = f"""
        <div class="bg-green-500/20 border border-green-500 text-green-300 px-4 py-3 rounded mb-4">
            {escape(success)}
        </div>
        """

    content = f"""
    <div class="flex items-center justify-center min-h-screen">
        <div class="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-md">
            <h1 class="text-2xl font-bold text-center mb-6">Verify Your Email</h1>
            {message_html}
            <div class="text-center">
                <p class="text-gray-300 mb-4">
                    A verification email has been sent to:
                </p>
                <p class="text-blue-400 font-semibold mb-6">
                    {escape(pending_email)}
                </p>
                <p class="text-gray-400 text-sm mb-6">
                    Please check your inbox and click the verification link to continue.
                </p>
                <form method="POST" action="/resend-verification" class="mb-4">
                    {_csrf_field(csrf_token)}
                    <button
                        type="submit"
                        class="w-full bg-gray-700 hover:bg-gray-600 text-white font-medium
                               py-2 px-4 rounded transition-colors"
                    >
                        Resend Verification Email
                    </button>
                </form>
                <a href="/logout" class="text-gray-400 hover:text-white text-sm">
                    Logout
                </a>
            </div>
        </div>
    </div>
    """
    return _base("Verify Email", content)


def lobbies_list_page(
    lobbies: list["Lobby"],
    csrf_token: str = "",
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
) -> str:
    """Lobbies list page template.

    Args:
        lobbies: ロビーのリスト
        csrf_token: CSRF トークン
        guilds_map: ギルドID -> ギルド名 のマッピング
        channels_map: ギルドID -> [(チャンネルID, チャンネル名), ...] のマッピング
    """
    if guilds_map is None:
        guilds_map = {}
    if channels_map is None:
        channels_map = {}

    def get_channel_name(guild_id: str, channel_id: str) -> str | None:
        """チャンネル名を取得する。"""
        guild_channels = channels_map.get(guild_id, [])
        for cid, name in guild_channels:
            if cid == channel_id:
                return name
        return None

    row_parts: list[str] = []
    for lobby in lobbies:
        session_count = len(lobby.sessions) if lobby.sessions else 0
        guild_name = guilds_map.get(lobby.guild_id)
        channel_name = get_channel_name(lobby.guild_id, lobby.lobby_channel_id)

        # サーバー名表示
        if guild_name:
            guild_display = (
                f'<span class="font-medium">{escape(guild_name)}</span>'
                f'<br><span class="font-mono text-xs text-gray-500">'
                f"{escape(lobby.guild_id)}</span>"
            )
        else:
            guild_display = (
                f'<span class="font-mono text-yellow-400">'
                f"{escape(lobby.guild_id)}</span>"
            )

        # チャンネル名表示
        if channel_name:
            channel_display = (
                f'<span class="font-medium">#{escape(channel_name)}</span>'
                f'<br><span class="font-mono text-xs text-gray-500">'
                f"{escape(lobby.lobby_channel_id)}</span>"
            )
        else:
            channel_display = (
                f'<span class="font-mono text-yellow-400">'
                f"{escape(lobby.lobby_channel_id)}</span>"
            )

        row_parts.append(f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 align-middle">{lobby.id}</td>
            <td class="py-3 px-4 align-middle">{guild_display}</td>
            <td class="py-3 px-4 align-middle">{channel_display}</td>
            <td class="py-3 px-4 align-middle">{lobby.default_user_limit or "無制限"}</td>
            <td class="py-3 px-4 align-middle">{session_count}</td>
            <td class="py-3 px-4 align-middle">
                <a href="#" onclick="postAction('/lobbies/{lobby.id}/delete', '{csrf_token}', 'Delete this lobby?'); return false;"
                   class="text-red-400 hover:text-red-300 text-sm">Delete</a>
            </td>
        </tr>
        """)
    rows = "".join(row_parts)

    if not lobbies:
        rows = """
        <tr>
            <td colspan="6" class="py-8 text-center text-gray-500">
                No lobbies configured
            </td>
        </tr>
        """

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Lobbies",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Lobbies", None),
            ],
        )
    }
        <div class="bg-gray-800 rounded-lg overflow-hidden">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="py-3 px-4 text-left">ID</th>
                        <th class="py-3 px-4 text-left">Server</th>
                        <th class="py-3 px-4 text-left">Channel</th>
                        <th class="py-3 px-4 text-left">User Limit</th>
                        <th class="py-3 px-4 text-left">Active Sessions</th>
                        <th class="py-3 px-4 text-left">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
        <p class="mt-4 text-gray-500 text-sm">
            Lobbies are created via Discord command: /voice lobby set
        </p>
    </div>
    """
    return _base("Lobbies", content)


def sticky_list_page(
    stickies: list["StickyMessage"],
    csrf_token: str = "",
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
) -> str:
    """Sticky messages list page template.

    Args:
        stickies: スティッキーメッセージのリスト
        csrf_token: CSRF トークン
        guilds_map: ギルドID -> ギルド名 のマッピング
        channels_map: ギルドID -> [(チャンネルID, チャンネル名), ...] のマッピング
    """
    if guilds_map is None:
        guilds_map = {}
    if channels_map is None:
        channels_map = {}

    def get_channel_name(guild_id: str, channel_id: str) -> str | None:
        """チャンネル名を取得する。"""
        guild_channels = channels_map.get(guild_id, [])
        for cid, name in guild_channels:
            if cid == channel_id:
                return name
        return None

    row_parts: list[str] = []
    for sticky in stickies:
        title_display = (
            escape(
                sticky.title[:30] + "..." if len(sticky.title) > 30 else sticky.title
            )
            or "(no title)"
        )
        desc_display = escape(
            sticky.description[:50] + "..."
            if len(sticky.description) > 50
            else sticky.description
        )
        color_display = f"#{sticky.color:06x}" if sticky.color else "-"

        guild_name = guilds_map.get(sticky.guild_id)
        channel_name = get_channel_name(sticky.guild_id, sticky.channel_id)

        # サーバー名表示
        if guild_name:
            guild_display = (
                f'<span class="font-medium">{escape(guild_name)}</span>'
                f'<br><span class="font-mono text-xs text-gray-500">'
                f"{escape(sticky.guild_id)}</span>"
            )
        else:
            guild_display = (
                f'<span class="font-mono text-yellow-400">'
                f"{escape(sticky.guild_id)}</span>"
            )

        # チャンネル名表示
        if channel_name:
            channel_display = (
                f'<span class="font-medium">#{escape(channel_name)}</span>'
                f'<br><span class="font-mono text-xs text-gray-500">'
                f"{escape(sticky.channel_id)}</span>"
            )
        else:
            channel_display = (
                f'<span class="font-mono text-yellow-400">'
                f"{escape(sticky.channel_id)}</span>"
            )

        row_parts.append(f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 align-middle">{guild_display}</td>
            <td class="py-3 px-4 align-middle">{channel_display}</td>
            <td class="py-3 px-4 align-middle">{title_display}</td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">{desc_display}</td>
            <td class="py-3 px-4 align-middle">{escape(sticky.message_type)}</td>
            <td class="py-3 px-4 align-middle">{sticky.cooldown_seconds}s</td>
            <td class="py-3 px-4 align-middle">
                <span class="inline-block w-4 h-4 rounded" style="background-color: {color_display if sticky.color else "transparent"}"></span>
                {color_display}
            </td>
            <td class="py-3 px-4 align-middle">
                <a href="#" onclick="postAction('/sticky/{sticky.channel_id}/delete', '{csrf_token}', 'Delete this sticky message?'); return false;"
                   class="text-red-400 hover:text-red-300 text-sm">Delete</a>
            </td>
        </tr>
        """)
    rows = "".join(row_parts)

    if not stickies:
        rows = """
        <tr>
            <td colspan="8" class="py-8 text-center text-gray-500">
                No sticky messages configured
            </td>
        </tr>
        """

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Sticky Messages",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Sticky Messages", None),
            ],
        )
    }
        <div class="bg-gray-800 rounded-lg overflow-hidden overflow-x-auto">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="py-3 px-4 text-left">Server</th>
                        <th class="py-3 px-4 text-left">Channel</th>
                        <th class="py-3 px-4 text-left">Title</th>
                        <th class="py-3 px-4 text-left">Description</th>
                        <th class="py-3 px-4 text-left">Type</th>
                        <th class="py-3 px-4 text-left">Cooldown</th>
                        <th class="py-3 px-4 text-left">Color</th>
                        <th class="py-3 px-4 text-left">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
        <p class="mt-4 text-gray-500 text-sm">
            Sticky messages are created via Discord command: /sticky set
        </p>
    </div>
    """
    return _base("Sticky Messages", content)


def bump_list_page(
    configs: list["BumpConfig"],
    reminders: list["BumpReminder"],
    csrf_token: str = "",
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
) -> str:
    """Bump configs and reminders list page template.

    Args:
        configs: Bump 設定のリスト
        reminders: Bump リマインダーのリスト
        csrf_token: CSRF トークン
        guilds_map: ギルドID -> ギルド名 のマッピング
        channels_map: ギルドID -> [(チャンネルID, チャンネル名), ...] のマッピング
    """
    if guilds_map is None:
        guilds_map = {}
    if channels_map is None:
        channels_map = {}

    def get_channel_name(guild_id: str, channel_id: str) -> str | None:
        """チャンネル名を取得する。"""
        guild_channels = channels_map.get(guild_id, [])
        for cid, name in guild_channels:
            if cid == channel_id:
                return name
        return None

    def format_guild_display(guild_id: str) -> str:
        """サーバー名の表示を生成する。"""
        guild_name = guilds_map.get(guild_id)
        if guild_name:
            return (
                f'<span class="font-medium">{escape(guild_name)}</span>'
                f'<br><span class="font-mono text-xs text-gray-500">'
                f"{escape(guild_id)}</span>"
            )
        return f'<span class="font-mono text-yellow-400">{escape(guild_id)}</span>'

    def format_channel_display(guild_id: str, channel_id: str) -> str:
        """チャンネル名の表示を生成する。"""
        channel_name = get_channel_name(guild_id, channel_id)
        if channel_name:
            return (
                f'<span class="font-medium">#{escape(channel_name)}</span>'
                f'<br><span class="font-mono text-xs text-gray-500">'
                f"{escape(channel_id)}</span>"
            )
        return f'<span class="font-mono text-yellow-400">{escape(channel_id)}</span>'

    config_row_parts: list[str] = []
    for config in configs:
        guild_display = format_guild_display(config.guild_id)
        channel_display = format_channel_display(config.guild_id, config.channel_id)
        config_row_parts.append(f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 align-middle">{guild_display}</td>
            <td class="py-3 px-4 align-middle">{channel_display}</td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">
                {format_datetime(config.created_at)}
            </td>
            <td class="py-3 px-4 align-middle">
                <a href="#" onclick="postAction('/bump/config/{config.guild_id}/delete', '{csrf_token}', 'Delete this bump config?'); return false;"
                   class="text-red-400 hover:text-red-300 text-sm">Delete</a>
            </td>
        </tr>
        """)
    config_rows = "".join(config_row_parts)

    if not configs:
        config_rows = """
        <tr>
            <td colspan="4" class="py-8 text-center text-gray-500">
                No bump configs
            </td>
        </tr>
        """

    reminder_row_parts: list[str] = []
    for reminder in reminders:
        status = "Enabled" if reminder.is_enabled else "Disabled"
        status_class = "text-green-400" if reminder.is_enabled else "text-gray-500"
        remind_at = format_datetime(reminder.remind_at)
        guild_display = format_guild_display(reminder.guild_id)
        channel_display = format_channel_display(reminder.guild_id, reminder.channel_id)
        reminder_row_parts.append(f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 align-middle">{reminder.id}</td>
            <td class="py-3 px-4 align-middle">{guild_display}</td>
            <td class="py-3 px-4 align-middle">{escape(reminder.service_name)}</td>
            <td class="py-3 px-4 align-middle">{channel_display}</td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">{remind_at}</td>
            <td class="py-3 px-4 align-middle">
                <span class="{status_class}">{status}</span>
            </td>
            <td class="py-3 px-4 align-middle space-x-2">
                <a href="#" onclick="postAction('/bump/reminder/{reminder.id}/toggle', '{csrf_token}'); return false;"
                   class="text-blue-400 hover:text-blue-300 text-sm">Toggle</a>
                <a href="#" onclick="postAction('/bump/reminder/{reminder.id}/delete', '{csrf_token}', 'Delete this reminder?'); return false;"
                   class="text-red-400 hover:text-red-300 text-sm">Delete</a>
            </td>
        </tr>
        """)
    reminder_rows = "".join(reminder_row_parts)

    if not reminders:
        reminder_rows = """
        <tr>
            <td colspan="7" class="py-8 text-center text-gray-500">
                No bump reminders
            </td>
        </tr>
        """

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Bump Reminders",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Bump Reminders", None),
            ],
        )
    }

        <h2 class="text-xl font-semibold mb-4">Bump Configs</h2>
        <div class="bg-gray-800 rounded-lg overflow-hidden mb-8">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="py-3 px-4 text-left">Server</th>
                        <th class="py-3 px-4 text-left">Channel</th>
                        <th class="py-3 px-4 text-left">Created</th>
                        <th class="py-3 px-4 text-left">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {config_rows}
                </tbody>
            </table>
        </div>

        <h2 class="text-xl font-semibold mb-4">Bump Reminders</h2>
        <div class="bg-gray-800 rounded-lg overflow-hidden">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="py-3 px-4 text-left">ID</th>
                        <th class="py-3 px-4 text-left">Server</th>
                        <th class="py-3 px-4 text-left">Service</th>
                        <th class="py-3 px-4 text-left">Channel</th>
                        <th class="py-3 px-4 text-left">Remind At</th>
                        <th class="py-3 px-4 text-left">Status</th>
                        <th class="py-3 px-4 text-left">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {reminder_rows}
                </tbody>
            </table>
        </div>
        <p class="mt-4 text-gray-500 text-sm">
            Bump configs are created via Discord command: /bump setup
        </p>
    </div>
    """
    return _base("Bump Reminders", content)


def role_panels_list_page(
    panels: list["RolePanel"],
    items_by_panel: dict[int, list["RolePanelItem"]],
    csrf_token: str = "",
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
) -> str:
    """Role panels list page template.

    Args:
        panels: ロールパネルのリスト
        items_by_panel: パネルID -> アイテムリスト のマッピング
        csrf_token: CSRF トークン
        guilds_map: ギルドID -> ギルド名 のマッピング
        channels_map: ギルドID -> [(チャンネルID, チャンネル名), ...] のマッピング
    """
    if guilds_map is None:
        guilds_map = {}
    if channels_map is None:
        channels_map = {}

    def get_channel_name(guild_id: str, channel_id: str) -> str | None:
        """チャンネル名を取得する。"""
        guild_channels = channels_map.get(guild_id, [])
        for cid, name in guild_channels:
            if cid == channel_id:
                return name
        return None

    panel_row_parts: list[str] = []
    for panel in panels:
        panel_type_badge = (
            '<span class="bg-blue-600 px-2 py-1 rounded text-xs">Button</span>'
            if panel.panel_type == "button"
            else '<span class="bg-purple-600 px-2 py-1 rounded text-xs">Reaction</span>'
        )
        remove_reaction_badge = ""
        if panel.panel_type == "reaction" and panel.remove_reaction:
            remove_reaction_badge = (
                '<span class="bg-yellow-600 px-2 py-1 rounded text-xs ml-1'
                ' whitespace-nowrap">Auto-remove</span>'
            )

        items = items_by_panel.get(panel.id, [])

        created_at = format_datetime(panel.created_at)

        guild_name = guilds_map.get(panel.guild_id)
        channel_name = get_channel_name(panel.guild_id, panel.channel_id)

        # サーバー名表示
        if guild_name:
            guild_display = (
                f'<span class="font-medium">{escape(guild_name)}</span>'
                f'<br><span class="font-mono text-xs text-gray-500">'
                f"{escape(panel.guild_id)}</span>"
            )
        else:
            guild_display = (
                f'<span class="font-mono text-yellow-400">'
                f"{escape(panel.guild_id)}</span>"
            )

        # チャンネル名表示
        if channel_name:
            channel_display = (
                f'<span class="font-medium">#{escape(channel_name)}</span>'
                f'<br><span class="font-mono text-xs text-gray-500">'
                f"{escape(panel.channel_id)}</span>"
            )
        else:
            channel_display = (
                f'<span class="font-mono text-yellow-400">'
                f"{escape(panel.channel_id)}</span>"
            )

        panel_row_parts.append(f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 align-middle">
                <a href="/rolepanels/{panel.id}"
                   class="font-medium text-blue-400 hover:text-blue-300">
                    {escape(panel.title)}
                </a>
            </td>
            <td class="py-3 px-4 align-middle whitespace-nowrap">
                {panel_type_badge}{remove_reaction_badge}
            </td>
            <td class="py-3 px-4 align-middle">{guild_display}</td>
            <td class="py-3 px-4 align-middle">{channel_display}</td>
            <td class="py-3 px-4 align-middle text-sm">{len(items)} role(s)</td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">{created_at}</td>
            <td class="py-3 px-4 align-middle space-x-2">
                <a href="/rolepanels/{panel.id}"
                   class="text-blue-400 hover:text-blue-300 text-sm">Edit</a>
                <a href="#" onclick="postAction('/rolepanels/{panel.id}/copy', '{csrf_token}'); return false;"
                   class="text-gray-400 hover:text-gray-200 text-sm">Copy</a>
                <a href="#" onclick="postAction('/rolepanels/{panel.id}/delete', '{csrf_token}', 'Delete this role panel?'); return false;"
                   class="text-red-400 hover:text-red-300 text-sm">Delete</a>
            </td>
        </tr>
        """)
    panel_rows = "".join(panel_row_parts)

    if not panels:
        panel_rows = """
        <tr>
            <td colspan="7" class="py-8 text-center text-gray-500">
                No role panels configured
            </td>
        </tr>
        """

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Role Panels",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Role Panels", None),
            ],
        )
    }

        <div class="flex justify-end mb-4">
            <a href="/rolepanels/new"
               class="bg-blue-600 hover:bg-blue-700 text-white font-medium
                      py-2 px-4 rounded transition-colors">
                + Create Panel
            </a>
        </div>

        <div class="bg-gray-800 rounded-lg overflow-hidden">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="py-3 px-4 text-left">Title</th>
                        <th class="py-3 px-4 text-left">Type</th>
                        <th class="py-3 px-4 text-left">Server</th>
                        <th class="py-3 px-4 text-left">Channel</th>
                        <th class="py-3 px-4 text-left">Roles</th>
                        <th class="py-3 px-4 text-left">Created</th>
                        <th class="py-3 px-4 text-left">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {panel_rows}
                </tbody>
            </table>
        </div>
        <p class="mt-4 text-gray-500 text-sm">
            Click on a panel title to add/manage roles, or use /rolepanel add in Discord.
        </p>
    </div>
    """
    return _base("Role Panels", content)


def role_panel_create_page(
    error: str | None = None,
    guild_id: str = "",
    channel_id: str = "",
    panel_type: str = "button",
    title: str = "",
    description: str = "",
    use_embed: bool = True,
    color: str = "",
    remove_reaction: bool = False,
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
    discord_roles: dict[str, list[tuple[str, str, int]]] | None = None,
    csrf_token: str = "",
    existing_items: list[dict[str, str | int | None]] | None = None,
) -> str:
    """Role panel create page template.

    Args:
        use_embed: メッセージ形式 (True: Embed, False: テキスト)
        color: Embed のカラーコード (例: "#85E7AD")
        remove_reaction: リアクション自動削除フラグ (リアクション式のみ)
        guilds_map: ギルドID -> ギルド名 のマッピング
        channels_map: ギルドID -> [(channel_id, channel_name), ...] のマッピング
        discord_roles: ギルドID -> [(role_id, role_name, color), ...] のマッピング
        existing_items: バリデーションエラー時に保持するロールアイテムのリスト
    """
    if guilds_map is None:
        guilds_map = {}
    if channels_map is None:
        channels_map = {}
    if discord_roles is None:
        discord_roles = {}

    message_html = ""
    if error:
        message_html = f"""
        <div class="bg-red-500/20 border border-red-500 text-red-300 px-4 py-3 rounded mb-4">
            {escape(error)}
        </div>
        """

    # ギルドが登録されていない場合の警告
    no_guilds_warning = ""
    if not guilds_map:
        no_guilds_warning = """
        <div class="bg-yellow-500/20 border border-yellow-500 text-yellow-300 px-4 py-3 rounded mb-4">
            No guilds available. Please start the Bot first to sync guild and channel information.
        </div>
        """

    # Panel type selection
    button_selected = "checked" if panel_type == "button" else ""
    reaction_selected = "checked" if panel_type == "reaction" else ""

    # Message format selection
    embed_selected = "checked" if use_embed else ""
    text_selected = "" if use_embed else "checked"

    # Remove reaction checkbox
    remove_reaction_checked = "checked" if remove_reaction else ""

    # Guild select options (名前で表示)
    guild_options = ""
    for gid, gname in sorted(guilds_map.items(), key=lambda x: x[1]):
        selected = "selected" if gid == guild_id else ""
        guild_options += (
            f'<option value="{escape(gid)}" {selected}>{escape(gname)}</option>\n'
        )

    # Channel/Role データを JavaScript 用に JSON 化
    import json

    # channels_map を JavaScript で使いやすい形式に変換: {guild_id: [{id, name}, ...]}
    channels_for_js: dict[str, list[dict[str, str]]] = {}
    for gid, channels in channels_map.items():
        channels_for_js[gid] = [{"id": c[0], "name": c[1]} for c in channels]
    channels_json = json.dumps(channels_for_js)

    # discord_roles を JavaScript で使いやすい形式に変換: {guild_id: [{id, name, color}, ...]}
    discord_roles_for_js: dict[str, list[dict[str, str | int]]] = {}
    for gid, roles in discord_roles.items():
        discord_roles_for_js[gid] = [
            {"id": r[0], "name": r[1], "color": r[2]} for r in roles
        ]
    discord_roles_json = json.dumps(discord_roles_for_js)

    # バリデーションエラー時に保持するロールアイテムを JSON 化
    existing_items_json = json.dumps(existing_items or [])

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Create Role Panel",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Role Panels", "/rolepanels"),
                ("Create", None),
            ],
        )
    }

        {message_html}
        {no_guilds_warning}

        <form method="POST" action="/rolepanels/new" id="createPanelForm">
            {_csrf_field(csrf_token)}

            <!-- Card 1: Panel Settings -->
            <div class="bg-gray-800 p-6 rounded-lg mb-6">
                <h2 class="text-lg font-semibold mb-4">Panel Settings</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <label for="guild_select" class="block text-sm font-medium mb-2">
                            Server <span class="text-red-400">*</span>
                        </label>
                        <select
                            id="guild_select"
                            name="guild_id"
                            required
                            class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                                   focus:outline-none focus:ring-2 focus:ring-blue-500
                                   text-gray-100"
                            {"disabled" if not guilds_map else ""}
                        >
                            <option value="">-- Select Server --</option>
                            {guild_options}
                        </select>
                    </div>
                    <div>
                        <label for="channel_select" class="block text-sm font-medium mb-2">
                            Channel <span class="text-red-400">*</span>
                        </label>
                        <select
                            id="channel_select"
                            name="channel_id"
                            required
                            class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                                   focus:outline-none focus:ring-2 focus:ring-blue-500
                                   text-gray-100"
                            {"disabled" if not guilds_map else ""}
                        >
                            <option value="">-- Select Channel --</option>
                        </select>
                    </div>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                    <div>
                        <label class="block text-sm font-medium mb-2">
                            Panel Type <span class="text-red-400">*</span>
                        </label>
                        <div class="flex gap-4">
                            <label class="flex items-center gap-2 cursor-pointer">
                                <input type="radio" name="panel_type" value="button"
                                       {button_selected}
                                       class="text-blue-500 focus:ring-blue-500">
                                <span>Button</span>
                            </label>
                            <label class="flex items-center gap-2 cursor-pointer">
                                <input type="radio" name="panel_type" value="reaction"
                                       {reaction_selected}
                                       class="text-blue-500 focus:ring-blue-500">
                                <span>Reaction</span>
                            </label>
                        </div>
                    </div>
                    <div>
                        <label class="block text-sm font-medium mb-2">
                            Message Format
                        </label>
                        <div class="flex gap-4">
                            <label class="flex items-center gap-2 cursor-pointer">
                                <input type="radio" name="use_embed" value="1"
                                       {embed_selected}
                                       class="text-blue-500 focus:ring-blue-500">
                                <span>Embed</span>
                            </label>
                            <label class="flex items-center gap-2 cursor-pointer">
                                <input type="radio" name="use_embed" value="0"
                                       {text_selected}
                                       class="text-blue-500 focus:ring-blue-500">
                                <span>Text</span>
                            </label>
                        </div>
                    </div>
                </div>

                <!-- Embed Color option (embed only) -->
                <div id="embedColorOption" class="mt-4{
        " hidden" if not use_embed else ""
    }">
                    <label for="embed_color" class="block text-sm font-medium mb-2">
                        Embed Color
                    </label>
                    <div class="flex items-center gap-3">
                        <input
                            type="color"
                            id="embed_color"
                            name="color"
                            value="{color if color else "#85E7AD"}"
                            class="w-12 h-10 p-1 bg-gray-700 border border-gray-600 rounded
                                   cursor-pointer focus:outline-none focus:ring-2
                                   focus:ring-blue-500"
                        >
                        <input
                            type="text"
                            id="embed_color_text"
                            value="{color if color else "#85E7AD"}"
                            maxlength="7"
                            pattern="#[0-9A-Fa-f]{{6}}"
                            class="w-28 px-3 py-2 bg-gray-700 border border-gray-600 rounded
                                   focus:outline-none focus:ring-2 focus:ring-blue-500
                                   text-gray-100 font-mono text-sm"
                            placeholder="#85E7AD"
                        >
                    </div>
                </div>

                <!-- Remove Reaction option (reaction type only) -->
                <div id="removeReactionOption" class="mt-4 hidden">
                    <label class="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" name="remove_reaction" value="1"
                               id="removeReactionCheckbox"
                               {remove_reaction_checked}
                               class="rounded bg-gray-700 border-gray-600
                                      text-blue-500 focus:ring-blue-500">
                        <span>Auto-remove reactions</span>
                    </label>
                    <p class="text-gray-500 text-xs mt-1 ml-6">
                        When enabled, reactions are automatically removed after toggling the role.
                        Each reaction stays at count 1.
                    </p>
                </div>
            </div>

            <!-- Card 2: Title & Description -->
            <div class="bg-gray-800 p-6 rounded-lg mb-6">
                <h2 class="text-lg font-semibold mb-4">Title & Description</h2>
                <div class="grid grid-cols-1 gap-4">
                    <div>
                        <label for="title" class="block text-sm font-medium mb-2">
                            Title <span class="text-red-400">*</span>
                        </label>
                        <input
                            type="text"
                            id="title"
                            name="title"
                            value="{escape(title)}"
                            required
                            maxlength="256"
                            class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                                   focus:outline-none focus:ring-2 focus:ring-blue-500
                                   text-gray-100"
                            placeholder="Role Selection"
                        >
                    </div>
                    <div>
                        <label for="description" class="block text-sm font-medium mb-2">
                            Description
                        </label>
                        <textarea
                            id="description"
                            name="description"
                            rows="3"
                            maxlength="4096"
                            class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                                   focus:outline-none focus:ring-2 focus:ring-blue-500
                                   text-gray-100"
                            placeholder="Click a button to get or remove a role"
                        >{escape(description)}</textarea>
                    </div>
                </div>
            </div>

            <!-- Card 3: Role Items -->
            <div class="bg-gray-800 p-6 rounded-lg mb-6">
                <h2 class="text-lg font-semibold mb-4">
                    Role Items (<span id="itemCount">0</span>)
                </h2>
                <p id="noKnownRolesInfo" class="text-red-400 text-xs mb-4 hidden">
                    No roles found for this guild. Please sync roles by starting the Bot first.
                </p>
                <table class="w-full table-fixed" id="roleItemsTable">
                    <thead class="bg-gray-700">
                        <tr>
                            <th class="py-2 px-1 w-8"></th>
                            <th class="py-2 px-2 text-left w-20">Emoji</th>
                            <th class="py-2 px-2 text-left">Role</th>
                            <th class="py-2 px-2 text-left label-field">Label</th>
                            <th class="py-2 px-2 text-left style-field w-28">Style</th>
                            <th class="py-2 px-2 text-left w-16">Actions</th>
                        </tr>
                    </thead>
                    <tbody id="roleItemsContainer">
                    </tbody>
                </table>
                <p id="noRolesInfo" class="py-8 text-center text-gray-500 hidden">
                    No roles configured. Add roles below.
                </p>
                <p id="noRolesWarning" class="text-yellow-400 text-sm mt-2 hidden">
                    Please add at least one role item.
                </p>
                <div class="mt-4">
                    <button
                        type="button"
                        id="addRoleItemBtn"
                        class="bg-green-600 hover:bg-green-700 text-white font-medium
                               py-2 px-4 rounded transition-colors disabled:opacity-50
                               disabled:cursor-not-allowed disabled:hover:bg-green-600"
                    >
                        + Add Role
                    </button>
                </div>
            </div>

            <!-- Action Buttons -->
            <div class="flex gap-3">
                <button
                    type="submit"
                    name="action"
                    value="save_draft"
                    id="saveDraftBtn"
                    class="bg-gray-600 hover:bg-gray-500 text-white font-medium
                           py-2 px-6 rounded transition-colors disabled:opacity-50
                           disabled:cursor-not-allowed"
                    disabled
                >
                    Save &amp; Continue Editing
                </button>
                <button
                    type="submit"
                    name="action"
                    value="create"
                    id="submitBtn"
                    class="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-medium
                           py-2 px-4 rounded transition-colors disabled:opacity-50
                           disabled:cursor-not-allowed"
                    disabled
                >
                    Create Panel
                </button>
            </div>
        </form>
    </div>

    <script>
    (function() {{
        const guildChannels = {channels_json};
        const guildSelect = document.getElementById('guild_select');
        const channelSelect = document.getElementById('channel_select');

        // 初期値を保存
        const initialGuildId = "{escape(guild_id)}";
        const initialChannelId = "{escape(channel_id)}";

        function updateChannelOptions(selectedGuildId) {{
            // チャンネル選択をリセット
            channelSelect.innerHTML = '<option value="">-- Select Channel --</option>';

            if (selectedGuildId && guildChannels[selectedGuildId]) {{
                const channels = guildChannels[selectedGuildId];
                channels.forEach(function(ch) {{
                    const option = document.createElement('option');
                    option.value = ch.id;
                    option.textContent = '#' + ch.name;
                    if (ch.id === initialChannelId) {{
                        option.selected = true;
                    }}
                    channelSelect.appendChild(option);
                }});
            }}
        }}

        // ギルド選択変更時
        guildSelect.addEventListener('change', function() {{
            updateChannelOptions(this.value);
            // ロール情報の更新は後で定義される関数を呼び出す
            if (typeof updateRolesInfo === 'function') {{
                updateRolesInfo();
            }}
        }});

        // 初期状態を設定
        if (initialGuildId && guildChannels[initialGuildId]) {{
            guildSelect.value = initialGuildId;
            updateChannelOptions(initialGuildId);
            if (initialChannelId) {{
                channelSelect.value = initialChannelId;
            }}
        }}

        // --- Embed Color Picker ---
        const embedColorOption = document.getElementById('embedColorOption');
        const embedColorPicker = document.getElementById('embed_color');
        const embedColorText = document.getElementById('embed_color_text');
        const useEmbedRadios = document.querySelectorAll('input[name="use_embed"]');

        // カラーピッカーとテキスト入力を同期
        embedColorPicker.addEventListener('input', function() {{
            embedColorText.value = this.value.toUpperCase();
        }});

        embedColorText.addEventListener('input', function() {{
            // 有効なカラーコードかチェック
            if (/^#[0-9A-Fa-f]{{6}}$/.test(this.value)) {{
                embedColorPicker.value = this.value;
            }}
        }});

        // Embed/Text 選択でカラーピッカーの表示を切り替え
        useEmbedRadios.forEach(function(radio) {{
            radio.addEventListener('change', function() {{
                if (this.value === '1') {{
                    embedColorOption.classList.remove('hidden');
                }} else {{
                    embedColorOption.classList.add('hidden');
                }}
            }});
        }});

        // --- Role Items Management ---
        const discordRoles = {discord_roles_json};
        const existingItems = {existing_items_json};
        const roleItemsContainer = document.getElementById('roleItemsContainer');
        const roleItemsTable = document.getElementById('roleItemsTable');
        const addRoleItemBtn = document.getElementById('addRoleItemBtn');
        const submitBtn = document.getElementById('submitBtn');
        const saveDraftBtn = document.getElementById('saveDraftBtn');
        const noRolesWarning = document.getElementById('noRolesWarning');
        const noKnownRolesInfo = document.getElementById('noKnownRolesInfo');
        const noRolesInfo = document.getElementById('noRolesInfo');
        const itemCountSpan = document.getElementById('itemCount');
        let roleItemIndex = 0;

        function updateSubmitButton() {{
            const itemCount = roleItemsContainer.querySelectorAll('.role-item-row').length;
            const hasGuild = guildSelect.value !== '';
            submitBtn.disabled = itemCount === 0 || !hasGuild;
            saveDraftBtn.disabled = !hasGuild;
            noRolesWarning.classList.toggle('hidden', itemCount > 0);
            itemCountSpan.textContent = itemCount;
            // テーブルとプレースホルダの表示切替
            roleItemsTable.classList.toggle('hidden', itemCount === 0);
            noRolesInfo.classList.toggle('hidden', itemCount > 0);
        }}

        function updateRolesInfo() {{
            const availableRoles = getRolesForCurrentGuild();
            const hasRoles = availableRoles.length > 0;
            noKnownRolesInfo.classList.toggle('hidden', hasRoles);
            // ロールがない場合は Add Role ボタンを非活性化
            addRoleItemBtn.disabled = !hasRoles;
            updateSubmitButton();
        }}

        function getCurrentGuildId() {{
            return guildSelect.value;
        }}

        function getRolesForCurrentGuild() {{
            const currentGuildId = getCurrentGuildId();
            return discordRoles[currentGuildId] || [];
        }}

        // ロールの色を CSS 色文字列に変換
        function colorToHex(color) {{
            if (!color) return '#99aab5';  // デフォルトグレー
            return '#' + color.toString(16).padStart(6, '0');
        }}

        // HTML エスケープ
        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}

        function createRoleItemRow(index, prefill) {{
            const row = document.createElement('tr');
            row.className = 'role-item-row border-b border-gray-700';
            row.draggable = true;

            const availableRoles = getRolesForCurrentGuild();
            let roleSelectHtml = '';
            if (availableRoles.length > 0) {{
                roleSelectHtml = `
                    <div class="role-autocomplete relative">
                        <input
                            type="text"
                            class="role-input w-full px-2 py-1 bg-gray-600 border border-gray-500 rounded
                                   focus:outline-none focus:ring-2 focus:ring-blue-500
                                   text-gray-100 text-sm"
                            placeholder="Type to search roles..."
                            autocomplete="off"
                        >
                        <div class="role-dropdown absolute z-50 w-full mt-1 bg-gray-700 border border-gray-500
                                    rounded shadow-lg max-h-48 overflow-y-auto hidden">
                        </div>
                    </div>
                `;
            }}

            row.innerHTML = `
                <td class="py-1 px-1 align-middle cursor-grab active:cursor-grabbing text-gray-400 hover:text-gray-200">
                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M7 2a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm6 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM7 8a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm6 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm-6 6a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm6 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4z"/>
                    </svg>
                    <input type="hidden" name="item_position[]" class="position-input" value="${{index}}">
                </td>
                <td class="py-1 px-2 align-middle">
                    <input
                        type="text"
                        name="item_emoji[]"
                        required
                        maxlength="64"
                        class="w-full px-2 py-1 bg-gray-600 border border-gray-500 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100 text-sm"
                        placeholder="🎮"
                    >
                </td>
                <td class="py-1 px-2 align-middle">
                    ${{roleSelectHtml}}
                    <input
                        type="hidden"
                        name="item_role_id[]"
                        class="role-id-input"
                    >
                </td>
                <td class="py-1 px-2 align-middle label-field">
                    <input
                        type="text"
                        name="item_label[]"
                        maxlength="80"
                        class="w-full px-2 py-1 bg-gray-600 border border-gray-500 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100 text-sm"
                        placeholder="Gamer"
                    >
                </td>
                <td class="py-1 px-2 align-middle style-field">
                    <select
                        name="item_style[]"
                        class="w-full px-2 py-1 bg-gray-600 border border-gray-500 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100 text-sm"
                    >
                        <option value="secondary">Gray</option>
                        <option value="primary">Blue</option>
                        <option value="success">Green</option>
                        <option value="danger">Red</option>
                    </select>
                </td>
                <td class="py-1 px-2 align-middle">
                    <button
                        type="button"
                        class="remove-role-item text-red-400 hover:text-red-300 text-sm"
                        title="Remove"
                    >
                        Delete
                    </button>
                </td>
            `;

            // ロールオートコンプリートのイベント設定
            setupRoleAutocomplete(row);

            // プリフィルデータがある場合は値をセット
            if (prefill) {{
                const emojiInput = row.querySelector('input[name="item_emoji[]"]');
                const roleInput = row.querySelector('.role-input');
                const roleIdInput = row.querySelector('.role-id-input');
                const labelInput = row.querySelector('input[name="item_label[]"]');
                const styleSelect = row.querySelector('select[name="item_style[]"]');
                const posInput = row.querySelector('.position-input');

                if (emojiInput && prefill.emoji) emojiInput.value = prefill.emoji;
                if (roleIdInput && prefill.role_id) roleIdInput.value = prefill.role_id;
                if (roleInput && prefill.role_id) {{
                    // discordRoles からロール名を検索
                    let roleName = '';
                    for (const guildId in discordRoles) {{
                        const found = discordRoles[guildId].find(r => r.id === prefill.role_id);
                        if (found) {{
                            roleName = found.name;
                            break;
                        }}
                    }}
                    roleInput.value = roleName ? '@' + roleName : prefill.role_id;
                }}
                if (labelInput && prefill.label) labelInput.value = prefill.label;
                if (styleSelect && prefill.style) styleSelect.value = prefill.style;
                if (posInput && prefill.position != null) posInput.value = prefill.position;
            }}

            return row;
        }}

        // ロールオートコンプリートの設定
        function setupRoleAutocomplete(row) {{
            const roleInput = row.querySelector('.role-input');
            const roleDropdown = row.querySelector('.role-dropdown');
            const roleIdInput = row.querySelector('.role-id-input');

            if (!roleInput || !roleDropdown || !roleIdInput) return;

            const availableRoles = getRolesForCurrentGuild();

            // ドロップダウンを表示
            function showDropdown(filter = '') {{
                const filterLower = filter.toLowerCase();
                const filteredRoles = availableRoles.filter(r =>
                    r.name.toLowerCase().includes(filterLower)
                );

                if (filteredRoles.length === 0) {{
                    roleDropdown.innerHTML = '<div class="px-3 py-2 text-gray-400 text-sm">No matching roles</div>';
                }} else {{
                    roleDropdown.innerHTML = filteredRoles.map(r => {{
                        const colorStyle = r.color ? `color: ${{colorToHex(r.color)}}` : 'color: #99aab5';
                        return `<div class="role-option px-3 py-2 hover:bg-gray-600 cursor-pointer text-sm"
                                     data-id="${{r.id}}" data-name="${{escapeHtml(r.name)}}" style="${{colorStyle}}">
                                    @${{escapeHtml(r.name)}}
                                </div>`;
                    }}).join('');
                }}
                roleDropdown.classList.remove('hidden');
            }}

            // ドロップダウンを非表示
            function hideDropdown() {{
                roleDropdown.classList.add('hidden');
            }}

            // 入力時にフィルタリング
            roleInput.addEventListener('input', function() {{
                showDropdown(this.value);
                // 入力が変更されたら選択をクリア
                roleIdInput.value = '';
            }});

            // フォーカス時にドロップダウン表示
            roleInput.addEventListener('focus', function() {{
                showDropdown(this.value);
            }});

            // ドロップダウンからの選択
            roleDropdown.addEventListener('click', function(e) {{
                const option = e.target.closest('.role-option');
                if (option) {{
                    const roleId = option.dataset.id;
                    const roleName = option.dataset.name;
                    roleInput.value = '@' + roleName;
                    roleIdInput.value = roleId;
                    hideDropdown();
                }}
            }});

            // 外部クリックでドロップダウンを閉じる
            document.addEventListener('click', function(e) {{
                if (!row.contains(e.target)) {{
                    hideDropdown();
                }}
            }});

            // Escape キーでドロップダウンを閉じる
            roleInput.addEventListener('keydown', function(e) {{
                if (e.key === 'Escape') {{
                    hideDropdown();
                }}
            }});
        }}

        addRoleItemBtn.addEventListener('click', function() {{
            const row = createRoleItemRow(roleItemIndex++);
            roleItemsContainer.appendChild(row);
            updateSubmitButton();
            updateLabelFieldsVisibility();
            // Focus the emoji input of the new row
            row.querySelector('input[name="item_emoji[]"]').focus();
        }});

        roleItemsContainer.addEventListener('click', function(e) {{
            if (e.target.classList.contains('remove-role-item')) {{
                e.target.closest('.role-item-row').remove();
                updatePositions();
                updateSubmitButton();
            }}
        }});

        // --- Drag and Drop functionality ---
        let draggedItem = null;

        roleItemsContainer.addEventListener('dragstart', function(e) {{
            const row = e.target.closest('.role-item-row');
            if (!row) return;
            draggedItem = row;
            row.classList.add('opacity-50');
            e.dataTransfer.effectAllowed = 'move';
        }});

        roleItemsContainer.addEventListener('dragend', function(e) {{
            const row = e.target.closest('.role-item-row');
            if (row) {{
                row.classList.remove('opacity-50');
            }}
            draggedItem = null;
            // Remove all drag-over styles
            document.querySelectorAll('.role-item-row').forEach(r => {{
                r.classList.remove('border-t-2', 'border-blue-500');
            }});
        }});

        roleItemsContainer.addEventListener('dragover', function(e) {{
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            const row = e.target.closest('.role-item-row');
            if (!row || row === draggedItem) return;

            // Show drop indicator
            document.querySelectorAll('.role-item-row').forEach(r => {{
                r.classList.remove('border-t-2', 'border-blue-500');
            }});
            row.classList.add('border-t-2', 'border-blue-500');
        }});

        roleItemsContainer.addEventListener('drop', function(e) {{
            e.preventDefault();
            const row = e.target.closest('.role-item-row');
            if (!row || !draggedItem || row === draggedItem) return;

            // Insert dragged item before the target row
            roleItemsContainer.insertBefore(draggedItem, row);
            updatePositions();
        }});

        function updatePositions() {{
            const rows = roleItemsContainer.querySelectorAll('.role-item-row');
            rows.forEach((row, index) => {{
                const posInput = row.querySelector('.position-input');
                if (posInput) {{
                    posInput.value = index;
                }}
            }});
        }}

        // フォーム送信前に最低1つのロールアイテムがあることを確認し、position を更新
        document.getElementById('createPanelForm').addEventListener('submit', function(e) {{
            updatePositions();
            const itemCount = roleItemsContainer.querySelectorAll('.role-item-row').length;
            if (itemCount === 0) {{
                e.preventDefault();
                alert('Please add at least one role item before creating the panel.');
                return false;
            }}
        }});

        // --- Label フィールドの表示/非表示 (reaction の場合は非表示) ---
        function isButtonType() {{
            const panelTypeRadio = document.querySelector('input[name="panel_type"]:checked');
            return panelTypeRadio && panelTypeRadio.value === 'button';
        }}

        function updateLabelFieldsVisibility() {{
            const showLabel = isButtonType();
            // Hide both label and style fields for reaction panels
            const labelFields = document.querySelectorAll('.label-field');
            labelFields.forEach(field => {{
                field.style.display = showLabel ? '' : 'none';
            }});
            const styleFields = document.querySelectorAll('.style-field');
            styleFields.forEach(field => {{
                field.style.display = showLabel ? '' : 'none';
            }});
        }}

        // panel_type が変更されたときにラベルフィールドの表示を更新
        document.querySelectorAll('input[name="panel_type"]').forEach(radio => {{
            radio.addEventListener('change', updateLabelFieldsVisibility);
            radio.addEventListener('change', updateRemoveReactionVisibility);
        }});

        // リアクション式選択時のみ remove_reaction オプションを表示
        function updateRemoveReactionVisibility() {{
            const panelTypeRadio = document.querySelector('input[name="panel_type"]:checked');
            const removeReactionOption = document.getElementById('removeReactionOption');
            if (panelTypeRadio && panelTypeRadio.value === 'reaction') {{
                removeReactionOption.classList.remove('hidden');
            }} else {{
                removeReactionOption.classList.add('hidden');
            }}
        }}

        // バリデーションエラー時に既存アイテムを復元
        if (existingItems.length > 0) {{
            existingItems.forEach(function(item) {{
                const row = createRoleItemRow(roleItemIndex++, item);
                roleItemsContainer.appendChild(row);
            }});
        }}

        // 初期状態を設定
        updateSubmitButton();
        updateRolesInfo();
        updateLabelFieldsVisibility();
        updateRemoveReactionVisibility();
    }})();
    </script>
    """
    return _base("Create Role Panel", content)


def role_panel_detail_page(
    panel: "RolePanel",
    items: list["RolePanelItem"],
    error: str | None = None,
    success: str | None = None,
    discord_roles: list[tuple[str, str, int]] | None = None,
    guild_name: str | None = None,
    channel_name: str | None = None,
    csrf_token: str = "",
) -> str:
    """Role panel detail page template with item management.

    Args:
        discord_roles: [(role_id, role_name, color), ...] のリスト
        guild_name: ギルド名 (キャッシュから取得)
        channel_name: チャンネル名 (キャッシュから取得)
    """
    if discord_roles is None:
        discord_roles = []

    message_html = ""
    if error:
        message_html = f"""
        <div class="bg-red-500/20 border border-red-500 text-red-300 px-4 py-3 rounded mb-4">
            {escape(error)}
        </div>
        """
    elif success:
        message_html = f"""
        <div class="bg-green-500/20 border border-green-500 text-green-300 px-4 py-3 rounded mb-4">
            {escape(success)}
        </div>
        """

    panel_type_badge = (
        '<span class="bg-blue-600 px-2 py-1 rounded text-xs">Button</span>'
        if panel.panel_type == "button"
        else '<span class="bg-purple-600 px-2 py-1 rounded text-xs">Reaction</span>'
    )

    format_badge = (
        '<span class="text-blue-400">Embed</span>'
        if panel.use_embed
        else '<span class="text-gray-300">Text</span>'
    )

    # Auto-remove reactions badge (reaction type only)
    remove_reaction_badge = ""
    if panel.panel_type == "reaction":
        if panel.remove_reaction:
            remove_reaction_badge = '<span class="text-yellow-400">Enabled</span>'
        else:
            remove_reaction_badge = '<span class="text-gray-400">Disabled</span>'

    # ロールID -> ロール情報のマップを作成
    role_info_map: dict[str, tuple[str, int]] = {
        r[0]: (r[1], r[2]) for r in discord_roles
    }

    # ボタン式の場合のみラベルを表示
    is_button_type = panel.panel_type == "button"

    # Build items table
    style_display_map = {
        "primary": '<span class="text-blue-400">Blue</span>',
        "secondary": '<span class="text-gray-400">Gray</span>',
        "success": '<span class="text-green-400">Green</span>',
        "danger": '<span class="text-red-400">Red</span>',
    }

    items_row_parts: list[str] = []
    for item in items:
        label_display = escape(item.label) if item.label else "(no label)"
        style_display = style_display_map.get(
            item.style, '<span class="text-gray-400">Gray</span>'
        )
        # ロール名を表示（存在する場合）
        role_info = role_info_map.get(item.role_id)
        if role_info:
            role_name, role_color = role_info
            color_hex = f"#{role_color:06x}" if role_color else "#99aab5"
            role_display = (
                f'<span style="color: {color_hex}">@{escape(role_name)}</span>'
            )
            role_id_display = f'{role_display}<br><span class="font-mono text-xs text-gray-500">{escape(item.role_id)}</span>'
        else:
            role_id_display = f'<span class="font-mono">{escape(item.role_id)}</span>'

        label_cell = (
            f'<td class="py-3 px-4 align-middle">{label_display}</td>'
            if is_button_type
            else ""
        )
        style_cell = (
            f'<td class="py-3 px-4 align-middle">{style_display}</td>'
            if is_button_type
            else ""
        )
        items_row_parts.append(f"""
        <tr class="border-b border-gray-700" data-item-id="{item.id}" draggable="true">
            <td class="py-3 px-2 align-middle cursor-grab active:cursor-grabbing text-gray-400 hover:text-gray-200">
                <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M7 2a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm6 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM7 8a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm6 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm-6 6a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm6 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4z"/>
                </svg>
            </td>
            <td class="py-3 px-4 align-middle text-xl">{escape(item.emoji)}</td>
            <td class="py-3 px-4 align-middle">{role_id_display}</td>
            {label_cell}
            {style_cell}
            <td class="py-3 px-4 align-middle">
                <a href="#" onclick="postAction('/rolepanels/{panel.id}/items/{item.id}/delete', '{csrf_token}', 'Delete this role item?'); return false;"
                   class="text-red-400 hover:text-red-300 text-sm">Delete</a>
            </td>
        </tr>
        """)
    items_rows = "".join(items_row_parts)

    col_count = 6 if is_button_type else 4
    if not items:
        items_rows = f"""
        <tr>
            <td colspan="{col_count}" class="py-8 text-center text-gray-500">
                No roles configured. Add roles below.
            </td>
        </tr>
        """

    content = f"""
    <div class="p-6">
        {
        _nav(
            f"Panel: {escape(panel.title)}",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Role Panels", "/rolepanels"),
                (escape(panel.title), None),
            ],
        )
    }

        {message_html}

        <!-- Panel Info -->
        <div class="bg-gray-800 p-6 rounded-lg mb-6">
            <h2 class="text-lg font-semibold mb-4">Panel Information</h2>
            <div class="grid grid-cols-2 gap-4 text-sm">
                <div>
                    <span class="text-gray-400">Type:</span>
                    {panel_type_badge}
                </div>
                <div>
                    <span class="text-gray-400">Format:</span>
                    {format_badge}
                </div>
                <div>
                    <span class="text-gray-400">Server:</span>
                    {
        f'<span class="font-medium">{escape(guild_name)}</span><br><span class="font-mono text-xs text-gray-500">{escape(panel.guild_id)}</span>'
        if guild_name
        else f'<span class="font-mono text-yellow-400">{escape(panel.guild_id)}</span>'
    }
                </div>
                <div>
                    <span class="text-gray-400">Channel:</span>
                    {
        f'<span class="font-medium">#{escape(channel_name)}</span><br><span class="font-mono text-xs text-gray-500">{escape(panel.channel_id)}</span>'
        if channel_name
        else f'<span class="font-mono text-yellow-400">{escape(panel.channel_id)}</span>'
    }
                </div>
                <div>
                    <span class="text-gray-400">Message ID:</span>
                    <span class="font-mono">{
        escape(panel.message_id or "(not posted)")
    }</span>
                </div>
                {
        f'''<div class="flex items-center gap-2">
                    <span class="text-gray-400">Auto-remove:</span>
                    {remove_reaction_badge}
                    <form method="POST" action="/rolepanels/{panel.id}/toggle-remove-reaction"
                          class="inline">
                        {_csrf_field(csrf_token)}
                        <button type="submit"
                                class="text-xs text-blue-400 hover:text-blue-300 underline">
                            Toggle
                        </button>
                    </form>
                </div>'''
        if panel.panel_type == "reaction"
        else ""
    }
            </div>

            <!-- Edit Title & Description Form -->
            <form method="POST" action="/rolepanels/{
        panel.id
    }/edit" class="mt-6 pt-4 border-t border-gray-700">
                {_csrf_field(csrf_token)}
                <div class="grid grid-cols-1 gap-4">
                    <div>
                        <label for="title" class="block text-sm text-gray-400 mb-1">Title</label>
                        <input type="text" id="title" name="title"
                               value="{escape(panel.title)}"
                               maxlength="100"
                               required
                               class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2
                                      focus:outline-none focus:border-blue-500">
                    </div>
                    <div>
                        <label for="description" class="block text-sm text-gray-400 mb-1">Description</label>
                        <textarea id="description" name="description"
                                  rows="3"
                                  maxlength="2000"
                                  class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2
                                         focus:outline-none focus:border-blue-500"
                                  placeholder="Optional description...">{
        escape(panel.description or "")
    }</textarea>
                    </div>
                    {
        f'''<div id="editColorOption">
                        <label for="edit_color" class="block text-sm text-gray-400 mb-1">Embed Color</label>
                        <div class="flex items-center gap-3">
                            <input type="color" id="edit_color" name="color"
                                   value="{f"#{panel.color:06x}" if panel.color else "#85E7AD"}"
                                   class="w-10 h-10 rounded cursor-pointer bg-transparent border-0">
                            <input type="text" id="edit_color_text"
                                   value="{f"#{panel.color:06x}".upper() if panel.color else "#85E7AD"}"
                                   maxlength="7" pattern="#[0-9A-Fa-f]{{6}}"
                                   class="w-28 px-3 py-2 bg-gray-700 border border-gray-600 rounded
                                          focus:outline-none focus:border-blue-500
                                          text-gray-100 font-mono text-sm">
                        </div>
                    </div>'''
        if panel.use_embed
        else ""
    }
                    <div>
                        <button type="submit"
                                class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded font-medium
                                       transition-colors">
                            Save Changes
                        </button>
                    </div>
                </div>
            </form>

            <div class="mt-6 pt-4 border-t border-gray-700">
                {
        f'''<div class="flex items-center mb-4">
                    <span class="text-green-400 font-medium">✓ Posted to Discord</span>
                    <span class="ml-4 text-gray-400 text-sm font-mono">
                        Message ID: {escape(panel.message_id)}
                    </span>
                </div>'''
        if panel.message_id
        else ""
    }
                <div class="flex gap-3 items-center flex-wrap">
                    <form method="POST" action="/rolepanels/{panel.id}/post"
                          onsubmit="return confirm('{
        "Update this panel in Discord?"
        if panel.message_id
        else "Post this panel to Discord?"
    }');">
                        {_csrf_field(csrf_token)}
                        <button type="submit"
                                class="bg-green-600 hover:bg-green-700 px-6 py-2 rounded font-semibold
                                       transition-colors">
                            {
        "Update in Discord" if panel.message_id else "Post to Discord"
    }
                        </button>
                    </form>
                    <form method="POST" action="/rolepanels/{panel.id}/copy">
                        {_csrf_field(csrf_token)}
                        <button type="submit"
                                class="bg-gray-600 hover:bg-gray-500 px-4 py-2 rounded font-medium
                                       transition-colors">
                            Duplicate Panel
                        </button>
                    </form>
                    <span class="text-gray-400 text-sm">
                        {
        "Updates the existing message and reactions."
        if panel.message_id
        else "The panel will be posted to the channel above."
    }
                    </span>
                </div>
            </div>
        </div>

        <!-- Role Items -->
        <div class="bg-gray-800 p-6 rounded-lg mb-6">
            <h2 class="text-lg font-semibold mb-4">Role Items ({len(items)})</h2>
            <div class="overflow-x-auto">
                <table class="w-full">
                    <thead class="bg-gray-700">
                        <tr>
                            <th class="py-3 px-2 w-8"></th>
                            <th class="py-3 px-4 text-left">Emoji</th>
                            <th class="py-3 px-4 text-left">Role</th>
                            {
        ""
        if not is_button_type
        else '<th class="py-3 px-4 text-left">Label</th><th class="py-3 px-4 text-left">Style</th>'
    }
                            <th class="py-3 px-4 text-left">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {items_rows}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Add Role Item Form -->
        <div class="bg-gray-800 p-6 rounded-lg">
            <h2 class="text-lg font-semibold mb-4">Add Role Item</h2>
            <form method="POST" action="/rolepanels/{panel.id}/items/add">
                {_csrf_field(csrf_token)}
                <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
                    <div>
                        <label for="emoji" class="block text-sm font-medium mb-2">
                            Emoji <span class="text-red-400">*</span>
                        </label>
                        <input
                            type="text"
                            id="emoji"
                            name="emoji"
                            required
                            maxlength="64"
                            class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                                   focus:outline-none focus:ring-2 focus:ring-blue-500
                                   text-gray-100"
                            placeholder="🎮 or custom emoji"
                        >
                    </div>
                    <div>
                        <label for="role_select" class="block text-sm font-medium mb-2">
                            Role <span class="text-red-400">*</span>
                        </label>
                        {
        ""
        if not discord_roles
        else '''
                        <div class="role-autocomplete relative">
                            <input
                                type="text"
                                id="role_input"
                                class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                                       focus:outline-none focus:ring-2 focus:ring-blue-500
                                       text-gray-100"
                                placeholder="Type to search roles..."
                                autocomplete="off"
                            >
                            <div id="role_dropdown"
                                 class="absolute z-50 w-full mt-1 bg-gray-700 border border-gray-600
                                        rounded shadow-lg max-h-48 overflow-y-auto hidden">
                            </div>
                        </div>
                        <input type="hidden" id="role_id" name="role_id">
                        '''
    }
                    </div>
                    {
        '''<div>
                        <label for="label" class="block text-sm font-medium mb-2">
                            Label (for buttons)
                        </label>
                        <input
                            type="text"
                            id="label"
                            name="label"
                            maxlength="80"
                            class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                                   focus:outline-none focus:ring-2 focus:ring-blue-500
                                   text-gray-100"
                            placeholder="Gamer"
                        >
                    </div>
                    <div>
                        <label for="style" class="block text-sm font-medium mb-2">
                            Button Style
                        </label>
                        <select
                            id="style"
                            name="style"
                            class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                                   focus:outline-none focus:ring-2 focus:ring-blue-500
                                   text-gray-100"
                        >
                            <option value="secondary">Gray (Secondary)</option>
                            <option value="primary">Blue (Primary)</option>
                            <option value="success">Green (Success)</option>
                            <option value="danger">Red (Danger)</option>
                        </select>
                    </div>'''
        if is_button_type
        else ""
    }
                </div>
                <button
                    type="submit"
                    class="bg-green-600 hover:bg-green-700 text-white font-medium
                           py-2 px-4 rounded transition-colors disabled:opacity-50
                           disabled:cursor-not-allowed disabled:hover:bg-green-600"
                    {"disabled" if not discord_roles else ""}
                >
                    Add Role Item
                </button>
            </form>
            {
        ""
        if discord_roles
        else '<p class="mt-2 text-red-400 text-sm">No roles found for this guild. Please sync roles by starting the Bot first.</p>'
    }
        </div>
    </div>
    {
        ""
        if not discord_roles
        else f'''
    <script>
    (function() {{
        const roleInput = document.getElementById("role_input");
        const roleDropdown = document.getElementById("role_dropdown");
        const roleIdInput = document.getElementById("role_id");

        if (!roleInput || !roleDropdown || !roleIdInput) return;

        const roles = {_roles_to_js_array(discord_roles)};

        function colorToHex(color) {{
            if (!color) return '#99aab5';
            return '#' + color.toString(16).padStart(6, '0');
        }}

        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}

        function showDropdown(filter) {{
            const filterLower = (filter || '').toLowerCase();
            const filtered = roles.filter(r => r.name.toLowerCase().includes(filterLower));

            if (filtered.length === 0) {{
                roleDropdown.innerHTML = '<div class="px-4 py-2 text-gray-400 text-sm">No matching roles</div>';
            }} else {{
                roleDropdown.innerHTML = filtered.map(r => {{
                    const colorStyle = r.color ? 'color: ' + colorToHex(r.color) : 'color: #99aab5';
                    return '<div class="role-option px-4 py-2 hover:bg-gray-600 cursor-pointer" ' +
                           'data-id="' + r.id + '" data-name="' + escapeHtml(r.name) + '" style="' + colorStyle + '">' +
                           '@' + escapeHtml(r.name) + '</div>';
                }}).join('');
            }}
            roleDropdown.classList.remove('hidden');
        }}

        function hideDropdown() {{
            roleDropdown.classList.add('hidden');
        }}

        roleInput.addEventListener('input', function() {{
            showDropdown(this.value);
            roleIdInput.value = '';
        }});

        roleInput.addEventListener('focus', function() {{
            showDropdown(this.value);
        }});

        roleDropdown.addEventListener('click', function(e) {{
            const option = e.target.closest('.role-option');
            if (option) {{
                roleInput.value = '@' + option.dataset.name;
                roleIdInput.value = option.dataset.id;
                hideDropdown();
            }}
        }});

        document.addEventListener('click', function(e) {{
            if (!roleInput.contains(e.target) && !roleDropdown.contains(e.target)) {{
                hideDropdown();
            }}
        }});

        roleInput.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') {{
                hideDropdown();
            }}
        }});
    }})();
    </script>
    '''
    }
    <script>
    (function() {{
        const editColorPicker = document.getElementById('edit_color');
        const editColorText = document.getElementById('edit_color_text');
        if (editColorPicker && editColorText) {{
            editColorPicker.addEventListener('input', function() {{
                editColorText.value = this.value.toUpperCase();
            }});
            editColorText.addEventListener('input', function() {{
                if (/^#[0-9A-Fa-f]{{6}}$/.test(this.value)) {{
                    editColorPicker.value = this.value;
                }}
            }});
        }}
    }})();
    </script>
    <script>
    (function() {{
        const tbody = document.querySelector('table tbody');
        if (!tbody) return;
        const panelId = {panel.id};
        let dragRow = null;

        tbody.addEventListener('dragstart', function(e) {{
            dragRow = e.target.closest('tr[data-item-id]');
            if (!dragRow) return;
            dragRow.classList.add('opacity-50');
            e.dataTransfer.effectAllowed = 'move';
        }});

        tbody.addEventListener('dragend', function() {{
            if (dragRow) dragRow.classList.remove('opacity-50');
            dragRow = null;
            tbody.querySelectorAll('tr').forEach(r => r.classList.remove('border-t-2', 'border-blue-400'));
        }});

        tbody.addEventListener('dragover', function(e) {{
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            const target = e.target.closest('tr[data-item-id]');
            tbody.querySelectorAll('tr').forEach(r => r.classList.remove('border-t-2', 'border-blue-400'));
            if (target && target !== dragRow) {{
                target.classList.add('border-t-2', 'border-blue-400');
            }}
        }});

        tbody.addEventListener('drop', function(e) {{
            e.preventDefault();
            const target = e.target.closest('tr[data-item-id]');
            if (!target || !dragRow || target === dragRow) return;
            tbody.insertBefore(dragRow, target);
            // Collect new order and send to server
            const itemIds = Array.from(tbody.querySelectorAll('tr[data-item-id]'))
                .map(r => parseInt(r.dataset.itemId));
            const csrfInput = document.querySelector('input[name="csrf_token"]');
            fetch('/rolepanels/' + panelId + '/items/reorder', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                    item_ids: itemIds,
                    csrf_token: csrfInput ? csrfInput.value : ''
                }})
            }});
        }});
    }})();
    </script>
    """
    return _base(f"Panel: {panel.title}", content)


def autoban_list_page(
    rules: list["AutoBanRule"],
    csrf_token: str = "",
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
) -> str:
    """Autoban rules list page template."""
    if guilds_map is None:
        guilds_map = {}
    if channels_map is None:
        channels_map = {}

    row_parts: list[str] = []
    for rule in rules:
        guild_name = guilds_map.get(rule.guild_id)
        if guild_name:
            guild_display = (
                f'<span class="font-medium">{escape(guild_name)}</span>'
                f'<br><span class="font-mono text-xs text-gray-500">'
                f"{escape(rule.guild_id)}</span>"
            )
        else:
            guild_display = (
                f'<span class="font-mono text-yellow-400">'
                f"{escape(rule.guild_id)}</span>"
            )

        # Details column based on rule type
        if rule.rule_type == "username_match":
            wildcard = " (wildcard)" if rule.use_wildcard else " (exact)"
            details = escape(rule.pattern or "") + wildcard
        elif rule.rule_type == "account_age":
            details = f"{rule.threshold_hours}h" if rule.threshold_hours else "-"
        elif rule.rule_type in ("role_acquired", "vc_join", "message_post"):
            details = (
                f"{rule.threshold_seconds}s after join"
                if rule.threshold_seconds
                else "-"
            )
        elif rule.rule_type in ("vc_without_intro", "msg_without_intro"):
            if rule.required_channel_id:
                ch_name = None
                for cid, cname in channels_map.get(rule.guild_id, []):
                    if cid == rule.required_channel_id:
                        ch_name = cname
                        break
                if ch_name:
                    details = f"#{escape(ch_name)}"
                else:
                    details = f"Ch: {escape(rule.required_channel_id)}"
            else:
                details = "-"
        else:
            details = "-"

        status = "Enabled" if rule.is_enabled else "Disabled"
        status_class = "text-green-400" if rule.is_enabled else "text-gray-500"
        created = format_datetime(rule.created_at)

        row_parts.append(f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 align-middle">{guild_display}</td>
            <td class="py-3 px-4 align-middle">{escape(rule.rule_type)}</td>
            <td class="py-3 px-4 align-middle">{escape(rule.action)}</td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">{details}</td>
            <td class="py-3 px-4 align-middle">
                <span class="{status_class}">{status}</span>
            </td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">{created}</td>
            <td class="py-3 px-4 align-middle space-x-2">
                <a href="/autoban/{rule.id}/edit"
                   class="text-blue-400 hover:text-blue-300 text-sm">Edit</a>
                <a href="#" onclick="postAction('/autoban/{rule.id}/toggle', '{csrf_token}'); return false;"
                   class="text-blue-400 hover:text-blue-300 text-sm">Toggle</a>
                <a href="#" onclick="postAction('/autoban/{rule.id}/delete', '{csrf_token}', 'Delete this autoban rule?'); return false;"
                   class="text-red-400 hover:text-red-300 text-sm">Delete</a>
            </td>
        </tr>
        """)
    rows = "".join(row_parts)

    if not rules:
        rows = """
        <tr>
            <td colspan="7" class="py-8 text-center text-gray-500">
                No autoban rules configured
            </td>
        </tr>
        """

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Autoban Rules",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Autoban Rules", None),
            ],
        )
    }
        <div class="flex gap-3 mb-4">
            <a href="/autoban/new"
               class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm transition-colors">
                + Create Rule
            </a>
            <a href="/autoban/logs"
               class="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded text-sm transition-colors">
                View Logs
            </a>
            <a href="/autoban/settings"
               class="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded text-sm transition-colors">
                Settings
            </a>
        </div>
        <div class="bg-gray-800 rounded-lg overflow-hidden overflow-x-auto">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="py-3 px-4 text-left">Server</th>
                        <th class="py-3 px-4 text-left">Type</th>
                        <th class="py-3 px-4 text-left">Action</th>
                        <th class="py-3 px-4 text-left">Details</th>
                        <th class="py-3 px-4 text-left">Status</th>
                        <th class="py-3 px-4 text-left">Created</th>
                        <th class="py-3 px-4 text-left">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
    </div>
    """
    return _base("Autoban Rules", content)


def autoban_create_page(
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
    csrf_token: str = "",
) -> str:
    """Autoban rule create page template."""
    import json as json_mod

    if guilds_map is None:
        guilds_map = {}
    if channels_map is None:
        channels_map = {}

    guild_options = ""
    for gid, gname in sorted(guilds_map.items(), key=lambda x: x[1]):
        guild_options += (
            f'<option value="{escape(gid)}">{escape(gname)} ({escape(gid)})</option>'
        )

    channels_data: dict[str, list[dict[str, str]]] = {}
    for gid, ch_list in channels_map.items():
        channels_data[gid] = [{"id": cid, "name": cname} for cid, cname in ch_list]
    channels_json = json_mod.dumps(channels_data)

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Create Autoban Rule",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Autoban Rules", "/autoban"),
                ("Create", None),
            ],
        )
    }
        <div class="max-w-2xl">
            <form method="POST" action="/autoban/new" class="space-y-6">
                {_csrf_field(csrf_token)}

                <div>
                    <label class="block text-sm font-medium mb-1">Server</label>
                    <select name="guild_id" required id="guildSelect"
                            onchange="updateRequiredChannel()"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="">Select server...</option>
                        {guild_options}
                    </select>
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">Rule Type</label>
                    <div class="space-y-2" id="ruleTypeGroup">
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="radio" name="rule_type" value="username_match"
                                   checked onchange="updateRuleFields()">
                            <span>Username Match</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="radio" name="rule_type" value="account_age"
                                   onchange="updateRuleFields()">
                            <span>Account Age</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="radio" name="rule_type" value="no_avatar"
                                   onchange="updateRuleFields()">
                            <span>No Avatar</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="radio" name="rule_type" value="role_acquired"
                                   onchange="updateRuleFields()">
                            <span>Role Acquired (after join)</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="radio" name="rule_type" value="vc_join"
                                   onchange="updateRuleFields()">
                            <span>VC Join (after join)</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="radio" name="rule_type" value="message_post"
                                   onchange="updateRuleFields()">
                            <span>Message Post (after join)</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="radio" name="rule_type" value="vc_without_intro"
                                   onchange="updateRuleFields()">
                            <span>VC Join without Intro Post</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="radio" name="rule_type" value="msg_without_intro"
                                   onchange="updateRuleFields()">
                            <span>Message without Intro Post</span>
                        </label>
                    </div>
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">Action</label>
                    <select name="action"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="ban">Ban</option>
                        <option value="kick">Kick</option>
                    </select>
                </div>

                <div id="usernameFields">
                    <div class="space-y-3">
                        <div>
                            <label class="block text-sm font-medium mb-1">Pattern</label>
                            <input type="text" name="pattern"
                                   placeholder="e.g. spammer"
                                   class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        </div>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" name="use_wildcard" value="on"
                                   class="rounded bg-gray-700 border-gray-600">
                            <span class="text-sm">Use Wildcard (match pattern anywhere in username)</span>
                        </label>
                    </div>
                </div>

                <div id="accountAgeFields" class="hidden">
                    <label class="block text-sm font-medium mb-1">
                        Threshold (hours, max 336 = 14 days)
                    </label>
                    <input type="number" name="threshold_hours"
                           min="1" max="336" placeholder="e.g. 24"
                           class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                </div>

                <div id="thresholdSecondsFields" class="hidden">
                    <label class="block text-sm font-medium mb-1">
                        Threshold (seconds after join, max 3600 = 1 hour)
                    </label>
                    <input type="number" name="threshold_seconds"
                           min="1" max="3600" placeholder="e.g. 30"
                           class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                </div>

                <div id="requiredChannelFields" class="hidden">
                    <label class="block text-sm font-medium mb-1">
                        Required Channel (must post here first)
                    </label>
                    <select name="required_channel_id" id="requiredChannelSelect"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="">Select channel...</option>
                    </select>
                </div>

                <button type="submit"
                        class="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded transition-colors">
                    Create Rule
                </button>
            </form>
        </div>
    </div>

    <script>
    const channelsData = {channels_json};
    function updateRuleFields() {{
        const ruleType = document.querySelector('input[name="rule_type"]:checked').value;
        const usernameFields = document.getElementById('usernameFields');
        const accountAgeFields = document.getElementById('accountAgeFields');
        const thresholdSecondsFields = document.getElementById('thresholdSecondsFields');
        const requiredChannelFields = document.getElementById('requiredChannelFields');
        const introTypes = ['vc_without_intro', 'msg_without_intro'];

        usernameFields.classList.toggle('hidden', ruleType !== 'username_match');
        accountAgeFields.classList.toggle('hidden', ruleType !== 'account_age');
        thresholdSecondsFields.classList.toggle('hidden',
            ruleType !== 'role_acquired' && ruleType !== 'vc_join' && ruleType !== 'message_post');
        requiredChannelFields.classList.toggle('hidden', !introTypes.includes(ruleType));
    }}
    function updateRequiredChannel() {{
        const guildId = document.getElementById('guildSelect').value;
        const sel = document.getElementById('requiredChannelSelect');
        sel.innerHTML = '<option value="">Select channel...</option>';
        if (channelsData[guildId]) {{
            channelsData[guildId].forEach(ch => {{
                const opt = document.createElement('option');
                opt.value = ch.id;
                opt.textContent = '#' + ch.name;
                sel.appendChild(opt);
            }});
        }}
    }}
    </script>
    """
    return _base("Create Autoban Rule", content)


def autoban_edit_page(
    rule: "AutoBanRule",
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
    csrf_token: str = "",
) -> str:
    """Autoban rule edit page template."""
    if guilds_map is None:
        guilds_map = {}
    if channels_map is None:
        channels_map = {}

    guild_name = guilds_map.get(rule.guild_id, rule.guild_id)
    guild_display = f"{escape(guild_name)} ({escape(rule.guild_id)})"

    ban_selected = " selected" if rule.action == "ban" else ""
    kick_selected = " selected" if rule.action == "kick" else ""

    # Rule-type-specific fields
    type_fields = ""
    if rule.rule_type == "username_match":
        checked = " checked" if rule.use_wildcard else ""
        type_fields = f"""
                <div>
                    <label class="block text-sm font-medium mb-1">Pattern</label>
                    <input type="text" name="pattern"
                           value="{escape(rule.pattern or "")}"
                           class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                </div>
                <label class="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" name="use_wildcard" value="on"{checked}
                           class="rounded bg-gray-700 border-gray-600">
                    <span class="text-sm">Use Wildcard (match pattern anywhere in username)</span>
                </label>
        """
    elif rule.rule_type == "account_age":
        val = rule.threshold_hours or ""
        type_fields = f"""
                <div>
                    <label class="block text-sm font-medium mb-1">
                        Threshold (hours, max 336 = 14 days)
                    </label>
                    <input type="number" name="threshold_hours"
                           min="1" max="336" value="{val}"
                           class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                </div>
        """
    elif rule.rule_type in ("role_acquired", "vc_join", "message_post"):
        val = rule.threshold_seconds or ""
        type_fields = f"""
                <div>
                    <label class="block text-sm font-medium mb-1">
                        Threshold (seconds after join, max 3600 = 1 hour)
                    </label>
                    <input type="number" name="threshold_seconds"
                           min="1" max="3600" value="{val}"
                           class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                </div>
        """
    elif rule.rule_type in ("vc_without_intro", "msg_without_intro"):
        guild_channels = channels_map.get(rule.guild_id, [])
        ch_options = ""
        for cid, cname in guild_channels:
            selected = " selected" if cid == rule.required_channel_id else ""
            ch_options += (
                f'<option value="{escape(cid)}"{selected}>#{escape(cname)}</option>'
            )
        type_fields = f"""
                <div>
                    <label class="block text-sm font-medium mb-1">
                        Required Channel (must post here first)
                    </label>
                    <select name="required_channel_id"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="">Select channel...</option>
                        {ch_options}
                    </select>
                </div>
        """

    # Human-readable rule type label
    type_labels = {
        "username_match": "Username Match",
        "account_age": "Account Age",
        "no_avatar": "No Avatar",
        "role_acquired": "Role Acquired (after join)",
        "vc_join": "VC Join (after join)",
        "message_post": "Message Post (after join)",
        "vc_without_intro": "VC Join without Intro Post",
        "msg_without_intro": "Message without Intro Post",
    }
    rule_type_label = type_labels.get(rule.rule_type, rule.rule_type)

    content = f"""
    <div class="p-6">
        {
        _nav(
            f"Edit Autoban Rule #{rule.id}",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Autoban Rules", "/autoban"),
                (f"Edit #{rule.id}", None),
            ],
        )
    }
        <div class="max-w-2xl">
            <form method="POST" action="/autoban/{rule.id}/edit" class="space-y-6">
                {_csrf_field(csrf_token)}

                <div>
                    <label class="block text-sm font-medium mb-1">Server</label>
                    <div class="bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-400">
                        {guild_display}
                    </div>
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">Rule Type</label>
                    <div class="bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-400">
                        {escape(rule_type_label)}
                    </div>
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">Action</label>
                    <select name="action"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="ban"{ban_selected}>Ban</option>
                        <option value="kick"{kick_selected}>Kick</option>
                    </select>
                </div>

                {type_fields}

                <div class="flex gap-3">
                    <button type="submit"
                            class="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded transition-colors">
                        Save Changes
                    </button>
                    <a href="/autoban"
                       class="bg-gray-600 hover:bg-gray-700 px-6 py-2 rounded transition-colors">
                        Cancel
                    </a>
                </div>
            </form>
        </div>
    </div>
    """
    return _base(f"Edit Autoban Rule #{rule.id}", content)


def autoban_logs_page(
    logs: list["AutoBanLog"],
    guilds_map: dict[str, str] | None = None,
) -> str:
    """Autoban logs page template."""
    if guilds_map is None:
        guilds_map = {}

    row_parts: list[str] = []
    for log in logs:
        guild_name = guilds_map.get(log.guild_id)
        if guild_name:
            guild_display = (
                f'<span class="font-medium">{escape(guild_name)}</span>'
                f'<br><span class="font-mono text-xs text-gray-500">'
                f"{escape(log.guild_id)}</span>"
            )
        else:
            guild_display = (
                f'<span class="font-mono text-yellow-400">{escape(log.guild_id)}</span>'
            )

        action_class = (
            "text-red-400" if log.action_taken == "banned" else "text-yellow-400"
        )
        created = format_datetime(log.created_at)

        row_parts.append(f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 align-middle">{guild_display}</td>
            <td class="py-3 px-4 align-middle font-mono text-sm">{escape(log.user_id)}</td>
            <td class="py-3 px-4 align-middle">{escape(log.username)}</td>
            <td class="py-3 px-4 align-middle">
                <span class="{action_class}">{escape(log.action_taken)}</span>
            </td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">{escape(log.reason)}</td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">#{log.rule_id}</td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">{created}</td>
        </tr>
        """)
    rows = "".join(row_parts)

    if not logs:
        rows = """
        <tr>
            <td colspan="7" class="py-8 text-center text-gray-500">
                No autoban logs
            </td>
        </tr>
        """

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Autoban Logs",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Autoban Rules", "/autoban"),
                ("Logs", None),
            ],
        )
    }
        <div class="bg-gray-800 rounded-lg overflow-hidden overflow-x-auto">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="py-3 px-4 text-left">Server</th>
                        <th class="py-3 px-4 text-left">User ID</th>
                        <th class="py-3 px-4 text-left">Username</th>
                        <th class="py-3 px-4 text-left">Action</th>
                        <th class="py-3 px-4 text-left">Reason</th>
                        <th class="py-3 px-4 text-left">Rule</th>
                        <th class="py-3 px-4 text-left">Date</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
    </div>
    """
    return _base("Autoban Logs", content)


def ban_logs_page(
    logs: list["BanLog"],
    guilds_map: dict[str, str] | None = None,
) -> str:
    """Ban logs page template."""
    if guilds_map is None:
        guilds_map = {}

    row_parts: list[str] = []
    for log in logs:
        guild_name = guilds_map.get(log.guild_id)
        if guild_name:
            guild_display = (
                f'<span class="font-medium">{escape(guild_name)}</span>'
                f'<br><span class="font-mono text-xs text-gray-500">'
                f"{escape(log.guild_id)}</span>"
            )
        else:
            guild_display = (
                f'<span class="font-mono text-yellow-400">{escape(log.guild_id)}</span>'
            )

        # Source label
        if log.is_autoban:
            source_html = '<span class="bg-red-600 text-white text-xs px-2 py-0.5 rounded">AutoBan</span>'
        else:
            source_html = '<span class="bg-gray-600 text-gray-300 text-xs px-2 py-0.5 rounded">Manual</span>'

        # Reason display: strip [Autoban] prefix if present
        reason_display = log.reason or "-"
        if reason_display.startswith("[Autoban] "):
            reason_display = reason_display[len("[Autoban] ") :]

        created = format_datetime(log.created_at)

        row_parts.append(f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 align-middle">{guild_display}</td>
            <td class="py-3 px-4 align-middle font-mono text-sm">{escape(log.user_id)}</td>
            <td class="py-3 px-4 align-middle">{escape(log.username)}</td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">{escape(reason_display)}</td>
            <td class="py-3 px-4 align-middle">{source_html}</td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">{created}</td>
        </tr>
        """)
    rows = "".join(row_parts)

    if not logs:
        rows = """
        <tr>
            <td colspan="6" class="py-8 text-center text-gray-500">
                No ban logs
            </td>
        </tr>
        """

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Ban Logs",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Ban Logs", None),
            ],
        )
    }
        <div class="bg-gray-800 rounded-lg overflow-hidden overflow-x-auto">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="py-3 px-4 text-left">Server</th>
                        <th class="py-3 px-4 text-left">User ID</th>
                        <th class="py-3 px-4 text-left">Username</th>
                        <th class="py-3 px-4 text-left">Reason</th>
                        <th class="py-3 px-4 text-left">Source</th>
                        <th class="py-3 px-4 text-left">Date</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
    </div>
    """
    return _base("Ban Logs", content)


def autoban_settings_page(
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
    configs_map: dict[str, str | None] | None = None,
    csrf_token: str = "",
) -> str:
    """Autoban settings page template."""
    import json as json_mod

    if guilds_map is None:
        guilds_map = {}
    if channels_map is None:
        channels_map = {}
    if configs_map is None:
        configs_map = {}

    guild_options = ""
    for gid, gname in sorted(guilds_map.items(), key=lambda x: x[1]):
        guild_options += (
            f'<option value="{escape(gid)}">{escape(gname)} ({escape(gid)})</option>'
        )

    channels_data: dict[str, list[dict[str, str]]] = {}
    for gid, ch_list in channels_map.items():
        channels_data[gid] = [{"id": cid, "name": cname} for cid, cname in ch_list]
    channels_json = json_mod.dumps(channels_data)

    configs_json = json_mod.dumps(
        {gid: (ch_id or "") for gid, ch_id in configs_map.items()}
    )

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Autoban Settings",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Autoban Rules", "/autoban"),
                ("Settings", None),
            ],
        )
    }
        <div class="max-w-2xl">
            <form method="POST" action="/autoban/settings" class="space-y-6">
                {_csrf_field(csrf_token)}

                <div>
                    <label class="block text-sm font-medium mb-1">Server</label>
                    <select name="guild_id" required id="guildSelect"
                            onchange="updateLogChannel()"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="">Select server...</option>
                        {guild_options}
                    </select>
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">
                        Log Channel
                        <span class="text-gray-400 font-normal">(BAN/KICK notification destination)</span>
                    </label>
                    <select name="log_channel_id" id="logChannelSelect"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="">None (disabled)</option>
                    </select>
                </div>

                <button type="submit"
                        class="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded transition-colors">
                    Save Settings
                </button>
            </form>
        </div>
    </div>

    <script>
    const channelsData = {channels_json};
    const configsData = {configs_json};
    function updateLogChannel() {{
        const guildId = document.getElementById('guildSelect').value;
        const logSelect = document.getElementById('logChannelSelect');
        logSelect.innerHTML = '<option value="">None (disabled)</option>';
        if (channelsData[guildId]) {{
            channelsData[guildId].forEach(ch => {{
                const opt = document.createElement('option');
                opt.value = ch.id;
                opt.textContent = '#' + ch.name;
                logSelect.appendChild(opt);
            }});
        }}
        // Restore saved value
        if (configsData[guildId]) {{
            logSelect.value = configsData[guildId];
        }}
    }}
    </script>
    """
    return _base("Autoban Settings", content)


# =============================================================================
# Ticket Templates
# =============================================================================


def ticket_list_page(
    tickets: list["Ticket"],
    csrf_token: str = "",
    guilds_map: dict[str, str] | None = None,
    status_filter: str = "",
) -> str:
    """Ticket list page template."""
    if guilds_map is None:
        guilds_map = {}

    row_parts: list[str] = []
    for ticket in tickets:
        guild_name = guilds_map.get(ticket.guild_id)
        if guild_name:
            guild_display = (
                f'<span class="font-medium">{escape(guild_name)}</span>'
                f'<br><span class="font-mono text-xs text-gray-500">'
                f"{escape(ticket.guild_id)}</span>"
            )
        else:
            guild_display = (
                f'<span class="font-mono text-yellow-400">'
                f"{escape(ticket.guild_id)}</span>"
            )

        status_colors = {
            "open": "text-green-400",
            "claimed": "text-blue-400",
            "closed": "text-gray-500",
        }
        status_class = status_colors.get(ticket.status, "text-gray-400")
        created = format_datetime(ticket.created_at)

        row_parts.append(f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 align-middle font-mono">#{ticket.ticket_number}</td>
            <td class="py-3 px-4 align-middle">{escape(ticket.username)}</td>
            <td class="py-3 px-4 align-middle">
                <span class="{status_class}">{escape(ticket.status)}</span>
            </td>
            <td class="py-3 px-4 align-middle">{guild_display}</td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">{created}</td>
            <td class="py-3 px-4 align-middle space-x-2">
                <a href="/tickets/{ticket.id}"
                   class="text-blue-400 hover:text-blue-300 text-sm">View</a>
                <a href="#" onclick="postAction('/tickets/{ticket.id}/delete', '{csrf_token}', 'Delete this ticket log?'); return false;"
                   class="text-red-400 hover:text-red-300 text-sm">Delete</a>
            </td>
        </tr>
        """)
    rows = "".join(row_parts)

    if not tickets:
        rows = """
        <tr>
            <td colspan="6" class="py-8 text-center text-gray-500">
                No tickets found
            </td>
        </tr>
        """

    # Status filter options
    filter_option_parts: list[str] = []
    for s in ["", "open", "claimed", "closed"]:
        selected = "selected" if s == status_filter else ""
        label = "All" if s == "" else s.capitalize()
        filter_option_parts.append(f'<option value="{s}" {selected}>{label}</option>')
    filter_options = "".join(filter_option_parts)

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Tickets",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Tickets", None),
            ],
        )
    }
        <div class="flex gap-3 mb-4 items-center">
            <a href="/tickets/panels"
               class="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded text-sm transition-colors">
                Panels
            </a>
            <form method="GET" action="/tickets" class="ml-auto flex items-center gap-2">
                <label class="text-sm text-gray-400">Status:</label>
                <select name="status" onchange="this.form.submit()"
                        class="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm text-gray-100">
                    {filter_options}
                </select>
            </form>
        </div>
        <div class="bg-gray-800 rounded-lg overflow-hidden overflow-x-auto">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="py-3 px-4 text-left">#</th>
                        <th class="py-3 px-4 text-left">User</th>
                        <th class="py-3 px-4 text-left">Status</th>
                        <th class="py-3 px-4 text-left">Server</th>
                        <th class="py-3 px-4 text-left">Created</th>
                        <th class="py-3 px-4 text-left">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
    </div>
    """
    return _base("Tickets", content)


# --- Discord-like transcript rendering ---

_DISCORD_AVATAR_COLORS = [
    "#5865F2",
    "#57F287",
    "#EB459E",
    "#ED4245",
    "#FAA61A",
    "#9B59B6",
    "#1ABC9C",
    "#E91E63",
    "#3498DB",
    "#2ECC71",
]

_TRANSCRIPT_MSG_RE = re.compile(
    r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (.+?): (.+)$"
)
_TRANSCRIPT_SYS_RE = re.compile(r"^===.*===$")
_TRANSCRIPT_META_RE = re.compile(r"^(Created by|Created at): (.+)$")


def _discord_avatar_color(username: str) -> str:
    """Get a consistent avatar color based on username hash."""
    return _DISCORD_AVATAR_COLORS[hash(username) % len(_DISCORD_AVATAR_COLORS)]


def _format_discord_content(content: str) -> str:
    """Format message content with styled attachments and stickers."""
    att_match = re.search(r"\[Attachments?: (.+?)\]", content)
    stk_match = re.search(r"\[Stickers?: (.+?)\]", content)

    main = content
    if att_match:
        main = main.replace(att_match.group(0), "").strip()
    if stk_match:
        main = main.replace(stk_match.group(0), "").strip()

    parts: list[str] = []
    if main:
        parts.append(escape(main))

    if att_match:
        for url in att_match.group(1).split(", "):
            eu = escape(url.strip())
            parts.append(
                f'<div style="margin-top:4px;">'
                f'<a href="{eu}" target="_blank" rel="noopener" '
                f'style="color:#00a8fc;font-size:13px;">'
                f"\U0001f4ce {eu}</a></div>"
            )

    if stk_match:
        parts.append(
            f'<div style="margin-top:4px;color:#949ba4;font-size:13px;">'
            f"\U0001f3f7\ufe0f {escape(stk_match.group(1))}</div>"
        )

    return "".join(parts) if parts else escape(content)


def _render_discord_transcript(transcript: str) -> str:
    """Render transcript as Discord dark mode chat UI."""
    lines = transcript.split("\n")
    parts: list[str] = []

    parts.append(
        "<style>"
        ".dc-msg:hover{background-color:#2e3035}"
        ".dc-msg .dc-ts{display:none}"
        ".dc-msg:hover .dc-ts{display:inline}"
        ".dc-chat::-webkit-scrollbar{width:8px}"
        ".dc-chat::-webkit-scrollbar-track{background:#2b2d31}"
        ".dc-chat::-webkit-scrollbar-thumb{background:#1a1b1e;border-radius:4px}"
        "</style>"
    )

    parts.append(
        '<div class="mt-6">'
        '<h3 class="text-lg font-semibold mb-2">Transcript</h3>'
        '<div class="dc-chat" style="background-color:#313338;border-radius:8px;padding:8px 0;max-height:600px;overflow-y:auto;">'
    )

    prev_user: str | None = None
    has_messages = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # System lines (=== ... ===)
        if _TRANSCRIPT_SYS_RE.match(line):
            prev_user = None
            parts.append(
                '<div style="text-align:center;padding:4px 16px;'
                f'color:#949ba4;font-size:12px;">{escape(line)}</div>'
            )
            continue

        # Meta lines (Created by/at)
        if _TRANSCRIPT_META_RE.match(line):
            parts.append(
                '<div style="text-align:center;padding:2px 16px;'
                f'color:#949ba4;font-size:12px;">{escape(line)}</div>'
            )
            continue

        # Chat messages
        m = _TRANSCRIPT_MSG_RE.match(line)
        if m:
            ts, username, content = m.groups()
            color = _discord_avatar_color(username)
            initial = escape(username[0].upper()) if username else "?"
            content_html = _format_discord_content(content)
            short_ts = escape(ts.split(" ")[1][:5])

            if username == prev_user:
                # Continuation message (compact, with hover timestamp)
                parts.append(
                    '<div class="dc-msg" style="padding:2px 16px 2px 72px;position:relative;line-height:1.375;">'
                    '<span class="dc-ts" style="position:absolute;left:0;width:72px;text-align:center;'
                    f'font-size:11px;color:#949ba4;line-height:22px;">{short_ts}</span>'
                    f'<span style="color:#dbdee1;font-size:14px;">{content_html}</span>'
                    "</div>"
                )
            else:
                # New message group with avatar
                prev_user = username
                mt = "margin-top:16px;" if has_messages else ""
                has_messages = True
                parts.append(
                    f'<div class="dc-msg" style="padding:4px 16px;display:flex;{mt}">'
                    # Avatar circle
                    f'<div style="width:40px;height:40px;border-radius:50%;background-color:{color};'
                    f"display:flex;align-items:center;justify-content:center;flex-shrink:0;"
                    f'margin-right:16px;margin-top:2px;">'
                    f'<span style="color:white;font-weight:600;font-size:16px;">{initial}</span></div>'
                    # Username + timestamp + content
                    f'<div style="min-width:0;flex:1;">'
                    f'<div><span style="color:{color};font-weight:600;font-size:14px;margin-right:8px;">'
                    f"{escape(username)}</span>"
                    f'<span style="color:#949ba4;font-size:12px;">{escape(ts)}</span></div>'
                    f'<div style="color:#dbdee1;font-size:14px;line-height:1.375;'
                    f'word-wrap:break-word;overflow-wrap:break-word;">'
                    f"{content_html}</div></div></div>"
                )
            continue

        # Fallback for unrecognized lines
        prev_user = None
        style = (
            "color:#f38ba8;font-style:italic;"
            if line.startswith("[Failed to fetch")
            else "color:#949ba4;"
        )
        parts.append(
            f'<div style="padding:4px 16px 4px 72px;font-size:13px;{style}">'
            f"{escape(line)}</div>"
        )

    parts.append("</div></div>")
    return "".join(parts)


def ticket_detail_page(
    ticket: "Ticket",
    category_name: str = "",
    guild_name: str = "",
    csrf_token: str = "",
) -> str:
    """Ticket detail page template."""
    import json as json_mod

    status_colors = {
        "open": "text-green-400",
        "claimed": "text-blue-400",
        "closed": "text-gray-500",
    }
    status_class = status_colors.get(ticket.status, "text-gray-400")

    created = format_datetime(ticket.created_at, "%Y-%m-%d %H:%M:%S")
    closed = format_datetime(ticket.closed_at, "%Y-%m-%d %H:%M:%S")

    # フォーム回答を表示
    form_answers_html = ""
    if ticket.form_answers:
        try:
            answers = json_mod.loads(ticket.form_answers)
            if isinstance(answers, list):
                form_answer_parts: list[str] = [
                    '<div class="mt-4"><h3 class="text-lg font-semibold mb-2">Form Answers</h3>'
                ]
                for qa in answers:
                    q = escape(str(qa.get("question", "")))
                    a = escape(str(qa.get("answer", "")))
                    form_answer_parts.append(f"""
                    <div class="bg-gray-700 rounded p-3 mb-2">
                        <div class="text-sm text-gray-400">{q}</div>
                        <div>{a}</div>
                    </div>
                    """)
                form_answer_parts.append("</div>")
                form_answers_html = "".join(form_answer_parts)
        except (json_mod.JSONDecodeError, TypeError):
            pass

    # トランスクリプト
    transcript_html = ""
    if ticket.transcript:
        transcript_html = _render_discord_transcript(ticket.transcript)
    elif ticket.status != "closed":
        transcript_html = """
        <div class="mt-6">
            <h3 class="text-lg font-semibold mb-2">Transcript</h3>
            <p class="text-gray-500 text-sm">Transcript will be available after the ticket is closed.</p>
        </div>
        """

    delete_form = f"""
        <div class="flex justify-end mb-4">
            <form method="POST" action="/tickets/{ticket.id}/delete"
                  onsubmit="return confirm('Delete this ticket log?');">
                {_csrf_field(csrf_token)}
                <button type="submit"
                        class="bg-red-600 hover:bg-red-500 px-4 py-2 rounded text-sm transition-colors">
                    Delete
                </button>
            </form>
        </div>
    """

    content = f"""
    <div class="p-6">
        {
        _nav(
            f"Ticket #{ticket.ticket_number}",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Tickets", "/tickets"),
                (f"Ticket #{ticket.ticket_number}", None),
            ],
        )
    }
        {delete_form}
        <div class="bg-gray-800 rounded-lg p-6">
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div>
                    <div class="text-sm text-gray-400">Status</div>
                    <div class="{status_class} font-medium">{
        escape(ticket.status)
    }</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">User</div>
                    <div>{escape(ticket.username)}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">Category</div>
                    <div>{escape(category_name)}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">Server</div>
                    <div>{escape(guild_name or ticket.guild_id)}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">Created</div>
                    <div class="text-sm">{created}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">Closed</div>
                    <div class="text-sm">{closed}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">Claimed By</div>
                    <div class="text-sm">{escape(ticket.claimed_by or "-")}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">Closed By</div>
                    <div class="text-sm">{escape(ticket.closed_by or "-")}</div>
                </div>
            </div>

            {form_answers_html}
            {transcript_html}
        </div>
    </div>
    """
    return _base(f"Ticket #{ticket.ticket_number}", content)


def ticket_panels_list_page(
    panels: list["TicketPanel"],
    csrf_token: str = "",
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
) -> str:
    """Ticket panels list page template."""
    if guilds_map is None:
        guilds_map = {}
    if channels_map is None:
        channels_map = {}

    def get_channel_name(guild_id: str, channel_id: str) -> str:
        """チャンネル名を取得する。"""
        for cid, name in channels_map.get(guild_id, []):
            if cid == channel_id:
                return f"#{name}"
        return channel_id

    row_parts: list[str] = []
    for panel in panels:
        guild_name = guilds_map.get(panel.guild_id, panel.guild_id)
        created = format_datetime(panel.created_at)
        posted = "Yes" if panel.message_id else "No"

        row_parts.append(f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 align-middle">
                <a href="/tickets/panels/{panel.id}"
                   class="font-medium text-blue-400 hover:text-blue-300">
                    {escape(panel.title)}
                </a>
            </td>
            <td class="py-3 px-4 align-middle text-sm">{escape(guild_name)}</td>
            <td class="py-3 px-4 align-middle text-sm">{escape(get_channel_name(panel.guild_id, panel.channel_id))}</td>
            <td class="py-3 px-4 align-middle text-sm">{posted}</td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">{created}</td>
            <td class="py-3 px-4 align-middle">
                <a href="#" onclick="postAction('/tickets/panels/{panel.id}/delete', '{csrf_token}', 'Delete this panel?'); return false;"
                   class="text-red-400 hover:text-red-300 text-sm">Delete</a>
            </td>
        </tr>
        """)
    rows = "".join(row_parts)

    if not panels:
        rows = """
        <tr>
            <td colspan="6" class="py-8 text-center text-gray-500">
                No ticket panels configured
            </td>
        </tr>
        """

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Ticket Panels",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Tickets", "/tickets"),
                ("Panels", None),
            ],
        )
    }
        <div class="flex gap-3 mb-4">
            <a href="/tickets/panels/new"
               class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm transition-colors">
                + Create Panel
            </a>
        </div>
        <div class="bg-gray-800 rounded-lg overflow-hidden overflow-x-auto">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="py-3 px-4 text-left">Title</th>
                        <th class="py-3 px-4 text-left">Server</th>
                        <th class="py-3 px-4 text-left">Channel</th>
                        <th class="py-3 px-4 text-left">Posted</th>
                        <th class="py-3 px-4 text-left">Created</th>
                        <th class="py-3 px-4 text-left">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
    </div>
    """
    return _base("Ticket Panels", content)


def ticket_panel_create_page(
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
    roles_map: dict[str, list[tuple[str, str]]] | None = None,
    discord_categories_map: dict[str, list[tuple[str, str]]] | None = None,
    csrf_token: str = "",
    error: str | None = None,
) -> str:
    """Ticket panel create page template."""
    if guilds_map is None:
        guilds_map = {}
    if channels_map is None:
        channels_map = {}
    if roles_map is None:
        roles_map = {}
    if discord_categories_map is None:
        discord_categories_map = {}

    guild_options = ""
    for gid, gname in sorted(guilds_map.items(), key=lambda x: x[1]):
        guild_options += (
            f'<option value="{escape(gid)}">{escape(gname)} ({escape(gid)})</option>'
        )

    error_html = ""
    if error:
        error_html = f"""
        <div class="bg-red-500/20 border border-red-500 text-red-300 px-4 py-3 rounded mb-6">
            {escape(error)}
        </div>
        """

    import json as json_mod

    channels_data: dict[str, list[dict[str, str]]] = {}
    for gid, ch_list in channels_map.items():
        channels_data[gid] = [{"id": cid, "name": cname} for cid, cname in ch_list]
    channels_json = json_mod.dumps(channels_data)

    roles_data: dict[str, list[dict[str, str]]] = {}
    for gid, role_list in roles_map.items():
        roles_data[gid] = [{"id": rid, "name": name} for rid, name in role_list]
    roles_json = json_mod.dumps(roles_data)

    cat_data: dict[str, list[dict[str, str]]] = {}
    for gid, cat_list in discord_categories_map.items():
        cat_data[gid] = [{"id": cid, "name": cname} for cid, cname in cat_list]
    discord_cats_json = json_mod.dumps(cat_data)

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Create Ticket Panel",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Tickets", "/tickets"),
                ("Panels", "/tickets/panels"),
                ("Create", None),
            ],
        )
    }
        {error_html}
        <div class="max-w-2xl">
            <form method="POST" action="/tickets/panels/new" class="space-y-6">
                {_csrf_field(csrf_token)}

                <div>
                    <label class="block text-sm font-medium mb-1">Server</label>
                    <select name="guild_id" required id="guildSelect"
                            onchange="updateSelects()"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="">Select server...</option>
                        {guild_options}
                    </select>
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">Channel</label>
                    <select name="channel_id" required id="channelSelect"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="">Select channel...</option>
                    </select>
                    <p class="text-xs text-gray-500 mt-1">
                        The channel where the ticket panel will be posted.
                    </p>
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">Title</label>
                    <input type="text" name="title" required
                           placeholder="e.g. Support Ticket"
                           class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">
                        Description
                        <span class="text-gray-400 font-normal">(optional)</span>
                    </label>
                    <textarea name="description" rows="3"
                              placeholder="Click a button below to create a ticket."
                              class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100"></textarea>
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">Staff Role</label>
                    <select name="staff_role_id" required id="staffRoleSelect"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="">Select role...</option>
                    </select>
                    <p class="text-xs text-gray-500 mt-1">
                        Staff with this role can view and manage tickets.
                    </p>
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">
                        Discord Category
                        <span class="text-gray-400 font-normal">(optional)</span>
                    </label>
                    <select name="discord_category_id" id="discordCategorySelect"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="">None</option>
                    </select>
                    <p class="text-xs text-gray-500 mt-1">
                        Ticket channels will be created under this Discord category.
                    </p>
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">Channel Prefix</label>
                    <input type="text" name="channel_prefix" value="ticket-"
                           class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">
                        Log Channel
                        <span class="text-gray-400 font-normal">(optional)</span>
                    </label>
                    <select name="log_channel_id" id="logChannelSelect"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="">None</option>
                    </select>
                    <p class="text-xs text-gray-500 mt-1">
                        Close notifications will be sent to this channel.
                    </p>
                </div>

                <button type="submit"
                        class="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded transition-colors">
                    Create Panel
                </button>
            </form>
        </div>
    </div>

    <script>
    const channelsData = {channels_json};
    const rolesData = {roles_json};
    const discordCatsData = {discord_cats_json};
    function updateSelects() {{
        const guildId = document.getElementById('guildSelect').value;

        const chSelect = document.getElementById('channelSelect');
        chSelect.innerHTML = '<option value="">Select channel...</option>';
        if (channelsData[guildId]) {{
            channelsData[guildId].forEach(ch => {{
                const opt = document.createElement('option');
                opt.value = ch.id;
                opt.textContent = '#' + ch.name;
                chSelect.appendChild(opt);
            }});
        }}

        const roleSelect = document.getElementById('staffRoleSelect');
        roleSelect.innerHTML = '<option value="">Select role...</option>';
        if (rolesData[guildId]) {{
            rolesData[guildId].forEach(role => {{
                const opt = document.createElement('option');
                opt.value = role.id;
                opt.textContent = role.name;
                roleSelect.appendChild(opt);
            }});
        }}

        const catSelect = document.getElementById('discordCategorySelect');
        catSelect.innerHTML = '<option value="">None</option>';
        if (discordCatsData[guildId]) {{
            discordCatsData[guildId].forEach(cat => {{
                const opt = document.createElement('option');
                opt.value = cat.id;
                opt.textContent = cat.name;
                catSelect.appendChild(opt);
            }});
        }}

        const logSelect = document.getElementById('logChannelSelect');
        logSelect.innerHTML = '<option value="">None</option>';
        if (channelsData[guildId]) {{
            channelsData[guildId].forEach(ch => {{
                const opt = document.createElement('option');
                opt.value = ch.id;
                opt.textContent = '#' + ch.name;
                logSelect.appendChild(opt);
            }});
        }}
    }}
    </script>
    """
    return _base("Create Ticket Panel", content)


def ticket_panel_detail_page(
    panel: "TicketPanel",
    associations: list[tuple["TicketPanelCategory", str]],
    success: str | None = None,
    guild_name: str | None = None,
    channel_name: str | None = None,
    csrf_token: str = "",
) -> str:
    """Ticket panel detail/edit page template.

    Args:
        panel: チケットパネル
        associations: (TicketPanelCategory, category_name) のリスト
        success: 成功メッセージ
        guild_name: ギルド名
        channel_name: チャンネル名
        csrf_token: CSRF トークン
    """
    success_html = ""
    if success:
        success_html = f"""
        <div class="bg-green-900/50 border border-green-700 rounded-lg p-3 mb-4">
            <span class="text-green-400">{escape(success)}</span>
        </div>
        """

    server_display = escape(guild_name or panel.guild_id)
    channel_display = escape(channel_name or panel.channel_id)
    message_display = escape(panel.message_id) if panel.message_id else "(not posted)"
    created = format_datetime(panel.created_at)

    # Post/Update to Discord ボタン
    if panel.message_id:
        discord_btn_label = "Update in Discord"
        discord_confirm = "Update the panel message in Discord?"
    else:
        discord_btn_label = "Post to Discord"
        discord_confirm = "Post this panel to Discord?"

    # カテゴリボタン行
    button_row_parts: list[str] = []
    style_options_map = {
        "primary": "Blue",
        "secondary": "Gray",
        "success": "Green",
        "danger": "Red",
    }
    for assoc, cat_name in associations:
        style_option_parts: list[str] = []
        for val, label in style_options_map.items():
            selected = "selected" if assoc.button_style == val else ""
            style_option_parts.append(
                f'<option value="{val}" {selected}>{label}</option>'
            )
        style_options = "".join(style_option_parts)

        button_row_parts.append(f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 align-middle text-sm">{escape(cat_name)}</td>
            <td class="py-3 px-4 align-middle">
                <form method="POST"
                      action="/tickets/panels/{panel.id}/buttons/{assoc.id}/edit"
                      class="flex gap-2 items-center flex-wrap">
                    {_csrf_field(csrf_token)}
                    <input type="text" name="button_label"
                           value="{escape(assoc.button_label or "")}"
                           placeholder="{escape(cat_name)}"
                           maxlength="80"
                           class="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm w-32">
                    <select name="button_style"
                            class="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm">
                        {style_options}
                    </select>
                    <input type="text" name="button_emoji"
                           value="{escape(assoc.button_emoji or "")}"
                           placeholder="Emoji"
                           maxlength="64"
                           class="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm w-20">
                    <button type="submit"
                            class="bg-blue-600 hover:bg-blue-500 px-3 py-1 rounded text-sm transition-colors">
                        Save
                    </button>
                </form>
            </td>
        </tr>
        """)
    button_rows = "".join(button_row_parts)

    if not associations:
        button_rows = """
        <tr>
            <td colspan="2" class="py-8 text-center text-gray-500">
                No category buttons configured
            </td>
        </tr>
        """

    content = f"""
    <div class="p-6">
        {
        _nav(
            escape(panel.title),
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Tickets", "/tickets"),
                ("Panels", "/tickets/panels"),
                (escape(panel.title), None),
            ],
        )
    }
        {success_html}

        <div class="bg-gray-800 rounded-lg p-6 mb-6">
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <div>
                    <div class="text-sm text-gray-400">Server</div>
                    <div class="text-sm">{server_display}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">Channel</div>
                    <div class="text-sm">{channel_display}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">Message ID</div>
                    <div class="text-sm font-mono">{message_display}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">Created</div>
                    <div class="text-sm">{created}</div>
                </div>
            </div>

            <div class="border-t border-gray-700 pt-4">
                <h3 class="text-lg font-semibold mb-3">Edit Panel</h3>
                <form method="POST" action="/tickets/panels/{panel.id}/edit"
                      class="space-y-4">
                    {_csrf_field(csrf_token)}
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Title</label>
                        <input type="text" name="title"
                               value="{escape(panel.title)}"
                               required maxlength="100"
                               class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Description</label>
                        <textarea name="description" rows="3" maxlength="2000"
                                  class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100"
                                  >{escape(panel.description or "")}</textarea>
                    </div>
                    <button type="submit"
                            class="bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded text-sm transition-colors">
                        Save Changes
                    </button>
                </form>
            </div>

            <div class="border-t border-gray-700 pt-4 mt-4">
                <form method="POST" action="/tickets/panels/{panel.id}/post"
                      onsubmit="return confirm('{discord_confirm}');">
                    {_csrf_field(csrf_token)}
                    <button type="submit"
                            class="bg-indigo-600 hover:bg-indigo-500 px-4 py-2 rounded text-sm transition-colors">
                        {discord_btn_label}
                    </button>
                </form>
            </div>
        </div>

        <div class="bg-gray-800 rounded-lg p-6">
            <h3 class="text-lg font-semibold mb-4">Category Buttons ({
        len(associations)
    })</h3>
            <div class="overflow-x-auto">
                <table class="w-full">
                    <thead class="bg-gray-700">
                        <tr>
                            <th class="py-3 px-4 text-left">Category</th>
                            <th class="py-3 px-4 text-left">Button Settings</th>
                        </tr>
                    </thead>
                    <tbody>
                        {button_rows}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    """
    return _base(f"Panel: {escape(panel.title)}", content)


def joinrole_page(
    configs: list["JoinRoleConfig"],
    csrf_token: str = "",
    guilds_map: dict[str, str] | None = None,
    roles_by_guild: dict[str, list[tuple[str, str, int]]] | None = None,
) -> str:
    """Join Role 設定一覧＋新規作成ページ。"""
    import json as json_mod

    if guilds_map is None:
        guilds_map = {}
    if roles_by_guild is None:
        roles_by_guild = {}

    row_parts: list[str] = []
    for config in configs:
        guild_name = guilds_map.get(config.guild_id)
        if guild_name:
            guild_display = (
                f'<span class="font-medium">{escape(guild_name)}</span>'
                f'<br><span class="font-mono text-xs text-gray-500">'
                f"{escape(config.guild_id)}</span>"
            )
        else:
            guild_display = (
                f'<span class="font-mono text-yellow-400">'
                f"{escape(config.guild_id)}</span>"
            )

        # ロール名をルックアップ
        role_name = config.role_id
        guild_roles = roles_by_guild.get(config.guild_id, [])
        for rid, r_name, _color in guild_roles:
            if rid == config.role_id:
                role_name = r_name
                break

        status = "Enabled" if config.enabled else "Disabled"
        status_class = "text-green-400" if config.enabled else "text-gray-500"
        created = format_datetime(config.created_at)

        row_parts.append(f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 align-middle">{guild_display}</td>
            <td class="py-3 px-4 align-middle">{escape(role_name)}</td>
            <td class="py-3 px-4 align-middle">{config.duration_hours}h</td>
            <td class="py-3 px-4 align-middle">
                <span class="{status_class}">{status}</span>
            </td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">{created}</td>
            <td class="py-3 px-4 align-middle space-x-2">
                <a href="#" onclick="postAction('/joinrole/{config.id}/toggle', '{csrf_token}'); return false;"
                   class="text-blue-400 hover:text-blue-300 text-sm">Toggle</a>
                <a href="#" onclick="postAction('/joinrole/{config.id}/delete', '{csrf_token}', 'Delete this join role config?'); return false;"
                   class="text-red-400 hover:text-red-300 text-sm">Delete</a>
            </td>
        </tr>
        """)
    rows = "".join(row_parts)

    if not configs:
        rows = """
        <tr>
            <td colspan="6" class="py-8 text-center text-gray-500">
                No join role configs configured
            </td>
        </tr>
        """

    # ギルド選択肢
    guild_options = "".join(
        f'<option value="{escape(gid)}">{escape(gname)}</option>'
        for gid, gname in guilds_map.items()
    )

    # ロール情報を JSON 化 (JS で guild 選択時にフィルタ)
    roles_data: dict[str, list[dict[str, str]]] = {}
    for gid, role_list in roles_by_guild.items():
        roles_data[gid] = [{"id": rid, "name": name} for rid, name, _c in role_list]
    roles_json = json_mod.dumps(roles_data)

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Join Role",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Join Role", None),
            ],
        )
    }
        <div class="bg-gray-800 rounded-lg overflow-hidden overflow-x-auto mb-6">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="py-3 px-4 text-left">Server</th>
                        <th class="py-3 px-4 text-left">Role</th>
                        <th class="py-3 px-4 text-left">Duration</th>
                        <th class="py-3 px-4 text-left">Status</th>
                        <th class="py-3 px-4 text-left">Created</th>
                        <th class="py-3 px-4 text-left">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>

        <div class="bg-gray-800 rounded-lg p-6">
            <h2 class="text-lg font-semibold mb-4">Add Join Role Config</h2>
            <form method="POST" action="/joinrole/new">
                {_csrf_field(csrf_token)}
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Server</label>
                        <select name="guild_id" id="joinroleGuildSelect" onchange="updateJoinRoleSelect()"
                                class="w-full bg-gray-700 rounded px-3 py-2 text-sm" required>
                            <option value="">Select server...</option>
                            {guild_options}
                        </select>
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Role</label>
                        <select name="role_id" id="joinroleRoleSelect"
                                class="w-full bg-gray-700 rounded px-3 py-2 text-sm" required>
                            <option value="">Select role...</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Duration (hours)</label>
                        <input type="number" name="duration_hours" min="1" max="720" value="24"
                               class="w-full bg-gray-700 rounded px-3 py-2 text-sm" required>
                    </div>
                </div>
                <button type="submit"
                        class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm transition-colors">
                    Add Config
                </button>
            </form>
        </div>
    </div>

    <script>
    const joinroleRolesData = {roles_json};
    function updateJoinRoleSelect() {{
        const guildId = document.getElementById('joinroleGuildSelect').value;
        const roleSelect = document.getElementById('joinroleRoleSelect');
        roleSelect.innerHTML = '<option value="">Select role...</option>';
        if (joinroleRolesData[guildId]) {{
            joinroleRolesData[guildId].forEach(role => {{
                const opt = document.createElement('option');
                opt.value = role.id;
                opt.textContent = role.name;
                roleSelect.appendChild(opt);
            }});
        }}
    }}
    </script>
    """
    return _base("Join Role", content)


def activity_page(
    activity_type: str = "playing",
    activity_text: str = "",
    csrf_token: str = "",
) -> str:
    """Bot Activity settings page template."""
    type_options = [
        ("playing", "プレイ中 (Playing)"),
        ("listening", "再生中 (Listening)"),
        ("watching", "視聴中 (Watching)"),
        ("competing", "参戦中 (Competing)"),
    ]
    options_html = ""
    for value, label in type_options:
        selected = " selected" if value == activity_type else ""
        options_html += (
            f'<option value="{escape(value)}"{selected}>{escape(label)}</option>'
        )

    current_label = dict(type_options).get(activity_type, activity_type)

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Bot Activity",
            breadcrumbs=[("Dashboard", "/dashboard"), ("Bot Activity", None)],
        )
    }
        <div class="max-w-2xl">
            <div class="bg-gray-800 rounded-lg p-6 mb-6">
                <h3 class="text-sm font-medium text-gray-400 mb-2">Current Setting</h3>
                <p class="text-lg">
                    <span class="text-gray-400">{escape(current_label)}:</span>
                    <span class="font-semibold">{
        escape(activity_text)
        if activity_text
        else '<span class="text-gray-500">Not set (using default)</span>'
    }</span>
                </p>
            </div>

            <form method="POST" action="/activity" class="space-y-6">
                {_csrf_field(csrf_token)}

                <div>
                    <label class="block text-sm font-medium mb-1">Activity Type</label>
                    <select name="activity_type" required
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        {options_html}
                    </select>
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">Text</label>
                    <input type="text" name="activity_text" required maxlength="128"
                           value="{escape(activity_text)}"
                           placeholder="お菓子を食べています"
                           class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                    <p class="text-gray-400 text-xs mt-1">Maximum 128 characters</p>
                </div>

                <button type="submit"
                        class="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded transition-colors">
                    Save
                </button>
            </form>
        </div>
    </div>
    """
    return _base("Bot Activity", content)
