"""Sticky message page templates."""

from html import escape
from typing import TYPE_CHECKING

from src.web.templates._common import _base, _nav

if TYPE_CHECKING:
    from src.database.models import StickyMessage


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
