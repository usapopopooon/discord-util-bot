"""Lobby page templates."""

from html import escape
from typing import TYPE_CHECKING

from src.web.templates._common import _base, _nav

if TYPE_CHECKING:
    from src.database.models import Lobby


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
