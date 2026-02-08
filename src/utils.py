"""Shared utility functions."""

from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import emoji

from src.config import settings

# =============================================================================
# リソースロック管理 (並行処理の競合防止)
# =============================================================================

# リソースごとのロックを管理
# key: resource_key (任意の文字列), value: (asyncio.Lock, last_access_time)
_resource_locks: dict[str, tuple[asyncio.Lock, float]] = {}

# ロッククリーンアップ間隔
_LOCK_CLEANUP_INTERVAL = 600  # 10分
_lock_last_cleanup_time = float("-inf")

# 未使用ロックの保持時間
_LOCK_EXPIRY_TIME = 300  # 5分


def _cleanup_resource_locks() -> None:
    """古い未使用ロックを削除する."""
    global _lock_last_cleanup_time
    now = time.monotonic()

    # 10分ごとにクリーンアップ
    if (
        _lock_last_cleanup_time > 0
        and now - _lock_last_cleanup_time < _LOCK_CLEANUP_INTERVAL
    ):
        return

    _lock_last_cleanup_time = now

    # 古いロックを削除 (5分以上アクセスがなく、ロックされていないもの)
    expired = [
        key
        for key, (lock, last_access) in _resource_locks.items()
        if now - last_access > _LOCK_EXPIRY_TIME and not lock.locked()
    ]
    for key in expired:
        del _resource_locks[key]


def get_resource_lock(resource_key: str) -> asyncio.Lock:
    """リソースキーに対応するロックを取得する.

    同じリソースキーに対しては常に同じロックインスタンスを返す。
    これにより、同一リソースへの同時アクセスを防止できる。

    Args:
        resource_key: リソースを識別するキー
            例: "channel:123456", "guild:789:bump:DISBOARD"

    Returns:
        asyncio.Lock インスタンス

    Example:
        async with get_resource_lock(f"channel:{channel_id}"):
            # この中は同じチャンネルに対して1つのリクエストのみ実行される
            await do_operation()
    """
    _cleanup_resource_locks()

    now = time.monotonic()

    if resource_key not in _resource_locks:
        _resource_locks[resource_key] = (asyncio.Lock(), now)
    else:
        # アクセス時刻を更新
        lock, _ = _resource_locks[resource_key]
        _resource_locks[resource_key] = (lock, now)

    return _resource_locks[resource_key][0]


def clear_resource_locks() -> None:
    """全てのリソースロックをクリアする (テスト用)."""
    global _lock_last_cleanup_time
    _resource_locks.clear()
    _lock_last_cleanup_time = float("-inf")


def get_resource_lock_count() -> int:
    """現在管理されているロックの数を返す (テスト/デバッグ用)."""
    return len(_resource_locks)


# Discord カスタム絵文字パターン: <:name:id> または <a:name:id> (アニメーション)
DISCORD_CUSTOM_EMOJI_PATTERN = re.compile(r"^<a?:\w+:\d+>$")

# 制御文字パターン (改行、タブ、キャリッジリターン等)
# C0/C1 制御文字と一部の特殊文字を含む
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _has_lone_surrogate(text: str) -> bool:
    """壊れたサロゲートペアが含まれているかチェックする.

    Args:
        text: 検証する文字列

    Returns:
        壊れたサロゲートが含まれている場合True
    """
    try:
        # encode して decode できれば正常なUTF-8
        text.encode("utf-8").decode("utf-8")
        return False
    except (UnicodeEncodeError, UnicodeDecodeError):
        return True


def is_valid_emoji(text: str | None) -> bool:
    """絵文字として有効かどうかを検証する.

    Args:
        text: 検証する文字列

    Returns:
        Discordカスタム絵文字またはUnicode絵文字の場合True

    Note:
        emoji ライブラリを使用して、ZWJ シーケンス (🧑‍🧑‍🧒 等) や
        keycap 絵文字 (3️⃣ 等) を含む全ての Unicode 絵文字に対応。

        以下のケースは無効として拒否:
        - 空文字、None
        - 壊れたサロゲートペア
        - 制御文字 (改行、タブ等) を含む文字列
    """
    if not text:
        return False

    # 壊れたサロゲートペアのチェック
    if _has_lone_surrogate(text):
        return False

    # 制御文字 (改行、タブ等) のチェック
    if CONTROL_CHAR_PATTERN.search(text):
        return False

    # Discord カスタム絵文字 (<:name:id> or <a:name:id>)
    if DISCORD_CUSTOM_EMOJI_PATTERN.match(text):
        return True

    # NFC 正規化して比較 (異体字セレクタ等の正規化)
    normalized = unicodedata.normalize("NFC", text)

    # Unicode 絵文字 (emoji ライブラリで検証)
    if emoji.is_emoji(normalized):
        return True

    # VS16 (U+FE0F) 付きの絵文字に対応
    # ブラウザやOSが⚓→⚓️のようにVS16を付加することがあり、
    # emoji ライブラリが認識しないケースがあるため除去して再検証
    stripped = normalized.replace("\ufe0f", "")
    return bool(stripped and emoji.is_emoji(stripped))


def normalize_emoji(text: str) -> str:
    """絵文字を正規化して返す.

    DB保存前に呼び出すことで、同じ見た目の絵文字が
    異なるバイト列で保存されることを防ぐ。

    Args:
        text: 正規化する絵文字文字列

    Returns:
        NFC正規化された絵文字文字列

    Note:
        Discord カスタム絵文字 (<:name:id>) はそのまま返す。
        Unicode 絵文字は NFC 正規化を適用。
    """
    if not text:
        return text

    # Discord カスタム絵文字はそのまま
    if DISCORD_CUSTOM_EMOJI_PATTERN.match(text):
        return text

    # NFC 正規化 + VS16 除去で統一的な保存形式にする
    normalized = unicodedata.normalize("NFC", text)
    stripped = normalized.replace("\ufe0f", "")
    # VS16 除去後も有効な絵文字なら除去した形で返す
    if stripped and emoji.is_emoji(stripped):
        return stripped
    return normalized


# =============================================================================
# 日時フォーマット (タイムゾーンオフセット対応)
# =============================================================================


@lru_cache(maxsize=4)
def _make_timezone(offset: int) -> timezone:
    """timezone オブジェクトをキャッシュして返す."""
    return timezone(timedelta(hours=offset))


def _get_timezone() -> timezone:
    """設定されたタイムゾーンオフセットから timezone オブジェクトを返す."""
    return _make_timezone(settings.timezone_offset)


def format_datetime(
    dt: datetime | None,
    fmt: str = "%Y-%m-%d %H:%M",
    *,
    fallback: str = "-",
) -> str:
    """datetime を設定されたタイムゾーンでフォーマットする.

    Args:
        dt: フォーマット対象の datetime (None 可)
        fmt: strftime フォーマット文字列
        fallback: dt が None の場合の代替文字列

    Returns:
        フォーマット済み文字列
    """
    if dt is None:
        return fallback
    tz = _get_timezone()
    local_dt = dt.astimezone(tz)
    return local_dt.strftime(fmt)
