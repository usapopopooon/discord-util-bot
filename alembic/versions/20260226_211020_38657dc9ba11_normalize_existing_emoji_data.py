"""normalize_existing_emoji_data

既存の role_panel_items テーブルの emoji カラムを normalize_emoji で再正規化する。
VS16 除去ロジック追加により、旧データと新データで絵文字形式が不一致になるのを修正。

Revision ID: 38657dc9ba11
Revises: y5z6a7b8c9d0
Create Date: 2026-02-26 21:10:20.951449

"""

import unicodedata
from typing import Sequence, Union

import emoji
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "38657dc9ba11"
down_revision: Union[str, None] = "y5z6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Discord カスタム絵文字パターン (<:name:id> or <a:name:id>)
import re

_CUSTOM_EMOJI_RE = re.compile(r"^<a?:\w+:\d+>$")


def _normalize_emoji(text: str) -> str:
    """src/utils.py の normalize_emoji と同じロジック (マイグレーション用コピー)."""
    if not text:
        return text
    if _CUSTOM_EMOJI_RE.match(text):
        return text
    normalized = unicodedata.normalize("NFC", text)
    if "\u200d" in normalized:
        return normalized
    if "\ufe0f" in normalized:
        stripped = normalized.replace("\ufe0f", "")
        if stripped and emoji.is_emoji(stripped):
            return stripped
    return normalized


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, emoji FROM role_panel_items")).fetchall()

    for row_id, old_emoji in rows:
        new_emoji = _normalize_emoji(old_emoji)
        if new_emoji != old_emoji:
            conn.execute(
                sa.text("UPDATE role_panel_items SET emoji = :new WHERE id = :id"),
                {"new": new_emoji, "id": row_id},
            )


def downgrade() -> None:
    # VS16 を元に戻すのは困難なため、downgrade は何もしない
    pass
