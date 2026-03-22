"""Settings and dashboard page templates."""

from html import escape

from src.web.templates._common import _base, _csrf_field, _nav


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
            <a href="/automod" class="bg-gray-800 p-6 rounded-lg hover:bg-gray-750 transition-colors">
                <h2 class="text-lg font-semibold mb-2">AutoMod</h2>
                <p class="text-gray-400 text-sm">Manage automod rules and logs</p>
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
            <a href="/eventlog" class="bg-gray-800 p-6 rounded-lg hover:bg-gray-750 transition-colors">
                <h2 class="text-lg font-semibold mb-2">Event Log</h2>
                <p class="text-gray-400 text-sm">Configure event logging channels</p>
            </a>
            <a href="/health/settings" class="bg-gray-800 p-6 rounded-lg hover:bg-gray-750 transition-colors">
                <h2 class="text-lg font-semibold mb-2">Health Monitor</h2>
                <p class="text-gray-400 text-sm">Configure heartbeat notification channels</p>
            </a>
        </div>
    </div>
    """
    return _base("Dashboard", content)


def settings_page(
    current_email: str,
    pending_email: str | None = None,
    timezone_offset: int = 9,
    csrf_token: str = "",
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

    sign = "+" if timezone_offset >= 0 else ""

    content = f"""
    <div class="p-6">
        {_nav("Settings", show_dashboard_link=True)}
        <div class="max-w-md">
            {pending_email_html}
            <div class="space-y-4">
                <div class="bg-gray-800 p-6 rounded-lg">
                    <h2 class="text-lg font-semibold mb-4">Timezone</h2>
                    <form method="post" action="/settings/timezone">
                        <input type="hidden" name="csrf_token" value="{csrf_token}">
                        <div class="flex items-center gap-3">
                            <label class="text-gray-400 text-sm whitespace-nowrap">UTC offset (hours)</label>
                            <input type="number" name="timezone_offset"
                                   value="{timezone_offset}" min="-12" max="14"
                                   class="bg-gray-700 text-white px-3 py-2 rounded w-24
                                          border border-gray-600 focus:border-blue-500 focus:outline-none">
                            <span class="text-gray-400 text-sm">UTC{sign}{timezone_offset}</span>
                            <button type="submit"
                                    class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded
                                           transition-colors text-sm">
                                Save
                            </button>
                        </div>
                    </form>
                </div>
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
