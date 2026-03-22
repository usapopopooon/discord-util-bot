"""Common helpers shared across template modules."""

import re
from html import escape

from src.utils import format_datetime

# Re-export for submodules
__all__ = [
    "_base",
    "_breadcrumb",
    "_build_emoji_list",
    "_csrf_field",
    "_get_emoji_json",
    "_nav",
    "_roles_to_js_array",
    "escape",
    "format_datetime",
    "re",
]


def _csrf_field(csrf_token: str) -> str:
    """CSRF トークンの hidden フィールドを生成する."""
    return f'<input type="hidden" name="csrf_token" value="{escape(csrf_token)}">'


def _roles_to_js_array(roles: list[tuple[str, str, int]]) -> str:
    """Discord ロールリストを JavaScript 配列文字列に変換する."""
    import json

    js_roles = [{"id": r[0], "name": r[1], "color": r[2]} for r in roles]
    return json.dumps(js_roles)


_EMOJI_JSON: str | None = None


def _get_emoji_json() -> str:
    """emoji ライブラリから名前→絵文字の JSON 配列を返す (キャッシュ付き)."""
    global _EMOJI_JSON  # noqa: PLW0603
    if _EMOJI_JSON is None:
        _EMOJI_JSON = _build_emoji_list()
    return _EMOJI_JSON


def _build_emoji_list() -> str:
    """emoji ライブラリから [name, char] の JSON 配列文字列を生成する."""
    import json

    import emoji as emoji_lib

    vs16 = "\ufe0f"
    seen: dict[str, str] = {}  # name -> char (重複排除用)
    for char, data in emoji_lib.EMOJI_DATA.items():
        en = data.get("en", "")
        if not en:
            continue
        # 国旗を除外 (Regional Indicator 2文字)
        if len(char) == 2 and all(0x1F1E6 <= ord(c) <= 0x1F1FF for c in char):
            continue
        # 肌色バリアントを除外
        if any(0x1F3FB <= ord(c) <= 0x1F3FF for c in char):
            continue
        name = en.strip(":").replace("_", " ").lower()
        # VS16 を付与して絵文字表示を強制 (⚓ → ⚓️)
        # VS16 なしだとブラウザがテキスト表示 (白黒記号) にする場合がある
        if data.get("variant") and not char.endswith(vs16):
            char = char + vs16
        # 同名エントリは VS16 版を優先 (☎ と ☎️ → ☎️ のみ)
        if name not in seen or vs16 in char:
            seen[name] = char
    items = sorted(seen.items(), key=lambda x: x[0])
    return json.dumps(items, ensure_ascii=False, separators=(",", ":"))


def _base(title: str, content: str) -> str:
    """Base HTML template with Tailwind CDN."""
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(title)} - Bot Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
    function postAction(url, csrfToken, confirmMsg) {{
        if (confirmMsg && !confirm(confirmMsg)) return;
        const f = document.createElement('form');
        f.method = 'POST';
        f.action = url;
        const i = document.createElement('input');
        i.type = 'hidden';
        i.name = 'csrf_token';
        i.value = csrfToken;
        f.appendChild(i);
        document.body.appendChild(f);
        f.submit();
    }}
    </script>
</head>
<body class="bg-gray-900 text-gray-100 min-h-screen">
    {content}
</body>
</html>"""


def _breadcrumb(crumbs: list[tuple[str, str | None]]) -> str:
    """パンくずリストを生成する.

    Args:
        crumbs: (label, url) のリスト。最後の要素は現在のページ (url=None)。
                最後の要素は h1 タイトルと重複するためレンダリングしない。

    Returns:
        パンくずリストの HTML
    """
    items = []
    # 最後の要素（現在のページ）は h1 タイトルとして表示されるため除外
    nav_crumbs = crumbs[:-1] if crumbs else []
    for i, (label, url) in enumerate(nav_crumbs):
        if url:
            items.append(
                f'<a href="{escape(url)}" class="text-gray-400 hover:text-white">'
                f"{escape(label)}</a>"
            )
        else:
            items.append(f'<span class="text-gray-300">{escape(label)}</span>')
        if i < len(nav_crumbs) - 1:
            items.append('<span class="text-gray-600">&gt;</span>')
    return " ".join(items)


def _nav(
    title: str,
    show_dashboard_link: bool = True,
    breadcrumbs: list[tuple[str, str | None]] | None = None,
) -> str:
    """Navigation bar component.

    Args:
        title: ページタイトル (h1)
        show_dashboard_link: Dashboard リンクを表示するか (breadcrumbs がある場合は無視)
        breadcrumbs: パンくずリスト。指定時は show_dashboard_link は無視される。
    """
    nav_content = ""
    if breadcrumbs:
        nav_content = _breadcrumb(breadcrumbs)
    elif show_dashboard_link:
        nav_content = (
            '<a href="/dashboard" class="text-gray-400 hover:text-white">'
            "&larr; Dashboard</a>"
        )
    return f"""
    <nav class="flex justify-between items-center mb-8">
        <div class="flex items-center gap-4">
            <div class="flex items-center gap-2 text-sm">
                {nav_content}
            </div>
            <h1 class="text-2xl font-bold">{escape(title)}</h1>
        </div>
        <a href="/logout"
           class="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded transition-colors">
            Logout
        </a>
    </nav>
    """
