"""AutoMod page templates."""

from html import escape
from typing import TYPE_CHECKING

from src.utils import format_datetime
from src.web.templates._common import _base, _csrf_field, _nav

if TYPE_CHECKING:
    from src.database.models import (
        AutoModBanList,
        AutoModLog,
        AutoModRule,
        BanLog,
    )


def automod_list_page(
    rules: list["AutoModRule"],
    csrf_token: str = "",
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
) -> str:
    """AutoMod rules list page template."""
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
            details = (
                f"{rule.threshold_seconds // 60}min" if rule.threshold_seconds else "-"
            )
        elif rule.rule_type in ("role_acquired", "vc_join", "message_post"):
            details = (
                f"{rule.threshold_seconds}s after join"
                if rule.threshold_seconds
                else "-"
            )
        elif rule.rule_type == "role_count":
            if rule.threshold_seconds and rule.target_role_ids:
                n_targets = len(rule.target_role_ids.split(","))
                details = f"{n_targets}個中{rule.threshold_seconds}個以上で発動"
            elif rule.threshold_seconds:
                details = f">= {rule.threshold_seconds} roles"
            else:
                details = "-"
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

        action_display = escape(rule.action)
        if rule.action == "timeout" and getattr(rule, "timeout_duration_seconds", None):
            action_display += f" ({(rule.timeout_duration_seconds or 0) // 60}min)"

        row_parts.append(f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 align-middle">{guild_display}</td>
            <td class="py-3 px-4 align-middle">{escape(rule.rule_type)}</td>
            <td class="py-3 px-4 align-middle">{action_display}</td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">{details}</td>
            <td class="py-3 px-4 align-middle">
                <span class="{status_class}">{status}</span>
            </td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">{created}</td>
            <td class="py-3 px-4 align-middle space-x-2">
                <a href="/automod/{rule.id}/edit"
                   class="text-blue-400 hover:text-blue-300 text-sm">Edit</a>
                <a href="#" onclick="postAction('/automod/{rule.id}/toggle', '{csrf_token}'); return false;"
                   class="text-blue-400 hover:text-blue-300 text-sm">Toggle</a>
                <a href="#" onclick="postAction('/automod/{rule.id}/delete', '{csrf_token}', 'Delete this automod rule?'); return false;"
                   class="text-red-400 hover:text-red-300 text-sm">Delete</a>
            </td>
        </tr>
        """)
    rows = "".join(row_parts)

    if not rules:
        rows = """
        <tr>
            <td colspan="7" class="py-8 text-center text-gray-500">
                No automod rules configured
            </td>
        </tr>
        """

    content = f"""
    <div class="p-6">
        {
        _nav(
            "AutoMod Rules",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("AutoMod Rules", None),
            ],
        )
    }
        <div class="flex gap-3 mb-4">
            <a href="/automod/new"
               class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm transition-colors">
                + Create Rule
            </a>
            <a href="/automod/logs"
               class="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded text-sm transition-colors">
                View Logs
            </a>
            <a href="/automod/banlist"
               class="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded text-sm transition-colors">
                Ban List
            </a>
            <a href="/automod/settings"
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
    return _base("AutoMod Rules", content)


def automod_create_page(
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
    roles_map: dict[str, list[tuple[str, str, int]]] | None = None,
    csrf_token: str = "",
) -> str:
    """AutoMod rule create page template."""
    import json as json_mod

    if guilds_map is None:
        guilds_map = {}
    if channels_map is None:
        channels_map = {}
    if roles_map is None:
        roles_map = {}

    guild_options = ""
    for gid, gname in sorted(guilds_map.items(), key=lambda x: x[1]):
        guild_options += (
            f'<option value="{escape(gid)}">{escape(gname)} ({escape(gid)})</option>'
        )

    channels_data: dict[str, list[dict[str, str]]] = {}
    for gid, ch_list in channels_map.items():
        channels_data[gid] = [{"id": cid, "name": cname} for cid, cname in ch_list]
    channels_json = json_mod.dumps(channels_data)

    roles_data: dict[str, list[dict[str, str]]] = {}
    for gid, r_list in roles_map.items():
        roles_data[gid] = [{"id": rid, "name": rname} for rid, rname, _c in r_list]
    roles_json = json_mod.dumps(roles_data)

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Create AutoMod Rule",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("AutoMod Rules", "/automod"),
                ("Create", None),
            ],
        )
    }
        <div class="max-w-2xl">
            <form method="POST" action="/automod/new" class="space-y-6">
                {_csrf_field(csrf_token)}

                <div>
                    <label class="block text-sm font-medium mb-1">Server</label>
                    <select name="guild_id" required id="guildSelect"
                            onchange="updateRequiredChannel(); updateTargetRoles()"
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
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="radio" name="rule_type" value="role_count"
                                   onchange="updateRuleFields()">
                            <span>Role Count (任意のロールをN個以上取得で発動)</span>
                        </label>
                    </div>
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">Action</label>
                    <select name="action" id="actionSelect" onchange="updateTimeoutField()"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="ban">Ban</option>
                        <option value="kick">Kick</option>
                        <option value="timeout">Timeout</option>
                    </select>
                </div>

                <div id="timeoutDurationFields" class="hidden">
                    <label class="block text-sm font-medium mb-1">
                        Timeout Duration (min)
                    </label>
                    <input type="number" name="timeout_duration_minutes"
                           min="1" max="40320" placeholder="e.g. 60"
                           class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
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
                        Threshold (minutes, max 20160 = 14 days)
                    </label>
                    <input type="number" name="account_age_minutes"
                           min="1" max="20160" placeholder="e.g. 60"
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

                <div id="roleCountFields" class="hidden">
                    <div class="mb-4">
                        <label class="block text-sm font-medium mb-1">
                            監視対象ロール (チェックしたロールのうちN個以上で発動)
                        </label>
                        <div id="targetRolesContainer"
                             class="max-h-48 overflow-y-auto bg-gray-700 border border-gray-600 rounded p-2 space-y-1">
                            <p class="text-gray-400 text-sm">サーバーを選択してください</p>
                        </div>
                    </div>
                    <label class="block text-sm font-medium mb-1">
                        何個以上取得したら発動するか (1-100)
                    </label>
                    <input type="number" name="role_count"
                           min="1" max="100" placeholder="e.g. 3"
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
    const rolesData = {roles_json};
    function updateRuleFields() {{
        const ruleType = document.querySelector('input[name="rule_type"]:checked').value;
        const usernameFields = document.getElementById('usernameFields');
        const accountAgeFields = document.getElementById('accountAgeFields');
        const thresholdSecondsFields = document.getElementById('thresholdSecondsFields');
        const roleCountFields = document.getElementById('roleCountFields');
        const requiredChannelFields = document.getElementById('requiredChannelFields');
        const introTypes = ['vc_without_intro', 'msg_without_intro'];

        usernameFields.classList.toggle('hidden', ruleType !== 'username_match');
        accountAgeFields.classList.toggle('hidden', ruleType !== 'account_age');
        thresholdSecondsFields.classList.toggle('hidden',
            ruleType !== 'role_acquired' && ruleType !== 'vc_join' && ruleType !== 'message_post');
        roleCountFields.classList.toggle('hidden', ruleType !== 'role_count');
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
    function updateTargetRoles() {{
        const guildId = document.getElementById('guildSelect').value;
        const container = document.getElementById('targetRolesContainer');
        container.innerHTML = '';
        if (rolesData[guildId]) {{
            rolesData[guildId].forEach(role => {{
                const label = document.createElement('label');
                label.className = 'flex items-center gap-2 cursor-pointer text-sm';
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.name = 'target_role_ids';
                cb.value = role.id;
                cb.className = 'rounded bg-gray-600 border-gray-500';
                const span = document.createElement('span');
                span.textContent = role.name;
                label.appendChild(cb);
                label.appendChild(span);
                container.appendChild(label);
            }});
        }} else {{
            container.innerHTML = '<p class="text-gray-400 text-sm">サーバーを選択してください</p>';
        }}
    }}
    function updateTimeoutField() {{
        const action = document.getElementById('actionSelect').value;
        document.getElementById('timeoutDurationFields').classList.toggle('hidden', action !== 'timeout');
    }}
    </script>
    """
    return _base("Create AutoMod Rule", content)


def automod_edit_page(
    rule: "AutoModRule",
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
    roles_map: dict[str, list[tuple[str, str, int]]] | None = None,
    csrf_token: str = "",
) -> str:
    """AutoMod rule edit page template."""
    if guilds_map is None:
        guilds_map = {}
    if channels_map is None:
        channels_map = {}

    guild_name = guilds_map.get(rule.guild_id, rule.guild_id)
    guild_display = f"{escape(guild_name)} ({escape(rule.guild_id)})"

    ban_selected = " selected" if rule.action == "ban" else ""
    kick_selected = " selected" if rule.action == "kick" else ""
    timeout_selected = " selected" if rule.action == "timeout" else ""
    timeout_duration_val = (
        (rule.timeout_duration_seconds or 0) // 60
        if getattr(rule, "timeout_duration_seconds", None)
        else ""
    )
    timeout_hidden = "" if rule.action == "timeout" else " hidden"

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
        val = rule.threshold_seconds // 60 if rule.threshold_seconds else ""
        type_fields = f"""
                <div>
                    <label class="block text-sm font-medium mb-1">
                        Threshold (minutes, max 20160 = 14 days)
                    </label>
                    <input type="number" name="account_age_minutes"
                           min="1" max="20160" value="{val}"
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
    elif rule.rule_type == "role_count":
        val = rule.threshold_seconds or ""
        existing_ids = set((rule.target_role_ids or "").split(","))
        guild_roles = (roles_map or {}).get(rule.guild_id, [])
        role_checkboxes = ""
        for rid, rname, _c in guild_roles:
            checked = " checked" if rid in existing_ids else ""
            role_checkboxes += (
                f'<label class="flex items-center gap-2 cursor-pointer text-sm">'
                f'<input type="checkbox" name="target_role_ids" value="{escape(rid)}"{checked}'
                f' class="rounded bg-gray-600 border-gray-500">'
                f"<span>{escape(rname)}</span></label>"
            )
        if not role_checkboxes:
            role_checkboxes = (
                '<p class="text-gray-400 text-sm">ロールが見つかりません</p>'
            )
        type_fields = f"""
                <div class="mb-4">
                    <label class="block text-sm font-medium mb-1">
                        監視対象ロール (チェックしたロールのうちN個以上で発動)
                    </label>
                    <div class="max-h-48 overflow-y-auto bg-gray-700 border border-gray-600 rounded p-2 space-y-1">
                        {role_checkboxes}
                    </div>
                </div>
                <div>
                    <label class="block text-sm font-medium mb-1">
                        何個以上取得したら発動するか (1-100)
                    </label>
                    <input type="number" name="role_count"
                           min="1" max="100" value="{val}"
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
        "role_count": "Role Count (任意のロールをN個以上取得で発動)",
    }
    rule_type_label = type_labels.get(rule.rule_type, rule.rule_type)

    content = f"""
    <div class="p-6">
        {
        _nav(
            f"Edit AutoMod Rule #{rule.id}",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("AutoMod Rules", "/automod"),
                (f"Edit #{rule.id}", None),
            ],
        )
    }
        <div class="max-w-2xl">
            <form method="POST" action="/automod/{rule.id}/edit" class="space-y-6">
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
                    <select name="action" id="actionSelect" onchange="updateTimeoutField()"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="ban"{ban_selected}>Ban</option>
                        <option value="kick"{kick_selected}>Kick</option>
                        <option value="timeout"{timeout_selected}>Timeout</option>
                    </select>
                </div>

                <div id="timeoutDurationFields" class="{timeout_hidden}">
                    <label class="block text-sm font-medium mb-1">
                        Timeout Duration (min)
                    </label>
                    <input type="number" name="timeout_duration_minutes"
                           min="1" max="40320" value="{timeout_duration_val}"
                           class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                </div>

                {type_fields}

                <div class="flex gap-3">
                    <button type="submit"
                            class="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded transition-colors">
                        Save Changes
                    </button>
                    <a href="/automod"
                       class="bg-gray-600 hover:bg-gray-700 px-6 py-2 rounded transition-colors">
                        Cancel
                    </a>
                </div>
            </form>
        </div>
    </div>

    <script>
    function updateTimeoutField() {{
        const action = document.getElementById('actionSelect').value;
        document.getElementById('timeoutDurationFields').classList.toggle('hidden', action !== 'timeout');
    }}
    </script>
    """
    return _base(f"Edit AutoMod Rule #{rule.id}", content)


def automod_logs_page(
    logs: list["AutoModLog"],
    guilds_map: dict[str, str] | None = None,
) -> str:
    """AutoMod logs page template."""
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
                No automod logs
            </td>
        </tr>
        """

    content = f"""
    <div class="p-6">
        {
        _nav(
            "AutoMod Logs",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("AutoMod Rules", "/automod"),
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
    return _base("AutoMod Logs", content)


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
        if log.is_automod:
            source_html = '<span class="bg-red-600 text-white text-xs px-2 py-0.5 rounded">AutoMod</span>'
        else:
            source_html = '<span class="bg-gray-600 text-gray-300 text-xs px-2 py-0.5 rounded">Manual</span>'

        # Reason display: strip [AutoMod] prefix if present
        reason_display = log.reason or "-"
        if reason_display.startswith("[AutoMod] "):
            reason_display = reason_display[len("[AutoMod] ") :]

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


def automod_settings_page(
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
    configs_map: dict[str, str | None] | None = None,
    intro_check_map: dict[str, int] | None = None,
    csrf_token: str = "",
) -> str:
    """AutoMod settings page template."""
    import json as json_mod

    if guilds_map is None:
        guilds_map = {}
    if channels_map is None:
        channels_map = {}
    if configs_map is None:
        configs_map = {}
    if intro_check_map is None:
        intro_check_map = {}

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

    intro_check_json = json_mod.dumps(intro_check_map)

    content = f"""
    <div class="p-6">
        {
        _nav(
            "AutoMod Settings",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("AutoMod Rules", "/automod"),
                ("Settings", None),
            ],
        )
    }
        <div class="max-w-2xl">
            <form method="POST" action="/automod/settings" class="space-y-6">
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

                <div>
                    <label class="block text-sm font-medium mb-1">
                        Intro Check Messages
                        <span class="text-gray-400 font-normal">
                            (DB に記録がない場合にチャンネル履歴を何件チェックするか。0 で無効)
                        </span>
                    </label>
                    <input type="number" name="intro_check_messages" id="introCheckInput"
                           value="50" min="0" max="200"
                           class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
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
    const introCheckData = {intro_check_json};
    function updateLogChannel() {{
        const guildId = document.getElementById('guildSelect').value;
        const logSelect = document.getElementById('logChannelSelect');
        const introInput = document.getElementById('introCheckInput');
        logSelect.innerHTML = '<option value="">None (disabled)</option>';
        if (channelsData[guildId]) {{
            channelsData[guildId].forEach(ch => {{
                const opt = document.createElement('option');
                opt.value = ch.id;
                opt.textContent = '#' + ch.name;
                logSelect.appendChild(opt);
            }});
        }}
        // Restore saved values
        if (configsData[guildId]) {{
            logSelect.value = configsData[guildId];
        }}
        introInput.value = (introCheckData[guildId] !== undefined)
            ? introCheckData[guildId] : 50;
    }}
    </script>
    """
    return _base("AutoMod Settings", content)


def automod_banlist_page(
    entries: list["AutoModBanList"],
    guilds_map: dict[str, str] | None = None,
    csrf_token: str = "",
) -> str:
    """AutoMod ban list page template."""
    if guilds_map is None:
        guilds_map = {}

    # Guild options for dropdown
    guild_options = ""
    for gid, gname in guilds_map.items():
        guild_options += f'<option value="{escape(gid)}">{escape(gname)}</option>\n'

    # Table rows
    row_parts: list[str] = []
    for entry in entries:
        guild_name = guilds_map.get(entry.guild_id)
        if guild_name:
            guild_display = f'<span class="font-medium">{escape(guild_name)}</span>'
        else:
            guild_display = (
                f'<span class="text-yellow-400">{escape(entry.guild_id)}</span>'
            )

        created = format_datetime(entry.created_at)
        reason_display = (
            escape(entry.reason)
            if entry.reason
            else ('<span class="text-gray-500">-</span>')
        )

        row_parts.append(f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 align-middle">{guild_display}</td>
            <td class="py-3 px-4 align-middle font-mono text-sm">
                {escape(entry.user_id)}
            </td>
            <td class="py-3 px-4 align-middle">{reason_display}</td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">
                {created}
            </td>
            <td class="py-3 px-4 align-middle">
                <form method="POST"
                      action="/automod/banlist/{entry.id}/delete"
                      style="display:inline">
                    {_csrf_field(csrf_token)}
                    <button type="submit"
                            class="text-red-400 hover:text-red-300 text-sm"
                            onclick="return confirm('Delete?')">
                        Delete
                    </button>
                </form>
            </td>
        </tr>
        """)

    rows_html = (
        "\n".join(row_parts)
        if row_parts
        else """
        <tr>
            <td colspan="5" class="py-8 text-center text-gray-400">
                No entries in ban list
            </td>
        </tr>
    """
    )

    content = f"""
    {
        _nav(
            "AutoMod Ban List",
            breadcrumbs=[
                ("AutoMod Rules", "/automod"),
                ("Ban List", None),
            ],
        )
    }
    <div class="bg-gray-800 rounded-lg p-6 mb-6">
        <h3 class="text-lg font-medium mb-4">Add User ID to Ban List</h3>
        <form method="POST" action="/automod/banlist" class="space-y-4">
            {_csrf_field(csrf_token)}
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                    <label class="block text-sm font-medium mb-1">
                        Server
                    </label>
                    <select name="guild_id" required
                            class="w-full bg-gray-700 border border-gray-600
                                   rounded px-3 py-2 text-gray-100">
                        <option value="">-- Select --</option>
                        {guild_options}
                    </select>
                </div>
                <div>
                    <label class="block text-sm font-medium mb-1">
                        User ID
                    </label>
                    <input type="text" name="user_id" required
                           pattern="[0-9]+"
                           title="Discord User ID (numbers only)"
                           placeholder="123456789012345678"
                           class="w-full bg-gray-700 border border-gray-600
                                  rounded px-3 py-2 text-gray-100">
                </div>
                <div>
                    <label class="block text-sm font-medium mb-1">
                        Reason (optional)
                    </label>
                    <input type="text" name="reason"
                           placeholder="Reason for ban"
                           class="w-full bg-gray-700 border border-gray-600
                                  rounded px-3 py-2 text-gray-100">
                </div>
            </div>
            <button type="submit"
                    class="bg-red-600 hover:bg-red-700 px-4 py-2
                           rounded text-sm transition-colors">
                + Add to Ban List
            </button>
        </form>
    </div>
    <div class="bg-gray-800 rounded-lg overflow-hidden overflow-x-auto">
        <table class="w-full">
            <thead class="bg-gray-700">
                <tr>
                    <th class="py-3 px-4 text-left text-sm">Server</th>
                    <th class="py-3 px-4 text-left text-sm">User ID</th>
                    <th class="py-3 px-4 text-left text-sm">Reason</th>
                    <th class="py-3 px-4 text-left text-sm">Created</th>
                    <th class="py-3 px-4 text-left text-sm">Actions</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </div>
    """
    return _base("AutoMod Ban List", content)
