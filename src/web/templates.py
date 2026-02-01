"""HTML templates using f-strings and Tailwind CSS."""

from html import escape
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.database.models import (
        BumpConfig,
        BumpReminder,
        Lobby,
        RolePanel,
        RolePanelItem,
        StickyMessage,
    )


def _base(title: str, content: str) -> str:
    """Base HTML template with Tailwind CDN."""
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(title)} - Bot Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen">
    {content}
</body>
</html>"""


def _nav(title: str, show_dashboard_link: bool = True) -> str:
    """Navigation bar component."""
    dashboard_link = ""
    if show_dashboard_link:
        dashboard_link = (
            '<a href="/dashboard" class="text-gray-400 hover:text-white">'
            "&larr; Dashboard</a>"
        )
    return f"""
    <nav class="flex justify-between items-center mb-8">
        <div class="flex items-center gap-4">
            {dashboard_link}
            <h1 class="text-2xl font-bold">{escape(title)}</h1>
        </div>
        <a href="/logout"
           class="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded transition-colors">
            Logout
        </a>
    </nav>
    """


def login_page(error: str | None = None) -> str:
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
            </div>
        </div>
    </div>
    """
    return _base("Settings", content)


def email_change_page(
    current_email: str,
    pending_email: str | None = None,
    error: str | None = None,
    success: str | None = None,
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
        {_nav("Change Email", show_dashboard_link=True)}
        <div class="max-w-md">
            <div class="bg-gray-800 p-6 rounded-lg">
                {message_html}
                {pending_email_html}
                <p class="text-gray-400 text-sm mb-4">
                    Current email: <strong>{escape(current_email)}</strong>
                </p>
                <form method="POST" action="/settings/email">
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
                <div class="mt-4">
                    <a href="/settings" class="text-gray-400 hover:text-white text-sm">
                        &larr; Back to settings
                    </a>
                </div>
            </div>
        </div>
    </div>
    """
    return _base("Change Email", content)


def password_change_page(
    error: str | None = None,
    success: str | None = None,
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
        {_nav("Change Password", show_dashboard_link=True)}
        <div class="max-w-md">
            <div class="bg-gray-800 p-6 rounded-lg">
                {message_html}
                <form method="POST" action="/settings/password">
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
                <div class="mt-4">
                    <a href="/settings" class="text-gray-400 hover:text-white text-sm">
                        &larr; Back to settings
                    </a>
                </div>
            </div>
        </div>
    </div>
    """
    return _base("Change Password", content)


def initial_setup_page(
    current_email: str,
    error: str | None = None,
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


def lobbies_list_page(lobbies: list["Lobby"]) -> str:
    """Lobbies list page template."""
    rows = ""
    for lobby in lobbies:
        session_count = len(lobby.sessions) if lobby.sessions else 0
        rows += f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4">{lobby.id}</td>
            <td class="py-3 px-4 font-mono text-sm">{escape(lobby.guild_id)}</td>
            <td class="py-3 px-4 font-mono text-sm">{escape(lobby.lobby_channel_id)}</td>
            <td class="py-3 px-4">{lobby.default_user_limit or "無制限"}</td>
            <td class="py-3 px-4">{session_count}</td>
            <td class="py-3 px-4">
                <form method="POST" action="/lobbies/{lobby.id}/delete"
                      onsubmit="return confirm('Delete this lobby?');">
                    <button type="submit"
                            class="text-red-400 hover:text-red-300 text-sm">
                        Delete
                    </button>
                </form>
            </td>
        </tr>
        """

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
        {_nav("Lobbies")}
        <div class="bg-gray-800 rounded-lg overflow-hidden">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="py-3 px-4 text-left">ID</th>
                        <th class="py-3 px-4 text-left">Guild ID</th>
                        <th class="py-3 px-4 text-left">Channel ID</th>
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


def sticky_list_page(stickies: list["StickyMessage"]) -> str:
    """Sticky messages list page template."""
    rows = ""
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
        rows += f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 font-mono text-sm">{escape(sticky.guild_id)}</td>
            <td class="py-3 px-4 font-mono text-sm">{escape(sticky.channel_id)}</td>
            <td class="py-3 px-4">{title_display}</td>
            <td class="py-3 px-4 text-gray-400 text-sm">{desc_display}</td>
            <td class="py-3 px-4">{escape(sticky.message_type)}</td>
            <td class="py-3 px-4">{sticky.cooldown_seconds}s</td>
            <td class="py-3 px-4">
                <span class="inline-block w-4 h-4 rounded" style="background-color: {color_display if sticky.color else "transparent"}"></span>
                {color_display}
            </td>
            <td class="py-3 px-4">
                <form method="POST" action="/sticky/{sticky.channel_id}/delete"
                      onsubmit="return confirm('Delete this sticky message?');">
                    <button type="submit"
                            class="text-red-400 hover:text-red-300 text-sm">
                        Delete
                    </button>
                </form>
            </td>
        </tr>
        """

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
        {_nav("Sticky Messages")}
        <div class="bg-gray-800 rounded-lg overflow-hidden overflow-x-auto">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="py-3 px-4 text-left">Guild ID</th>
                        <th class="py-3 px-4 text-left">Channel ID</th>
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


def bump_list_page(configs: list["BumpConfig"], reminders: list["BumpReminder"]) -> str:
    """Bump configs and reminders list page template."""
    config_rows = ""
    for config in configs:
        config_rows += f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 font-mono text-sm">{escape(config.guild_id)}</td>
            <td class="py-3 px-4 font-mono text-sm">{escape(config.channel_id)}</td>
            <td class="py-3 px-4 text-gray-400 text-sm">
                {config.created_at.strftime("%Y-%m-%d %H:%M") if config.created_at else "-"}
            </td>
            <td class="py-3 px-4">
                <form method="POST" action="/bump/config/{config.guild_id}/delete"
                      onsubmit="return confirm('Delete this bump config?');">
                    <button type="submit"
                            class="text-red-400 hover:text-red-300 text-sm">
                        Delete
                    </button>
                </form>
            </td>
        </tr>
        """

    if not configs:
        config_rows = """
        <tr>
            <td colspan="4" class="py-8 text-center text-gray-500">
                No bump configs
            </td>
        </tr>
        """

    reminder_rows = ""
    for reminder in reminders:
        status = "Enabled" if reminder.is_enabled else "Disabled"
        status_class = "text-green-400" if reminder.is_enabled else "text-gray-500"
        remind_at = (
            reminder.remind_at.strftime("%Y-%m-%d %H:%M") if reminder.remind_at else "-"
        )
        reminder_rows += f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4">{reminder.id}</td>
            <td class="py-3 px-4 font-mono text-sm">{escape(reminder.guild_id)}</td>
            <td class="py-3 px-4">{escape(reminder.service_name)}</td>
            <td class="py-3 px-4 font-mono text-sm">{escape(reminder.channel_id)}</td>
            <td class="py-3 px-4 text-gray-400 text-sm">{remind_at}</td>
            <td class="py-3 px-4">
                <span class="{status_class}">{status}</span>
            </td>
            <td class="py-3 px-4">
                <div class="flex gap-2">
                    <form method="POST" action="/bump/reminder/{reminder.id}/toggle">
                        <button type="submit"
                                class="text-blue-400 hover:text-blue-300 text-sm">
                            Toggle
                        </button>
                    </form>
                    <form method="POST" action="/bump/reminder/{reminder.id}/delete"
                          onsubmit="return confirm('Delete this reminder?');">
                        <button type="submit"
                                class="text-red-400 hover:text-red-300 text-sm">
                            Delete
                        </button>
                    </form>
                </div>
            </td>
        </tr>
        """

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
        {_nav("Bump Reminders")}

        <h2 class="text-xl font-semibold mb-4">Bump Configs</h2>
        <div class="bg-gray-800 rounded-lg overflow-hidden mb-8">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="py-3 px-4 text-left">Guild ID</th>
                        <th class="py-3 px-4 text-left">Channel ID</th>
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
                        <th class="py-3 px-4 text-left">Guild ID</th>
                        <th class="py-3 px-4 text-left">Service</th>
                        <th class="py-3 px-4 text-left">Channel ID</th>
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
) -> str:
    """Role panels list page template."""
    panel_rows = ""
    for panel in panels:
        panel_type_badge = (
            '<span class="bg-blue-600 px-2 py-1 rounded text-xs">Button</span>'
            if panel.panel_type == "button"
            else '<span class="bg-purple-600 px-2 py-1 rounded text-xs">Reaction</span>'
        )
        remove_reaction_badge = ""
        if panel.panel_type == "reaction" and panel.remove_reaction:
            remove_reaction_badge = (
                '<span class="bg-yellow-600 px-2 py-1 rounded text-xs ml-1">'
                "Auto-remove</span>"
            )

        items = items_by_panel.get(panel.id, [])
        items_html = ""
        if items:
            items_html = '<div class="flex flex-wrap gap-1 mt-2">'
            for item in items:
                label = escape(item.label) if item.label else ""
                items_html += f"""
                <span class="bg-gray-700 px-2 py-1 rounded text-xs">
                    {escape(item.emoji)} {label}
                </span>
                """
            items_html += "</div>"
        else:
            items_html = '<p class="text-gray-500 text-xs mt-2">No roles configured</p>'

        created_at = (
            panel.created_at.strftime("%Y-%m-%d %H:%M") if panel.created_at else "-"
        )

        panel_rows += f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4">
                <a href="/rolepanels/{panel.id}"
                   class="font-medium text-blue-400 hover:text-blue-300">
                    {escape(panel.title)}
                </a>
                <div class="text-gray-500 text-xs mt-1">
                    {escape(panel.description or "")}
                </div>
            </td>
            <td class="py-3 px-4">
                {panel_type_badge}{remove_reaction_badge}
            </td>
            <td class="py-3 px-4 font-mono text-sm">{escape(panel.guild_id)}</td>
            <td class="py-3 px-4 font-mono text-sm">{escape(panel.channel_id)}</td>
            <td class="py-3 px-4">
                <div class="text-sm">{len(items)} role(s)</div>
                {items_html}
            </td>
            <td class="py-3 px-4 text-gray-400 text-sm">{created_at}</td>
            <td class="py-3 px-4">
                <div class="flex gap-2">
                    <a href="/rolepanels/{panel.id}"
                       class="text-blue-400 hover:text-blue-300 text-sm">
                        Edit
                    </a>
                    <form method="POST" action="/rolepanels/{panel.id}/delete"
                          onsubmit="return confirm('Delete this role panel?');">
                        <button type="submit"
                                class="text-red-400 hover:text-red-300 text-sm">
                            Delete
                        </button>
                    </form>
                </div>
            </td>
        </tr>
        """

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
        {_nav("Role Panels")}

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
                        <th class="py-3 px-4 text-left">Guild ID</th>
                        <th class="py-3 px-4 text-left">Channel ID</th>
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
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
    discord_roles: dict[str, list[tuple[str, str, int]]] | None = None,
) -> str:
    """Role panel create page template.

    Args:
        guilds_map: ギルドID -> ギルド名 のマッピング
        channels_map: ギルドID -> [(channel_id, channel_name), ...] のマッピング
        discord_roles: ギルドID -> [(role_id, role_name, color), ...] のマッピング
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

    content = f"""
    <div class="p-6">
        {_nav("Create Role Panel")}
        <div class="max-w-lg">
            <div class="bg-gray-800 p-6 rounded-lg">
                {message_html}
                {no_guilds_warning}
                <form method="POST" action="/rolepanels/new" id="createPanelForm">
                    <div class="mb-4">
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
                        <p class="text-gray-500 text-xs mt-1">
                            Select a Discord server where the Bot is present
                        </p>
                    </div>

                    <div class="mb-4">
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
                        <p class="text-gray-500 text-xs mt-1">
                            Text channel where the panel will be posted
                        </p>
                    </div>

                    <div class="mb-4">
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
                        <p class="text-gray-500 text-xs mt-1">
                            Button: users click buttons. Reaction: users add/remove emoji reactions.
                        </p>
                    </div>

                    <div class="mb-4">
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

                    <div class="mb-6">
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

                    <!-- Role Items Section -->
                    <div class="mb-6 border-t border-gray-600 pt-6">
                        <div class="flex justify-between items-center mb-4">
                            <label class="block text-sm font-medium">
                                Role Items <span class="text-red-400">*</span>
                            </label>
                            <button
                                type="button"
                                id="addRoleItemBtn"
                                class="bg-green-600 hover:bg-green-700 text-white text-sm
                                       py-1 px-3 rounded transition-colors disabled:opacity-50
                                       disabled:cursor-not-allowed disabled:hover:bg-green-600"
                            >
                                + Add Role
                            </button>
                        </div>
                        <p class="text-gray-500 text-xs mb-4">
                            Add at least one role for users to select.
                        </p>
                        <p id="noKnownRolesInfo" class="text-red-400 text-xs mb-4 hidden">
                            No roles found for this guild. Please sync roles by starting the Bot first.
                        </p>
                        <div id="roleItemsContainer" class="space-y-3">
                            <!-- Role item rows will be added here by JavaScript -->
                        </div>
                        <p id="noRolesWarning" class="text-yellow-400 text-sm mt-2">
                            Please add at least one role item before creating the panel.
                        </p>
                    </div>

                    <button
                        type="submit"
                        id="submitBtn"
                        class="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium
                               py-2 px-4 rounded transition-colors disabled:opacity-50
                               disabled:cursor-not-allowed"
                        disabled
                    >
                        Create Panel
                    </button>
                </form>
                <p class="mt-4 text-gray-500 text-sm">
                    The panel will be created with the roles you add above.
                </p>
                <div class="mt-4">
                    <a href="/rolepanels" class="text-gray-400 hover:text-white text-sm">
                        &larr; Back to role panels
                    </a>
                </div>
            </div>
        </div>
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

        // --- Role Items Management ---
        const discordRoles = {discord_roles_json};
        const roleItemsContainer = document.getElementById('roleItemsContainer');
        const addRoleItemBtn = document.getElementById('addRoleItemBtn');
        const submitBtn = document.getElementById('submitBtn');
        const noRolesWarning = document.getElementById('noRolesWarning');
        const noKnownRolesInfo = document.getElementById('noKnownRolesInfo');
        let roleItemIndex = 0;

        function updateSubmitButton() {{
            const itemCount = roleItemsContainer.querySelectorAll('.role-item-row').length;
            const hasGuild = guildSelect.value !== '';
            submitBtn.disabled = itemCount === 0 || !hasGuild;
            noRolesWarning.classList.toggle('hidden', itemCount > 0);
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

        function createRoleItemRow(index) {{
            const row = document.createElement('div');
            row.className = 'role-item-row bg-gray-700 p-4 rounded flex flex-wrap gap-3 items-end';
            row.draggable = true;

            const availableRoles = getRolesForCurrentGuild();
            let roleSelectHtml = '';
            if (availableRoles.length > 0) {{
                const roleOptions = availableRoles.map(r => {{
                    const colorStyle = r.color ? `style="color: ${{colorToHex(r.color)}}"` : '';
                    return `<option value="${{r.id}}" ${{colorStyle}}>@${{r.name}}</option>`;
                }}).join('');
                roleSelectHtml = `
                    <select class="role-select w-full px-3 py-2 bg-gray-600 border border-gray-500 rounded
                                   focus:outline-none focus:ring-2 focus:ring-blue-500
                                   text-gray-100 text-sm" required>
                        <option value="">-- Select Role --</option>
                        ${{roleOptions}}
                    </select>
                `;
            }}

            row.innerHTML = `
                <div class="drag-handle flex items-center justify-center w-8 cursor-grab active:cursor-grabbing text-gray-400 hover:text-gray-200" title="Drag to reorder">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8h16M4 16h16" />
                    </svg>
                </div>
                <input type="hidden" name="item_position[]" class="position-input" value="${{index}}">
                <div class="flex-1 min-w-[80px]">
                    <label class="block text-xs font-medium mb-1 text-gray-300">
                        Emoji <span class="text-red-400">*</span>
                    </label>
                    <input
                        type="text"
                        name="item_emoji[]"
                        required
                        maxlength="64"
                        class="w-full px-3 py-2 bg-gray-600 border border-gray-500 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100 text-sm"
                        placeholder="🎮"
                    >
                </div>
                <div class="flex-[2] min-w-[160px]">
                    <label class="block text-xs font-medium mb-1 text-gray-300">
                        Role <span class="text-red-400">*</span>
                    </label>
                    ${{roleSelectHtml}}
                    <input
                        type="hidden"
                        name="item_role_id[]"
                        class="role-id-input"
                    >
                </div>
                <div class="label-field flex-[2] min-w-[120px]">
                    <label class="block text-xs font-medium mb-1 text-gray-300">
                        Label
                    </label>
                    <input
                        type="text"
                        name="item_label[]"
                        maxlength="80"
                        class="w-full px-3 py-2 bg-gray-600 border border-gray-500 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100 text-sm"
                        placeholder="Gamer"
                    >
                </div>
                <div>
                    <button
                        type="button"
                        class="remove-role-item bg-red-600 hover:bg-red-700 text-white
                               py-2 px-3 rounded transition-colors text-sm"
                        title="Remove"
                    >
                        &times;
                    </button>
                </div>
            `;

            // ロールセレクト変更時のイベント
            const roleSelect = row.querySelector('.role-select');
            const roleIdInput = row.querySelector('.role-id-input');
            if (roleSelect) {{
                roleSelect.addEventListener('change', function() {{
                    roleIdInput.value = this.value;
                }});
            }}

            return row;
        }}

        addRoleItemBtn.addEventListener('click', function() {{
            const row = createRoleItemRow(roleItemIndex++);
            roleItemsContainer.appendChild(row);
            updateSubmitButton();
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
            const labelFields = document.querySelectorAll('.label-field');
            labelFields.forEach(field => {{
                field.style.display = showLabel ? '' : 'none';
            }});
        }}

        // panel_type が変更されたときにラベルフィールドの表示を更新
        document.querySelectorAll('input[name="panel_type"]').forEach(radio => {{
            radio.addEventListener('change', updateLabelFieldsVisibility);
        }});

        // 初期状態を設定
        updateSubmitButton();
        updateRolesInfo();
        updateLabelFieldsVisibility();
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

    # ロールID -> ロール情報のマップを作成
    role_info_map: dict[str, tuple[str, int]] = {
        r[0]: (r[1], r[2]) for r in discord_roles
    }

    # ボタン式の場合のみラベルを表示
    is_button_type = panel.panel_type == "button"

    # Build items table
    items_rows = ""
    for item in items:
        label_display = escape(item.label) if item.label else "(no label)"
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
            f'<td class="py-3 px-4">{label_display}</td>' if is_button_type else ""
        )
        items_rows += f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 text-xl">{escape(item.emoji)}</td>
            <td class="py-3 px-4">{role_id_display}</td>
            {label_cell}
            <td class="py-3 px-4">{item.position}</td>
            <td class="py-3 px-4">
                <form method="POST" action="/rolepanels/{panel.id}/items/{item.id}/delete"
                      onsubmit="return confirm('Delete this role item?');">
                    <button type="submit"
                            class="text-red-400 hover:text-red-300 text-sm">
                        Delete
                    </button>
                </form>
            </td>
        </tr>
        """

    col_count = 5 if is_button_type else 4
    if not items:
        items_rows = f"""
        <tr>
            <td colspan="{col_count}" class="py-8 text-center text-gray-500">
                No roles configured. Add roles below.
            </td>
        </tr>
        """

    # Next position for new item
    next_position = max((item.position for item in items), default=-1) + 1

    content = f"""
    <div class="p-6">
        {_nav(f"Panel: {escape(panel.title)}")}

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
            </div>
            <div class="mt-4">
                <span class="text-gray-400">Description:</span>
                <p class="mt-1">{escape(panel.description or "(no description)")}</p>
            </div>
        </div>

        <!-- Role Items -->
        <div class="bg-gray-800 p-6 rounded-lg mb-6">
            <h2 class="text-lg font-semibold mb-4">Role Items ({len(items)})</h2>
            <div class="overflow-x-auto">
                <table class="w-full">
                    <thead class="bg-gray-700">
                        <tr>
                            <th class="py-3 px-4 text-left">Emoji</th>
                            <th class="py-3 px-4 text-left">Role</th>
                            {
        "" if not is_button_type else '<th class="py-3 px-4 text-left">Label</th>'
    }
                            <th class="py-3 px-4 text-left">Position</th>
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
        else f'''
                        <select
                            id="role_select"
                            class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                                   focus:outline-none focus:ring-2 focus:ring-blue-500
                                   text-gray-100"
                            required
                        >
                            <option value="">-- Select Role --</option>
                            {"".join(f'<option value="{escape(r[0])}" style="color: #{r[2] if r[2] else 0x99AAB5:06x}">@{escape(r[1])}</option>' for r in discord_roles)}
                        </select>
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
                    </div>'''
        if is_button_type
        else ""
    }
                    <div>
                        <label for="position" class="block text-sm font-medium mb-2">
                            Position
                        </label>
                        <input
                            type="number"
                            id="position"
                            name="position"
                            value="{next_position}"
                            min="0"
                            class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                                   focus:outline-none focus:ring-2 focus:ring-blue-500
                                   text-gray-100"
                        >
                    </div>
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

        <div class="mt-6">
            <a href="/rolepanels" class="text-gray-400 hover:text-white text-sm">
                &larr; Back to role panels
            </a>
        </div>
    </div>
    {
        ""
        if not discord_roles
        else '''
    <script>
    (function() {
        const roleSelect = document.getElementById("role_select");
        const roleIdInput = document.getElementById("role_id");

        if (roleSelect) {
            roleSelect.addEventListener("change", function() {
                roleIdInput.value = this.value;
            });
        }
    })();
    </script>
    '''
    }
    """
    return _base(f"Panel: {panel.title}", content)
