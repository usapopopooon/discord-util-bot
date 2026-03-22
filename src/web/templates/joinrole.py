"""Join Role page templates."""

from html import escape
from typing import TYPE_CHECKING

from src.utils import format_datetime
from src.web.templates._common import _base, _csrf_field, _nav

if TYPE_CHECKING:
    from src.database.models import JoinRoleConfig


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
