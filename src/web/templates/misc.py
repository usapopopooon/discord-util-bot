"""Miscellaneous page templates (activity, health, eventlog)."""

from html import escape
from typing import TYPE_CHECKING

from src.utils import format_datetime
from src.web.templates._common import _base, _csrf_field, _nav

if TYPE_CHECKING:
    from src.database.models import EventLogConfig


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


def health_settings_page(
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
    configs_map: dict[str, str] | None = None,
    csrf_token: str = "",
) -> str:
    """Health monitor settings page template."""
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
    configs_json = json_mod.dumps(configs_map)

    # 既存設定テーブル
    configs_rows = ""
    for gid, ch_id in configs_map.items():
        gname = guilds_map.get(gid, gid)
        ch_name = ch_id
        for cid, cname in channels_map.get(gid, []):
            if cid == ch_id:
                ch_name = f"#{cname}"
                break
        configs_rows += f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4">{escape(gname)}</td>
            <td class="py-3 px-4">{escape(ch_name)}</td>
            <td class="py-3 px-4">
                <form method="POST" action="/health/settings/{escape(gid)}/delete" class="inline">
                    {_csrf_field(csrf_token)}
                    <button type="submit" class="text-red-400 hover:text-red-300">Delete</button>
                </form>
            </td>
        </tr>
        """

    configs_table = ""
    if configs_rows:
        configs_table = f"""
        <div class="mb-8">
            <h2 class="text-lg font-semibold mb-4">Configured Guilds</h2>
            <table class="w-full">
                <thead>
                    <tr class="text-left text-gray-400 border-b border-gray-600">
                        <th class="py-2 px-4">Server</th>
                        <th class="py-2 px-4">Channel</th>
                        <th class="py-2 px-4">Actions</th>
                    </tr>
                </thead>
                <tbody>{configs_rows}</tbody>
            </table>
        </div>
        """

    content = f"""
    <div class="p-6">
        {_nav("Health Monitor", breadcrumbs=[("Dashboard", "/dashboard"), ("Health Monitor", None)])}
        {configs_table}
        <div class="max-w-2xl">
            <h2 class="text-lg font-semibold mb-4">Add / Update Configuration</h2>
            <form method="POST" action="/health/settings" class="space-y-6">
                {_csrf_field(csrf_token)}
                <div>
                    <label class="block text-sm font-medium mb-1">Server</label>
                    <select name="guild_id" required id="healthGuildSelect"
                            onchange="updateHealthChannel()"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="">Select server...</option>
                        {guild_options}
                    </select>
                </div>
                <div>
                    <label class="block text-sm font-medium mb-1">
                        Notification Channel
                        <span class="text-gray-400 font-normal">(Heartbeat / Deploy destination)</span>
                    </label>
                    <select name="channel_id" id="healthChannelSelect" required
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="">Select channel...</option>
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
    const healthChannelsData = {channels_json};
    const healthConfigsData = {configs_json};
    function updateHealthChannel() {{
        const guildId = document.getElementById('healthGuildSelect').value;
        const chSelect = document.getElementById('healthChannelSelect');
        chSelect.innerHTML = '<option value="">Select channel...</option>';
        if (healthChannelsData[guildId]) {{
            healthChannelsData[guildId].forEach(ch => {{
                const opt = document.createElement('option');
                opt.value = ch.id;
                opt.textContent = '#' + ch.name;
                chSelect.appendChild(opt);
            }});
        }}
        if (healthConfigsData[guildId]) {{
            chSelect.value = healthConfigsData[guildId];
        }}
    }}
    </script>
    """
    return _base("Health Monitor", content)


def eventlog_page(
    configs: list["EventLogConfig"],
    csrf_token: str = "",
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
) -> str:
    """Event Log 設定一覧＋新規作成ページ。"""
    import json as json_mod

    if guilds_map is None:
        guilds_map = {}
    if channels_map is None:
        channels_map = {}

    # イベントタイプの表示名
    event_type_labels = {
        "message_delete": "Message Delete",
        "message_edit": "Message Edit",
        "member_join": "Member Join",
        "member_leave": "Member Leave",
        "member_kick": "Member Kick",
        "member_ban": "Member Ban",
        "member_unban": "Member Unban",
        "member_timeout": "Member Timeout",
        "role_change": "Role Change",
        "nickname_change": "Nickname Change",
        "channel_create": "Channel Create",
        "channel_delete": "Channel Delete",
        "voice_state": "Voice State",
    }

    # チャンネル名マップ (全ギルドのチャンネルをフラット化)
    channel_name_map: dict[str, str] = {}
    for ch_list in channels_map.values():
        for cid, cname in ch_list:
            channel_name_map[cid] = cname

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

        event_label = event_type_labels.get(config.event_type, config.event_type)
        ch_name = channel_name_map.get(config.channel_id, config.channel_id)

        status = "Enabled" if config.enabled else "Disabled"
        status_class = "text-green-400" if config.enabled else "text-gray-500"
        created = format_datetime(config.created_at)

        row_parts.append(f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 align-middle">{guild_display}</td>
            <td class="py-3 px-4 align-middle">{escape(event_label)}</td>
            <td class="py-3 px-4 align-middle">#{escape(ch_name)}</td>
            <td class="py-3 px-4 align-middle">
                <span class="{status_class}">{status}</span>
            </td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">{created}</td>
            <td class="py-3 px-4 align-middle space-x-2">
                <a href="#" onclick="postAction('/eventlog/{config.id}/toggle', '{csrf_token}'); return false;"
                   class="text-blue-400 hover:text-blue-300 text-sm">Toggle</a>
                <a href="#" onclick="postAction('/eventlog/{config.id}/delete', '{csrf_token}', 'Delete this event log config?'); return false;"
                   class="text-red-400 hover:text-red-300 text-sm">Delete</a>
            </td>
        </tr>
        """)
    rows = "".join(row_parts)

    if not configs:
        rows = """
        <tr>
            <td colspan="6" class="py-8 text-center text-gray-500">
                No event log configs configured
            </td>
        </tr>
        """

    # ギルド選択肢
    guild_options = "".join(
        f'<option value="{escape(gid)}">{escape(gname)}</option>'
        for gid, gname in guilds_map.items()
    )

    # イベントタイプ選択肢
    event_options = "".join(
        f'<option value="{escape(k)}">{escape(v)}</option>'
        for k, v in event_type_labels.items()
    )

    # チャンネル情報を JSON 化 (JS で guild 選択時にフィルタ)
    channels_data: dict[str, list[dict[str, str]]] = {}
    for gid, ch_list in channels_map.items():
        channels_data[gid] = [{"id": cid, "name": cname} for cid, cname in ch_list]
    channels_json = json_mod.dumps(channels_data)

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Event Log",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Event Log", None),
            ],
        )
    }
        <div class="bg-gray-800 rounded-lg overflow-hidden overflow-x-auto mb-6">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="py-3 px-4 text-left">Server</th>
                        <th class="py-3 px-4 text-left">Event Type</th>
                        <th class="py-3 px-4 text-left">Channel</th>
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
            <h2 class="text-lg font-semibold mb-4">Add Event Log Config</h2>
            <form method="POST" action="/eventlog/new">
                {_csrf_field(csrf_token)}
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Server</label>
                        <select name="guild_id" id="eventlogGuildSelect" onchange="updateEventlogChannel()"
                                class="w-full bg-gray-700 rounded px-3 py-2 text-sm" required>
                            <option value="">Select server...</option>
                            {guild_options}
                        </select>
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Event Type</label>
                        <select name="event_type" id="eventlogEventType"
                                class="w-full bg-gray-700 rounded px-3 py-2 text-sm" required>
                            <option value="">Select event type...</option>
                            {event_options}
                        </select>
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Channel</label>
                        <select name="channel_id" id="eventlogChannelSelect"
                                class="w-full bg-gray-700 rounded px-3 py-2 text-sm" required>
                            <option value="">Select channel...</option>
                        </select>
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
    const eventlogChannelsData = {channels_json};
    function updateEventlogChannel() {{
        const guildId = document.getElementById('eventlogGuildSelect').value;
        const chSelect = document.getElementById('eventlogChannelSelect');
        chSelect.innerHTML = '<option value="">Select channel...</option>';
        if (eventlogChannelsData[guildId]) {{
            eventlogChannelsData[guildId].forEach(ch => {{
                const opt = document.createElement('option');
                opt.value = ch.id;
                opt.textContent = '#' + ch.name;
                chSelect.appendChild(opt);
            }});
        }}
    }}
    </script>
    """
    return _base("Event Log", content)
