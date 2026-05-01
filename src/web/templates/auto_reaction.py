"""Auto Reaction page templates."""

import json
from html import escape
from typing import TYPE_CHECKING

from src.services.auto_reaction_service import decode_auto_reaction_emojis
from src.utils import format_datetime
from src.web.templates._common import _base, _csrf_field, _nav

if TYPE_CHECKING:
    from src.database.models import AutoReactionConfig


def auto_reaction_page(
    configs: list["AutoReactionConfig"],
    csrf_token: str = "",
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
) -> str:
    """AutoReaction 設定一覧＋新規作成ページ。"""
    if guilds_map is None:
        guilds_map = {}
    if channels_map is None:
        channels_map = {}

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

        channel_name = config.channel_id
        for cid, c_name in channels_map.get(config.guild_id, []):
            if cid == config.channel_id:
                channel_name = f"#{c_name}"
                break

        emoji_list = decode_auto_reaction_emojis(config.emojis)
        emoji_display = (
            " ".join(escape(e) for e in emoji_list)
            if emoji_list
            else '<span class="text-gray-500">(none)</span>'
        )

        status = "Enabled" if config.enabled else "Disabled"
        status_class = "text-green-400" if config.enabled else "text-gray-500"
        created = format_datetime(config.created_at)

        row_parts.append(f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 align-middle">{guild_display}</td>
            <td class="py-3 px-4 align-middle">{escape(channel_name)}</td>
            <td class="py-3 px-4 align-middle">{emoji_display}</td>
            <td class="py-3 px-4 align-middle">
                <span class="{status_class}">{status}</span>
            </td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">{created}</td>
            <td class="py-3 px-4 align-middle space-x-2">
                <a href="#" onclick="postAction('/auto-reaction/{config.id}/toggle', '{csrf_token}'); return false;"
                   class="text-blue-400 hover:text-blue-300 text-sm">Toggle</a>
                <a href="#" onclick="postAction('/auto-reaction/{config.id}/delete', '{csrf_token}', 'Delete this auto reaction config?'); return false;"
                   class="text-red-400 hover:text-red-300 text-sm">Delete</a>
            </td>
        </tr>
        """)
    rows = "".join(row_parts)

    if not configs:
        rows = """
        <tr>
            <td colspan="6" class="py-8 text-center text-gray-500">
                No auto reaction configs configured
            </td>
        </tr>
        """

    guild_options = "".join(
        f'<option value="{escape(gid)}">{escape(gname)}</option>'
        for gid, gname in guilds_map.items()
    )

    channels_data: dict[str, list[dict[str, str]]] = {}
    for gid, ch_list in channels_map.items():
        channels_data[gid] = [{"id": cid, "name": name} for cid, name in ch_list]
    channels_json = json.dumps(channels_data)

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Auto Reaction",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Auto Reaction", None),
            ],
        )
    }
        <div class="bg-gray-800 rounded-lg overflow-hidden overflow-x-auto mb-6">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="py-3 px-4 text-left">Server</th>
                        <th class="py-3 px-4 text-left">Channel</th>
                        <th class="py-3 px-4 text-left">Emojis</th>
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
            <h2 class="text-lg font-semibold mb-4">Add Auto Reaction Config</h2>
            <form method="POST" action="/auto-reaction/new">
                {_csrf_field(csrf_token)}
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Server</label>
                        <select name="guild_id" id="autoReactionGuildSelect" onchange="updateAutoReactionSelects()"
                                class="w-full bg-gray-700 rounded px-3 py-2 text-sm" required>
                            <option value="">Select server...</option>
                            {guild_options}
                        </select>
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Channel</label>
                        <select name="channel_id" id="autoReactionChannelSelect"
                                class="w-full bg-gray-700 rounded px-3 py-2 text-sm" required>
                            <option value="">Select channel...</option>
                        </select>
                    </div>
                </div>
                <div class="mb-4">
                    <label class="block text-sm text-gray-400 mb-1">
                        Emojis (space-separated; Unicode 絵文字 または ``&lt;:name:id&gt;``)
                    </label>
                    <input type="text" name="emojis" placeholder="👍 ❤️ &lt;:custom:123456789012345678&gt;"
                           class="w-full bg-gray-700 rounded px-3 py-2 text-sm" required>
                </div>
                <button type="submit"
                        class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm transition-colors">
                    Add Config
                </button>
            </form>
        </div>
    </div>

    <script>
    const autoReactionChannelsData = {channels_json};
    function updateAutoReactionSelects() {{
        const guildId = document.getElementById('autoReactionGuildSelect').value;
        const channelSelect = document.getElementById('autoReactionChannelSelect');
        channelSelect.innerHTML = '<option value="">Select channel...</option>';
        if (autoReactionChannelsData[guildId]) {{
            autoReactionChannelsData[guildId].forEach(ch => {{
                const opt = document.createElement('option');
                opt.value = ch.id;
                opt.textContent = '#' + ch.name;
                channelSelect.appendChild(opt);
            }});
        }}
    }}
    </script>
    """
    return _base("Auto Reaction", content)
