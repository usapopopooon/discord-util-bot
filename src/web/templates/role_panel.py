"""Role panel page templates."""

from html import escape
from typing import TYPE_CHECKING

from src.utils import format_datetime
from src.web.templates._common import (
    _base,
    _csrf_field,
    _get_emoji_json,
    _nav,
    _roles_to_js_array,
)

if TYPE_CHECKING:
    from src.database.models import RolePanel, RolePanelItem


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
                    <div class="emoji-autocomplete relative">
                        <input
                            type="text"
                            name="item_emoji[]"
                            required
                            maxlength="64"
                            class="emoji-input w-full px-2 py-1 bg-gray-600 border border-gray-500 rounded
                                   focus:outline-none focus:ring-2 focus:ring-blue-500
                                   text-gray-100 text-sm"
                            placeholder="\U0001f3ae or type name"
                            autocomplete="off"
                        >
                        <div class="emoji-dropdown absolute z-50 w-full mt-1 bg-gray-700 border border-gray-500
                                    rounded shadow-lg max-h-48 overflow-y-auto hidden"></div>
                    </div>
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

            // 絵文字オートコンプリートのイベント設定
            const emojiInputEl = row.querySelector('.emoji-input');
            if (emojiInputEl) setupEmojiAutocomplete(emojiInputEl);

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

        // 絵文字オートコンプリートのデータとセットアップ
        const EMOJI_DATA = {_get_emoji_json()};

        function setupEmojiAutocomplete(input) {{
            const dropdown = input.nextElementSibling;
            if (!dropdown) return;
            let selectedIndex = -1;

            input.addEventListener('input', function() {{
                const query = input.value.trim().toLowerCase();
                if (!query || /^[\\p{{Emoji_Presentation}}\\p{{Extended_Pictographic}}]/u.test(query) || query.startsWith('<:') || query.startsWith('<a:')) {{
                    dropdown.classList.add('hidden');
                    return;
                }}
                const matches = EMOJI_DATA.filter(function(item) {{ return item[0].includes(query); }}).slice(0, 8);
                if (matches.length === 0) {{
                    dropdown.classList.add('hidden');
                    return;
                }}
                selectedIndex = -1;
                dropdown.innerHTML = matches.map(function(item, i) {{
                    return '<div class="emoji-option px-3 py-2 hover:bg-gray-600 cursor-pointer text-sm" data-emoji="' + item[1] + '">' +
                        '<span class="text-lg mr-2">' + item[1] + '</span> ' + escapeHtml(item[0]) +
                        '</div>';
                }}).join('');
                dropdown.classList.remove('hidden');
            }});

            dropdown.addEventListener('click', function(e) {{
                const option = e.target.closest('.emoji-option');
                if (option) {{
                    input.value = option.dataset.emoji;
                    dropdown.classList.add('hidden');
                }}
            }});

            input.addEventListener('keydown', function(e) {{
                const options = dropdown.querySelectorAll('.emoji-option');
                if (options.length === 0 || dropdown.classList.contains('hidden')) return;
                if (e.key === 'ArrowDown') {{
                    e.preventDefault();
                    selectedIndex = Math.min(selectedIndex + 1, options.length - 1);
                    options.forEach(function(opt, i) {{ opt.classList.toggle('bg-gray-600', i === selectedIndex); }});
                }} else if (e.key === 'ArrowUp') {{
                    e.preventDefault();
                    selectedIndex = Math.max(selectedIndex - 1, 0);
                    options.forEach(function(opt, i) {{ opt.classList.toggle('bg-gray-600', i === selectedIndex); }});
                }} else if (e.key === 'Enter' && selectedIndex >= 0) {{
                    e.preventDefault();
                    input.value = options[selectedIndex].dataset.emoji;
                    dropdown.classList.add('hidden');
                }} else if (e.key === 'Escape') {{
                    dropdown.classList.add('hidden');
                }}
            }});

            input.addEventListener('blur', function() {{
                setTimeout(function() {{ dropdown.classList.add('hidden'); }}, 200);
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
                    <span class="text-green-400 font-medium">\u2713 Posted to Discord</span>
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
                        <div class="emoji-autocomplete relative">
                            <input
                                type="text"
                                id="emoji"
                                name="emoji"
                                required
                                maxlength="64"
                                class="emoji-input w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                                       focus:outline-none focus:ring-2 focus:ring-blue-500
                                       text-gray-100"
                                placeholder="\U0001f3ae or type name"
                                autocomplete="off"
                            >
                            <div class="emoji-dropdown absolute z-50 w-full mt-1 bg-gray-700 border border-gray-600
                                        rounded shadow-lg max-h-48 overflow-y-auto hidden"></div>
                        </div>
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
        const EMOJI_DATA = {_get_emoji_json()};

        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}

        function setupEmojiAutocomplete(input) {{
            const dropdown = input.nextElementSibling;
            if (!dropdown) return;
            let selectedIndex = -1;

            input.addEventListener('input', function() {{
                const query = input.value.trim().toLowerCase();
                if (!query || /^[\\p{{Emoji_Presentation}}\\p{{Extended_Pictographic}}]/u.test(query) || query.startsWith('<:') || query.startsWith('<a:')) {{
                    dropdown.classList.add('hidden');
                    return;
                }}
                const matches = EMOJI_DATA.filter(function(item) {{ return item[0].includes(query); }}).slice(0, 8);
                if (matches.length === 0) {{
                    dropdown.classList.add('hidden');
                    return;
                }}
                selectedIndex = -1;
                dropdown.innerHTML = matches.map(function(item, i) {{
                    return '<div class="emoji-option px-3 py-2 hover:bg-gray-600 cursor-pointer text-sm" data-emoji="' + item[1] + '">' +
                        '<span class="text-lg mr-2">' + item[1] + '</span> ' + escapeHtml(item[0]) +
                        '</div>';
                }}).join('');
                dropdown.classList.remove('hidden');
            }});

            dropdown.addEventListener('click', function(e) {{
                const option = e.target.closest('.emoji-option');
                if (option) {{
                    input.value = option.dataset.emoji;
                    dropdown.classList.add('hidden');
                }}
            }});

            input.addEventListener('keydown', function(e) {{
                const options = dropdown.querySelectorAll('.emoji-option');
                if (options.length === 0 || dropdown.classList.contains('hidden')) return;
                if (e.key === 'ArrowDown') {{
                    e.preventDefault();
                    selectedIndex = Math.min(selectedIndex + 1, options.length - 1);
                    options.forEach(function(opt, i) {{ opt.classList.toggle('bg-gray-600', i === selectedIndex); }});
                }} else if (e.key === 'ArrowUp') {{
                    e.preventDefault();
                    selectedIndex = Math.max(selectedIndex - 1, 0);
                    options.forEach(function(opt, i) {{ opt.classList.toggle('bg-gray-600', i === selectedIndex); }});
                }} else if (e.key === 'Enter' && selectedIndex >= 0) {{
                    e.preventDefault();
                    input.value = options[selectedIndex].dataset.emoji;
                    dropdown.classList.add('hidden');
                }} else if (e.key === 'Escape') {{
                    dropdown.classList.add('hidden');
                }}
            }});

            input.addEventListener('blur', function() {{
                setTimeout(function() {{ dropdown.classList.add('hidden'); }}, 200);
            }});
        }}

        document.querySelectorAll('.emoji-input').forEach(setupEmojiAutocomplete);
    }})();
    </script>
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
