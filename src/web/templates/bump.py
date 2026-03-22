"""Bump reminder page templates."""

from html import escape
from typing import TYPE_CHECKING

from src.utils import format_datetime
from src.web.templates._common import _base, _nav

if TYPE_CHECKING:
    from src.database.models import BumpConfig, BumpReminder


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
