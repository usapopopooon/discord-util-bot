"""Ticket page templates."""

import re
from html import escape
from typing import TYPE_CHECKING

from src.utils import format_datetime
from src.web.templates._common import _base, _csrf_field, _nav

if TYPE_CHECKING:
    from src.database.models import Ticket, TicketPanel, TicketPanelCategory


# --- Discord-like transcript rendering ---

_DISCORD_AVATAR_COLORS = [
    "#5865F2",
    "#57F287",
    "#EB459E",
    "#ED4245",
    "#FAA61A",
    "#9B59B6",
    "#1ABC9C",
    "#E91E63",
    "#3498DB",
    "#2ECC71",
]

_TRANSCRIPT_MSG_RE = re.compile(
    r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (.+?): (.+)$"
)
_TRANSCRIPT_SYS_RE = re.compile(r"^===.*===$")
_TRANSCRIPT_META_RE = re.compile(r"^(Created by|Created at): (.+)$")


def _discord_avatar_color(username: str) -> str:
    """Get a consistent avatar color based on username hash."""
    return _DISCORD_AVATAR_COLORS[hash(username) % len(_DISCORD_AVATAR_COLORS)]


def _format_discord_content(content: str) -> str:
    """Format message content with styled attachments and stickers."""
    att_match = re.search(r"\[Attachments?: (.+?)\]", content)
    stk_match = re.search(r"\[Stickers?: (.+?)\]", content)

    main = content
    if att_match:
        main = main.replace(att_match.group(0), "").strip()
    if stk_match:
        main = main.replace(stk_match.group(0), "").strip()

    parts: list[str] = []
    if main:
        parts.append(escape(main))

    if att_match:
        for url in att_match.group(1).split(", "):
            eu = escape(url.strip())
            parts.append(
                f'<div style="margin-top:4px;">'
                f'<a href="{eu}" target="_blank" rel="noopener" '
                f'style="color:#00a8fc;font-size:13px;">'
                f"\U0001f4ce {eu}</a></div>"
            )

    if stk_match:
        parts.append(
            f'<div style="margin-top:4px;color:#949ba4;font-size:13px;">'
            f"\U0001f3f7\ufe0f {escape(stk_match.group(1))}</div>"
        )

    return "".join(parts) if parts else escape(content)


def _render_discord_transcript(transcript: str) -> str:
    """Render transcript as Discord dark mode chat UI."""
    lines = transcript.split("\n")
    parts: list[str] = []

    parts.append(
        "<style>"
        ".dc-msg:hover{background-color:#2e3035}"
        ".dc-msg .dc-ts{display:none}"
        ".dc-msg:hover .dc-ts{display:inline}"
        ".dc-chat::-webkit-scrollbar{width:8px}"
        ".dc-chat::-webkit-scrollbar-track{background:#2b2d31}"
        ".dc-chat::-webkit-scrollbar-thumb{background:#1a1b1e;border-radius:4px}"
        "</style>"
    )

    parts.append(
        '<div class="mt-6">'
        '<h3 class="text-lg font-semibold mb-2">Transcript</h3>'
        '<div class="dc-chat" style="background-color:#313338;border-radius:8px;padding:8px 0;max-height:600px;overflow-y:auto;">'
    )

    prev_user: str | None = None
    has_messages = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # System lines (=== ... ===)
        if _TRANSCRIPT_SYS_RE.match(line):
            prev_user = None
            parts.append(
                '<div style="text-align:center;padding:4px 16px;'
                f'color:#949ba4;font-size:12px;">{escape(line)}</div>'
            )
            continue

        # Meta lines (Created by/at)
        if _TRANSCRIPT_META_RE.match(line):
            parts.append(
                '<div style="text-align:center;padding:2px 16px;'
                f'color:#949ba4;font-size:12px;">{escape(line)}</div>'
            )
            continue

        # Chat messages
        m = _TRANSCRIPT_MSG_RE.match(line)
        if m:
            ts, username, content = m.groups()
            color = _discord_avatar_color(username)
            initial = escape(username[0].upper()) if username else "?"
            content_html = _format_discord_content(content)
            short_ts = escape(ts.split(" ")[1][:5])

            if username == prev_user:
                # Continuation message (compact, with hover timestamp)
                parts.append(
                    '<div class="dc-msg" style="padding:2px 16px 2px 72px;position:relative;line-height:1.375;">'
                    '<span class="dc-ts" style="position:absolute;left:0;width:72px;text-align:center;'
                    f'font-size:11px;color:#949ba4;line-height:22px;">{short_ts}</span>'
                    f'<span style="color:#dbdee1;font-size:14px;">{content_html}</span>'
                    "</div>"
                )
            else:
                # New message group with avatar
                prev_user = username
                mt = "margin-top:16px;" if has_messages else ""
                has_messages = True
                parts.append(
                    f'<div class="dc-msg" style="padding:4px 16px;display:flex;{mt}">'
                    # Avatar circle
                    f'<div style="width:40px;height:40px;border-radius:50%;background-color:{color};'
                    f"display:flex;align-items:center;justify-content:center;flex-shrink:0;"
                    f'margin-right:16px;margin-top:2px;">'
                    f'<span style="color:white;font-weight:600;font-size:16px;">{initial}</span></div>'
                    # Username + timestamp + content
                    f'<div style="min-width:0;flex:1;">'
                    f'<div><span style="color:{color};font-weight:600;font-size:14px;margin-right:8px;">'
                    f"{escape(username)}</span>"
                    f'<span style="color:#949ba4;font-size:12px;">{escape(ts)}</span></div>'
                    f'<div style="color:#dbdee1;font-size:14px;line-height:1.375;'
                    f'word-wrap:break-word;overflow-wrap:break-word;">'
                    f"{content_html}</div></div></div>"
                )
            continue

        # Fallback for unrecognized lines
        prev_user = None
        style = (
            "color:#f38ba8;font-style:italic;"
            if line.startswith("[Failed to fetch")
            else "color:#949ba4;"
        )
        parts.append(
            f'<div style="padding:4px 16px 4px 72px;font-size:13px;{style}">'
            f"{escape(line)}</div>"
        )

    parts.append("</div></div>")
    return "".join(parts)


def ticket_list_page(
    tickets: list["Ticket"],
    csrf_token: str = "",
    guilds_map: dict[str, str] | None = None,
    status_filter: str = "",
) -> str:
    """Ticket list page template."""
    if guilds_map is None:
        guilds_map = {}

    row_parts: list[str] = []
    for ticket in tickets:
        guild_name = guilds_map.get(ticket.guild_id)
        if guild_name:
            guild_display = (
                f'<span class="font-medium">{escape(guild_name)}</span>'
                f'<br><span class="font-mono text-xs text-gray-500">'
                f"{escape(ticket.guild_id)}</span>"
            )
        else:
            guild_display = (
                f'<span class="font-mono text-yellow-400">'
                f"{escape(ticket.guild_id)}</span>"
            )

        status_colors = {
            "open": "text-green-400",
            "claimed": "text-blue-400",
            "closed": "text-gray-500",
        }
        status_class = status_colors.get(ticket.status, "text-gray-400")
        created = format_datetime(ticket.created_at)

        row_parts.append(f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 align-middle font-mono">#{ticket.ticket_number}</td>
            <td class="py-3 px-4 align-middle">{escape(ticket.username)}</td>
            <td class="py-3 px-4 align-middle">
                <span class="{status_class}">{escape(ticket.status)}</span>
            </td>
            <td class="py-3 px-4 align-middle">{guild_display}</td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">{created}</td>
            <td class="py-3 px-4 align-middle space-x-2">
                <a href="/tickets/{ticket.id}"
                   class="text-blue-400 hover:text-blue-300 text-sm">View</a>
                <a href="#" onclick="postAction('/tickets/{ticket.id}/delete', '{csrf_token}', 'Delete this ticket log?'); return false;"
                   class="text-red-400 hover:text-red-300 text-sm">Delete</a>
            </td>
        </tr>
        """)
    rows = "".join(row_parts)

    if not tickets:
        rows = """
        <tr>
            <td colspan="6" class="py-8 text-center text-gray-500">
                No tickets found
            </td>
        </tr>
        """

    # Status filter options
    filter_option_parts: list[str] = []
    for s in ["", "open", "claimed", "closed"]:
        selected = "selected" if s == status_filter else ""
        label = "All" if s == "" else s.capitalize()
        filter_option_parts.append(f'<option value="{s}" {selected}>{label}</option>')
    filter_options = "".join(filter_option_parts)

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Tickets",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Tickets", None),
            ],
        )
    }
        <div class="flex gap-3 mb-4 items-center">
            <a href="/tickets/panels"
               class="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded text-sm transition-colors">
                Panels
            </a>
            <form method="GET" action="/tickets" class="ml-auto flex items-center gap-2">
                <label class="text-sm text-gray-400">Status:</label>
                <select name="status" onchange="this.form.submit()"
                        class="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm text-gray-100">
                    {filter_options}
                </select>
            </form>
        </div>
        <div class="bg-gray-800 rounded-lg overflow-hidden overflow-x-auto">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="py-3 px-4 text-left">#</th>
                        <th class="py-3 px-4 text-left">User</th>
                        <th class="py-3 px-4 text-left">Status</th>
                        <th class="py-3 px-4 text-left">Server</th>
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
    return _base("Tickets", content)


def ticket_detail_page(
    ticket: "Ticket",
    category_name: str = "",
    guild_name: str = "",
    csrf_token: str = "",
) -> str:
    """Ticket detail page template."""
    import json as json_mod

    status_colors = {
        "open": "text-green-400",
        "claimed": "text-blue-400",
        "closed": "text-gray-500",
    }
    status_class = status_colors.get(ticket.status, "text-gray-400")

    created = format_datetime(ticket.created_at, "%Y-%m-%d %H:%M:%S")
    closed = format_datetime(ticket.closed_at, "%Y-%m-%d %H:%M:%S")

    # フォーム回答を表示
    form_answers_html = ""
    if ticket.form_answers:
        try:
            answers = json_mod.loads(ticket.form_answers)
            if isinstance(answers, list):
                form_answer_parts: list[str] = [
                    '<div class="mt-4"><h3 class="text-lg font-semibold mb-2">Form Answers</h3>'
                ]
                for qa in answers:
                    q = escape(str(qa.get("question", "")))
                    a = escape(str(qa.get("answer", "")))
                    form_answer_parts.append(f"""
                    <div class="bg-gray-700 rounded p-3 mb-2">
                        <div class="text-sm text-gray-400">{q}</div>
                        <div>{a}</div>
                    </div>
                    """)
                form_answer_parts.append("</div>")
                form_answers_html = "".join(form_answer_parts)
        except (json_mod.JSONDecodeError, TypeError):
            pass

    # トランスクリプト
    transcript_html = ""
    if ticket.transcript:
        transcript_html = _render_discord_transcript(ticket.transcript)
    elif ticket.status != "closed":
        transcript_html = """
        <div class="mt-6">
            <h3 class="text-lg font-semibold mb-2">Transcript</h3>
            <p class="text-gray-500 text-sm">Transcript will be available after the ticket is closed.</p>
        </div>
        """

    delete_form = f"""
        <div class="flex justify-end mb-4">
            <form method="POST" action="/tickets/{ticket.id}/delete"
                  onsubmit="return confirm('Delete this ticket log?');">
                {_csrf_field(csrf_token)}
                <button type="submit"
                        class="bg-red-600 hover:bg-red-500 px-4 py-2 rounded text-sm transition-colors">
                    Delete
                </button>
            </form>
        </div>
    """

    content = f"""
    <div class="p-6">
        {
        _nav(
            f"Ticket #{ticket.ticket_number}",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Tickets", "/tickets"),
                (f"Ticket #{ticket.ticket_number}", None),
            ],
        )
    }
        {delete_form}
        <div class="bg-gray-800 rounded-lg p-6">
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div>
                    <div class="text-sm text-gray-400">Status</div>
                    <div class="{status_class} font-medium">{
        escape(ticket.status)
    }</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">User</div>
                    <div>{escape(ticket.username)}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">Category</div>
                    <div>{escape(category_name)}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">Server</div>
                    <div>{escape(guild_name or ticket.guild_id)}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">Created</div>
                    <div class="text-sm">{created}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">Closed</div>
                    <div class="text-sm">{closed}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">Claimed By</div>
                    <div class="text-sm">{escape(ticket.claimed_by or "-")}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">Closed By</div>
                    <div class="text-sm">{escape(ticket.closed_by or "-")}</div>
                </div>
            </div>

            {form_answers_html}
            {transcript_html}
        </div>
    </div>
    """
    return _base(f"Ticket #{ticket.ticket_number}", content)


def ticket_panels_list_page(
    panels: list["TicketPanel"],
    csrf_token: str = "",
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
) -> str:
    """Ticket panels list page template."""
    if guilds_map is None:
        guilds_map = {}
    if channels_map is None:
        channels_map = {}

    def get_channel_name(guild_id: str, channel_id: str) -> str:
        """チャンネル名を取得する。"""
        for cid, name in channels_map.get(guild_id, []):
            if cid == channel_id:
                return f"#{name}"
        return channel_id

    row_parts: list[str] = []
    for panel in panels:
        guild_name = guilds_map.get(panel.guild_id, panel.guild_id)
        created = format_datetime(panel.created_at)
        posted = "Yes" if panel.message_id else "No"

        row_parts.append(f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 align-middle">
                <a href="/tickets/panels/{panel.id}"
                   class="font-medium text-blue-400 hover:text-blue-300">
                    {escape(panel.title)}
                </a>
            </td>
            <td class="py-3 px-4 align-middle text-sm">{escape(guild_name)}</td>
            <td class="py-3 px-4 align-middle text-sm">{escape(get_channel_name(panel.guild_id, panel.channel_id))}</td>
            <td class="py-3 px-4 align-middle text-sm">{posted}</td>
            <td class="py-3 px-4 align-middle text-gray-400 text-sm">{created}</td>
            <td class="py-3 px-4 align-middle">
                <a href="#" onclick="postAction('/tickets/panels/{panel.id}/delete', '{csrf_token}', 'Delete this panel?'); return false;"
                   class="text-red-400 hover:text-red-300 text-sm">Delete</a>
            </td>
        </tr>
        """)
    rows = "".join(row_parts)

    if not panels:
        rows = """
        <tr>
            <td colspan="6" class="py-8 text-center text-gray-500">
                No ticket panels configured
            </td>
        </tr>
        """

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Ticket Panels",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Tickets", "/tickets"),
                ("Panels", None),
            ],
        )
    }
        <div class="flex gap-3 mb-4">
            <a href="/tickets/panels/new"
               class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm transition-colors">
                + Create Panel
            </a>
        </div>
        <div class="bg-gray-800 rounded-lg overflow-hidden overflow-x-auto">
            <table class="w-full">
                <thead class="bg-gray-700">
                    <tr>
                        <th class="py-3 px-4 text-left">Title</th>
                        <th class="py-3 px-4 text-left">Server</th>
                        <th class="py-3 px-4 text-left">Channel</th>
                        <th class="py-3 px-4 text-left">Posted</th>
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
    return _base("Ticket Panels", content)


def ticket_panel_create_page(
    guilds_map: dict[str, str] | None = None,
    channels_map: dict[str, list[tuple[str, str]]] | None = None,
    roles_map: dict[str, list[tuple[str, str]]] | None = None,
    discord_categories_map: dict[str, list[tuple[str, str]]] | None = None,
    csrf_token: str = "",
    error: str | None = None,
) -> str:
    """Ticket panel create page template."""
    if guilds_map is None:
        guilds_map = {}
    if channels_map is None:
        channels_map = {}
    if roles_map is None:
        roles_map = {}
    if discord_categories_map is None:
        discord_categories_map = {}

    guild_options = ""
    for gid, gname in sorted(guilds_map.items(), key=lambda x: x[1]):
        guild_options += (
            f'<option value="{escape(gid)}">{escape(gname)} ({escape(gid)})</option>'
        )

    error_html = ""
    if error:
        error_html = f"""
        <div class="bg-red-500/20 border border-red-500 text-red-300 px-4 py-3 rounded mb-6">
            {escape(error)}
        </div>
        """

    import json as json_mod

    channels_data: dict[str, list[dict[str, str]]] = {}
    for gid, ch_list in channels_map.items():
        channels_data[gid] = [{"id": cid, "name": cname} for cid, cname in ch_list]
    channels_json = json_mod.dumps(channels_data)

    roles_data: dict[str, list[dict[str, str]]] = {}
    for gid, role_list in roles_map.items():
        roles_data[gid] = [{"id": rid, "name": name} for rid, name in role_list]
    roles_json = json_mod.dumps(roles_data)

    cat_data: dict[str, list[dict[str, str]]] = {}
    for gid, cat_list in discord_categories_map.items():
        cat_data[gid] = [{"id": cid, "name": cname} for cid, cname in cat_list]
    discord_cats_json = json_mod.dumps(cat_data)

    content = f"""
    <div class="p-6">
        {
        _nav(
            "Create Ticket Panel",
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Tickets", "/tickets"),
                ("Panels", "/tickets/panels"),
                ("Create", None),
            ],
        )
    }
        {error_html}
        <div class="max-w-2xl">
            <form method="POST" action="/tickets/panels/new" class="space-y-6">
                {_csrf_field(csrf_token)}

                <div>
                    <label class="block text-sm font-medium mb-1">Server</label>
                    <select name="guild_id" required id="guildSelect"
                            onchange="updateSelects()"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="">Select server...</option>
                        {guild_options}
                    </select>
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">Channel</label>
                    <select name="channel_id" required id="channelSelect"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="">Select channel...</option>
                    </select>
                    <p class="text-xs text-gray-500 mt-1">
                        The channel where the ticket panel will be posted.
                    </p>
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">Title</label>
                    <input type="text" name="title" required
                           placeholder="e.g. Support Ticket"
                           class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">
                        Description
                        <span class="text-gray-400 font-normal">(optional)</span>
                    </label>
                    <textarea name="description" rows="3"
                              placeholder="Click a button below to create a ticket."
                              class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100"></textarea>
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">Staff Role</label>
                    <select name="staff_role_id" required id="staffRoleSelect"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="">Select role...</option>
                    </select>
                    <p class="text-xs text-gray-500 mt-1">
                        Staff with this role can view and manage tickets.
                    </p>
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">
                        Discord Category
                        <span class="text-gray-400 font-normal">(optional)</span>
                    </label>
                    <select name="discord_category_id" id="discordCategorySelect"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="">None</option>
                    </select>
                    <p class="text-xs text-gray-500 mt-1">
                        Ticket channels will be created under this Discord category.
                    </p>
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">Channel Prefix</label>
                    <input type="text" name="channel_prefix" value="ticket-"
                           class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                </div>

                <div>
                    <label class="block text-sm font-medium mb-1">
                        Log Channel
                        <span class="text-gray-400 font-normal">(optional)</span>
                    </label>
                    <select name="log_channel_id" id="logChannelSelect"
                            class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                        <option value="">None</option>
                    </select>
                    <p class="text-xs text-gray-500 mt-1">
                        Close notifications will be sent to this channel.
                    </p>
                </div>

                <button type="submit"
                        class="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded transition-colors">
                    Create Panel
                </button>
            </form>
        </div>
    </div>

    <script>
    const channelsData = {channels_json};
    const rolesData = {roles_json};
    const discordCatsData = {discord_cats_json};
    function updateSelects() {{
        const guildId = document.getElementById('guildSelect').value;

        const chSelect = document.getElementById('channelSelect');
        chSelect.innerHTML = '<option value="">Select channel...</option>';
        if (channelsData[guildId]) {{
            channelsData[guildId].forEach(ch => {{
                const opt = document.createElement('option');
                opt.value = ch.id;
                opt.textContent = '#' + ch.name;
                chSelect.appendChild(opt);
            }});
        }}

        const roleSelect = document.getElementById('staffRoleSelect');
        roleSelect.innerHTML = '<option value="">Select role...</option>';
        if (rolesData[guildId]) {{
            rolesData[guildId].forEach(role => {{
                const opt = document.createElement('option');
                opt.value = role.id;
                opt.textContent = role.name;
                roleSelect.appendChild(opt);
            }});
        }}

        const catSelect = document.getElementById('discordCategorySelect');
        catSelect.innerHTML = '<option value="">None</option>';
        if (discordCatsData[guildId]) {{
            discordCatsData[guildId].forEach(cat => {{
                const opt = document.createElement('option');
                opt.value = cat.id;
                opt.textContent = cat.name;
                catSelect.appendChild(opt);
            }});
        }}

        const logSelect = document.getElementById('logChannelSelect');
        logSelect.innerHTML = '<option value="">None</option>';
        if (channelsData[guildId]) {{
            channelsData[guildId].forEach(ch => {{
                const opt = document.createElement('option');
                opt.value = ch.id;
                opt.textContent = '#' + ch.name;
                logSelect.appendChild(opt);
            }});
        }}
    }}
    </script>
    """
    return _base("Create Ticket Panel", content)


def ticket_panel_detail_page(
    panel: "TicketPanel",
    associations: list[tuple["TicketPanelCategory", str]],
    success: str | None = None,
    guild_name: str | None = None,
    channel_name: str | None = None,
    csrf_token: str = "",
) -> str:
    """Ticket panel detail/edit page template.

    Args:
        panel: チケットパネル
        associations: (TicketPanelCategory, category_name) のリスト
        success: 成功メッセージ
        guild_name: ギルド名
        channel_name: チャンネル名
        csrf_token: CSRF トークン
    """
    success_html = ""
    if success:
        success_html = f"""
        <div class="bg-green-900/50 border border-green-700 rounded-lg p-3 mb-4">
            <span class="text-green-400">{escape(success)}</span>
        </div>
        """

    server_display = escape(guild_name or panel.guild_id)
    channel_display = escape(channel_name or panel.channel_id)
    message_display = escape(panel.message_id) if panel.message_id else "(not posted)"
    created = format_datetime(panel.created_at)

    # Post/Update to Discord ボタン
    if panel.message_id:
        discord_btn_label = "Update in Discord"
        discord_confirm = "Update the panel message in Discord?"
    else:
        discord_btn_label = "Post to Discord"
        discord_confirm = "Post this panel to Discord?"

    # カテゴリボタン行
    button_row_parts: list[str] = []
    style_options_map = {
        "primary": "Blue",
        "secondary": "Gray",
        "success": "Green",
        "danger": "Red",
    }
    for assoc, cat_name in associations:
        style_option_parts: list[str] = []
        for val, label in style_options_map.items():
            selected = "selected" if assoc.button_style == val else ""
            style_option_parts.append(
                f'<option value="{val}" {selected}>{label}</option>'
            )
        style_options = "".join(style_option_parts)

        button_row_parts.append(f"""
        <tr class="border-b border-gray-700">
            <td class="py-3 px-4 align-middle text-sm">{escape(cat_name)}</td>
            <td class="py-3 px-4 align-middle">
                <form method="POST"
                      action="/tickets/panels/{panel.id}/buttons/{assoc.id}/edit"
                      class="flex gap-2 items-center flex-wrap">
                    {_csrf_field(csrf_token)}
                    <input type="text" name="button_label"
                           value="{escape(assoc.button_label or "")}"
                           placeholder="{escape(cat_name)}"
                           maxlength="80"
                           class="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm w-32">
                    <select name="button_style"
                            class="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm">
                        {style_options}
                    </select>
                    <input type="text" name="button_emoji"
                           value="{escape(assoc.button_emoji or "")}"
                           placeholder="Emoji"
                           maxlength="64"
                           class="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm w-20">
                    <button type="submit"
                            class="bg-blue-600 hover:bg-blue-500 px-3 py-1 rounded text-sm transition-colors">
                        Save
                    </button>
                </form>
            </td>
        </tr>
        """)
    button_rows = "".join(button_row_parts)

    if not associations:
        button_rows = """
        <tr>
            <td colspan="2" class="py-8 text-center text-gray-500">
                No category buttons configured
            </td>
        </tr>
        """

    content = f"""
    <div class="p-6">
        {
        _nav(
            escape(panel.title),
            breadcrumbs=[
                ("Dashboard", "/dashboard"),
                ("Tickets", "/tickets"),
                ("Panels", "/tickets/panels"),
                (escape(panel.title), None),
            ],
        )
    }
        {success_html}

        <div class="bg-gray-800 rounded-lg p-6 mb-6">
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <div>
                    <div class="text-sm text-gray-400">Server</div>
                    <div class="text-sm">{server_display}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">Channel</div>
                    <div class="text-sm">{channel_display}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">Message ID</div>
                    <div class="text-sm font-mono">{message_display}</div>
                </div>
                <div>
                    <div class="text-sm text-gray-400">Created</div>
                    <div class="text-sm">{created}</div>
                </div>
            </div>

            <div class="border-t border-gray-700 pt-4">
                <h3 class="text-lg font-semibold mb-3">Edit Panel</h3>
                <form method="POST" action="/tickets/panels/{panel.id}/edit"
                      class="space-y-4">
                    {_csrf_field(csrf_token)}
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Title</label>
                        <input type="text" name="title"
                               value="{escape(panel.title)}"
                               required maxlength="100"
                               class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Description</label>
                        <textarea name="description" rows="3" maxlength="2000"
                                  class="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-gray-100"
                                  >{escape(panel.description or "")}</textarea>
                    </div>
                    <button type="submit"
                            class="bg-blue-600 hover:bg-blue-500 px-4 py-2 rounded text-sm transition-colors">
                        Save Changes
                    </button>
                </form>
            </div>

            <div class="border-t border-gray-700 pt-4 mt-4">
                <form method="POST" action="/tickets/panels/{panel.id}/post"
                      onsubmit="return confirm('{discord_confirm}');">
                    {_csrf_field(csrf_token)}
                    <button type="submit"
                            class="bg-indigo-600 hover:bg-indigo-500 px-4 py-2 rounded text-sm transition-colors">
                        {discord_btn_label}
                    </button>
                </form>
            </div>
        </div>

        <div class="bg-gray-800 rounded-lg p-6">
            <h3 class="text-lg font-semibold mb-4">Category Buttons ({
        len(associations)
    })</h3>
            <div class="overflow-x-auto">
                <table class="w-full">
                    <thead class="bg-gray-700">
                        <tr>
                            <th class="py-3 px-4 text-left">Category</th>
                            <th class="py-3 px-4 text-left">Button Settings</th>
                        </tr>
                    </thead>
                    <tbody>
                        {button_rows}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    """
    return _base(f"Panel: {escape(panel.title)}", content)
