"""Discord HTTP API client for posting messages from the web admin.

Web管理画面からDiscordにメッセージを投稿するためのHTTPクライアント。
BotとWebアプリが別プロセスで動作するため、Discord REST APIを直接使用する。

Notes:
    - Bot トークンは環境変数 DISCORD_TOKEN から取得
    - メッセージ投稿には channels/{channel_id}/messages エンドポイントを使用
    - コンポーネント (ボタン) の custom_id は Bot 側で処理される
"""

import asyncio
import logging
from typing import Any

import httpx

from src.config import settings
from src.database.models import RolePanel, RolePanelItem

logger = logging.getLogger(__name__)

# Discord API base URL
DISCORD_API_BASE = "https://discord.com/api/v10"

# Button style mapping (discord.py style names to API integers)
BUTTON_STYLE_MAP = {
    "primary": 1,
    "secondary": 2,
    "success": 3,
    "danger": 4,
}


def _create_embed_payload(
    panel: RolePanel, _items: list[RolePanelItem]
) -> dict[str, Any]:
    """ロールパネルの Embed ペイロードを作成する。

    Args:
        panel: RolePanel オブジェクト
        _items: パネルに設定されたロールアイテムのリスト (未使用)

    Returns:
        Discord API 用の Embed ペイロード
    """
    return {
        "title": panel.title,
        "description": panel.description or "",
        "color": panel.color if panel.color else 0x3498DB,  # Blue default
    }


def _create_content_text(panel: RolePanel, _items: list[RolePanelItem]) -> str:
    """ロールパネルの通常テキストメッセージを作成する。

    Args:
        panel: RolePanel オブジェクト
        _items: パネルに設定されたロールアイテムのリスト (未使用)

    Returns:
        メッセージテキスト
    """
    lines = [f"**{panel.title}**"]

    if panel.description:
        lines.append(panel.description)

    return "\n".join(lines)


def _create_components_payload(
    panel: RolePanel, items: list[RolePanelItem]
) -> list[dict[str, Any]]:
    """ロールパネルのコンポーネント (ボタン) ペイロードを作成する。

    Args:
        panel: RolePanel オブジェクト
        items: パネルに設定されたロールアイテムのリスト

    Returns:
        Discord API 用の Components ペイロード (action rows)
    """
    if panel.panel_type != "button" or not items:
        return []

    # Discord の制限: 1 action row につき最大 5 ボタン、最大 5 action rows
    buttons: list[dict[str, Any]] = []
    for item in items[:25]:  # 最大 25 ボタン
        button: dict[str, Any] = {
            "type": 2,  # Button
            "style": BUTTON_STYLE_MAP.get(item.style, 2),  # Secondary default
            "custom_id": f"role_panel:{panel.id}:{item.id}",
        }

        # ラベルまたは絵文字が必要
        if item.label:
            button["label"] = item.label

        if item.emoji:
            # Discord カスタム絵文字の場合
            if item.emoji.startswith("<"):
                # <:name:id> or <a:name:id> 形式をパース
                animated = item.emoji.startswith("<a:")
                parts = item.emoji.strip("<>").split(":")
                if len(parts) >= 3:
                    button["emoji"] = {
                        "name": parts[1] if animated else parts[1],
                        "id": parts[2] if animated else parts[2],
                        "animated": animated,
                    }
            else:
                # Unicode 絵文字
                button["emoji"] = {"name": item.emoji}

        buttons.append(button)

    # ボタンを action rows に分割 (1 row = 最大 5 ボタン)
    action_rows: list[dict[str, Any]] = []
    for i in range(0, len(buttons), 5):
        action_rows.append(
            {
                "type": 1,  # Action Row
                "components": buttons[i : i + 5],
            }
        )

    return action_rows


async def post_role_panel_to_discord(
    panel: RolePanel,
    items: list[RolePanelItem],
) -> tuple[bool, str | None, str | None]:
    """ロールパネルを Discord に投稿する。

    Args:
        panel: 投稿するロールパネル
        items: パネルのロールアイテム

    Returns:
        (success, message_id, error_message) のタプル
        - success: 投稿成功なら True
        - message_id: 成功時のメッセージ ID (失敗時は None)
        - error_message: 失敗時のエラーメッセージ (成功時は None)
    """
    if not settings.discord_token:
        return False, None, "Discord token is not configured"

    # メッセージペイロードを構築
    payload: dict[str, Any] = {}

    if panel.use_embed:
        payload["embeds"] = [_create_embed_payload(panel, items)]
    else:
        payload["content"] = _create_content_text(panel, items)

    # ボタン式の場合はコンポーネントを追加
    components = _create_components_payload(panel, items)
    if components:
        payload["components"] = components

    # Discord API にリクエスト
    url = f"{DISCORD_API_BASE}/channels/{panel.channel_id}/messages"
    headers = {
        "Authorization": f"Bot {settings.discord_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(url, json=payload, headers=headers, timeout=30)

            if response.status_code in (200, 201):
                data = response.json()
                message_id = data.get("id")
                logger.info(
                    "Posted role panel %d to channel %s (message_id=%s)",
                    panel.id,
                    panel.channel_id,
                    message_id,
                )
                return True, message_id, None

            # エラーレスポンスの処理
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("message", f"HTTP {response.status_code}")

            # 一般的なエラーコードの説明
            if response.status_code == 403:
                error_msg = "Bot にこのチャンネルへの送信権限がありません"
            elif response.status_code == 404:
                error_msg = "チャンネルが見つかりません (削除された可能性があります)"
            elif response.status_code == 401:
                error_msg = "Bot トークンが無効です"

            logger.error(
                "Failed to post role panel %d: %s (status=%d)",
                panel.id,
                error_msg,
                response.status_code,
            )
            return False, None, error_msg

    except httpx.TimeoutException:
        logger.error("Timeout posting role panel %d", panel.id)
        return False, None, "Discord API への接続がタイムアウトしました"
    except httpx.RequestError as e:
        logger.error("Request error posting role panel %d: %s", panel.id, e)
        return False, None, f"Discord API への接続に失敗しました: {e}"


async def edit_role_panel_in_discord(
    panel: RolePanel,
    items: list[RolePanelItem],
) -> tuple[bool, str | None]:
    """Discord のロールパネルメッセージを編集する。

    Args:
        panel: 編集するロールパネル (message_id が必要)
        items: パネルのロールアイテム

    Returns:
        (success, error_message) のタプル
        - success: 編集成功なら True
        - error_message: 失敗時のエラーメッセージ (成功時は None)
    """
    if not settings.discord_token:
        return False, "Discord token is not configured"

    if not panel.message_id:
        return False, "Panel has no message_id"

    # メッセージペイロードを構築
    payload: dict[str, Any] = {}

    if panel.use_embed:
        payload["embeds"] = [_create_embed_payload(panel, items)]
    else:
        payload["content"] = _create_content_text(panel, items)

    # ボタン式の場合はコンポーネントを追加
    components = _create_components_payload(panel, items)
    if components:
        payload["components"] = components
    else:
        # ボタンがない場合は空配列でクリア
        payload["components"] = []

    # Discord API に PATCH リクエスト
    url = f"{DISCORD_API_BASE}/channels/{panel.channel_id}/messages/{panel.message_id}"
    headers = {
        "Authorization": f"Bot {settings.discord_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.patch(
                url, json=payload, headers=headers, timeout=30
            )

            if response.status_code == 200:
                logger.info(
                    "Edited role panel %d message %s",
                    panel.id,
                    panel.message_id,
                )
                return True, None

            # エラーレスポンスの処理
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("message", f"HTTP {response.status_code}")

            # 一般的なエラーコードの説明
            if response.status_code == 403:
                error_msg = "Bot にこのメッセージの編集権限がありません"
            elif response.status_code == 404:
                error_msg = "メッセージが見つかりません (削除された可能性があります)"
            elif response.status_code == 401:
                error_msg = "Bot トークンが無効です"

            logger.error(
                "Failed to edit role panel %d: %s (status=%d)",
                panel.id,
                error_msg,
                response.status_code,
            )
            return False, error_msg

    except httpx.TimeoutException:
        logger.error("Timeout editing role panel %d", panel.id)
        return False, "Discord API への接続がタイムアウトしました"
    except httpx.RequestError as e:
        logger.error("Request error editing role panel %d: %s", panel.id, e)
        return False, f"Discord API への接続に失敗しました: {e}"


async def clear_reactions_from_message(
    channel_id: str,
    message_id: str,
) -> tuple[bool, str | None]:
    """メッセージの全リアクションを削除する。

    Args:
        channel_id: チャンネル ID
        message_id: メッセージ ID

    Returns:
        (success, error_message) のタプル
    """
    if not settings.discord_token:
        return False, "Discord token is not configured"

    headers = {
        "Authorization": f"Bot {settings.discord_token}",
    }

    try:
        async with httpx.AsyncClient(verify=False) as client:
            url = (
                f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}"
                "/reactions"
            )
            response = await client.delete(url, headers=headers, timeout=10)

            if response.status_code in (200, 204):
                return True, None

            error_data = response.json() if response.content else {}
            error_msg = error_data.get("message", f"HTTP {response.status_code}")
            logger.warning("Failed to clear reactions: %s", error_msg)
            return False, error_msg

    except httpx.TimeoutException:
        return False, "Discord API への接続がタイムアウトしました"
    except httpx.RequestError as e:
        return False, f"Discord API への接続に失敗しました: {e}"


async def add_reactions_to_message(
    channel_id: str,
    message_id: str,
    items: list[RolePanelItem],
    clear_existing: bool = False,
) -> tuple[bool, str | None]:
    """メッセージにリアクションを追加する。

    リアクション式パネルの場合に使用。

    Args:
        channel_id: チャンネル ID
        message_id: メッセージ ID
        items: リアクションを追加するロールアイテム
        clear_existing: 既存リアクションをクリアするか

    Returns:
        (success, error_message) のタプル
    """
    if not settings.discord_token:
        return False, "Discord token is not configured"

    # 既存リアクションをクリア
    if clear_existing:
        clear_success, clear_error = await clear_reactions_from_message(
            channel_id, message_id
        )
        if not clear_success:
            logger.warning("Failed to clear reactions: %s", clear_error)
            # クリア失敗は継続 (403 権限不足の場合もある)
        else:
            # クリア成功後、リアクション追加前にディレイを入れる
            # (Discord のレート制限対策)
            await asyncio.sleep(0.5)

    if not items:
        return True, None

    headers = {
        "Authorization": f"Bot {settings.discord_token}",
    }

    try:
        async with httpx.AsyncClient(verify=False) as client:
            for i, item in enumerate(items):
                # 絵文字をエンコード
                if item.emoji.startswith("<"):
                    # カスタム絵文字: <:name:id> → name:id
                    emoji_encoded = item.emoji.strip("<>").lstrip("a:")
                else:
                    # Unicode 絵文字: URL エンコード
                    import urllib.parse

                    emoji_encoded = urllib.parse.quote(item.emoji)

                url = (
                    f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}"
                    f"/reactions/{emoji_encoded}/@me"
                )

                response = await client.put(url, headers=headers, timeout=10)

                if response.status_code not in (200, 204):
                    error_data = response.json() if response.content else {}
                    error_msg = error_data.get(
                        "message", f"HTTP {response.status_code}"
                    )
                    logger.warning(
                        "Failed to add reaction %s: %s (status=%d)",
                        item.emoji,
                        error_msg,
                        response.status_code,
                    )
                    # リアクション追加の失敗は全体のエラーとしない
                    continue

                logger.debug("Added reaction %s to message %s", item.emoji, message_id)

                # Discord のレート制限対策: リアクション間にディレイを入れる
                # (最後のアイテムの後は待たない)
                if i < len(items) - 1:
                    await asyncio.sleep(0.4)

        return True, None

    except httpx.TimeoutException:
        return False, "Discord API への接続がタイムアウトしました"
    except httpx.RequestError as e:
        return False, f"Discord API への接続に失敗しました: {e}"
