# Discord Util Bot - アーキテクチャ & 設計ドキュメント

このドキュメントは、プロジェクトの仕様・設計方針・実装詳細をまとめたものです。

## プロジェクト概要

Discord サーバー運営を支援する多機能 Bot。一時 VC 管理、チケットシステム、Bump リマインダー、Sticky メッセージ、ロールパネル、AutoBan、Web 管理画面を搭載。

### 技術スタック

- **Python 3.12**
- **discord.py 2.x** - Discord Bot フレームワーク
- **SQLAlchemy 2.x (async)** - ORM
- **PostgreSQL** - データベース
- **Alembic** - マイグレーション
- **FastAPI** - Web 管理画面
- **pydantic-settings** - 設定管理
- **pytest + pytest-asyncio** - テスト
- **Ruff** - リンター
- **mypy** - 型チェック

## ディレクトリ構成

```
src/
├── main.py              # エントリーポイント (SIGTERM ハンドラ含む)
├── bot.py               # Bot クラス (on_ready, Cog ローダー)
├── config.py            # pydantic-settings による環境変数管理
├── constants.py         # アプリケーション定数
├── utils.py             # ユーティリティ関数 (データ同期、日時フォーマット等)
├── cogs/
│   ├── admin.py         # 管理者用コマンド (/admin cleanup, /admin stats)
│   ├── voice.py         # VC 自動作成・削除、/vc コマンドグループ
│   ├── bump.py          # Bump リマインダー
│   ├── sticky.py        # Sticky メッセージ
│   ├── role_panel.py    # ロールパネル
│   ├── ticket.py        # チケットシステム
│   ├── autoban.py       # AutoBan (自動 BAN/キック)
│   └── health.py        # ヘルスチェック (ハートビート)
├── core/
│   ├── permissions.py   # Discord 権限ヘルパー
│   ├── validators.py    # 入力バリデーション
│   └── builders.py      # チャンネル作成ビルダー
├── database/
│   ├── engine.py        # SQLAlchemy 非同期エンジン (SSL/プール設定)
│   └── models.py        # DB モデル定義
├── services/
│   └── db_service.py    # DB CRUD 操作 (ビジネスロジック)
├── ui/
│   ├── control_panel.py # コントロールパネル UI (View/Button/Select)
│   ├── role_panel_view.py # ロールパネル UI (View/Button/Modal)
│   └── ticket_view.py  # チケット UI (View/Button/Modal)
└── web/
    ├── app.py           # FastAPI Web 管理画面
    ├── discord_api.py   # Discord REST API クライアント (パネル投稿等)
    ├── email_service.py # メール送信サービス (SMTP)
    └── templates.py     # HTML テンプレート

tests/
├── conftest.py          # pytest fixtures (DB セッション等)
├── test_utils.py        # utils.py のテスト
├── cogs/
│   ├── test_admin.py    # admin.py のテスト
│   ├── test_voice.py
│   ├── test_bump.py
│   ├── test_sticky.py
│   ├── test_role_panel.py
│   ├── test_ticket.py
│   ├── test_autoban.py
│   └── test_health.py
├── database/
│   ├── test_engine.py
│   ├── test_models.py
│   └── test_integration.py
├── ui/
│   ├── test_control_panel.py
│   ├── test_role_panel_view.py
│   └── test_ticket_view.py
├── services/
│   └── test_db_service.py
└── web/
    ├── test_app.py
    ├── test_discord_api.py # Discord REST API クライアントのテスト
    ├── test_email_service.py
    ├── test_lifespan.py # FastAPI lifespan のテスト
    └── test_templates.py # テンプレート関数のテスト
```

## データベースモデル

### AdminUser
Web 管理画面のログインユーザー。

```python
class AdminUser(Base):
    id: Mapped[int]                         # PK
    email: Mapped[str]                      # unique
    password_hash: Mapped[str]              # bcrypt ハッシュ
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    password_changed_at: Mapped[datetime | None]
    reset_token: Mapped[str | None]         # パスワードリセット用
    reset_token_expires_at: Mapped[datetime | None]
    pending_email: Mapped[str | None]       # メールアドレス変更待ち
    email_change_token: Mapped[str | None]
    email_change_token_expires_at: Mapped[datetime | None]
    email_verified: Mapped[bool]
```

### Lobby
ロビー VC の設定を保存。

```python
class Lobby(Base):
    id: Mapped[int]                    # PK
    guild_id: Mapped[str]              # Discord サーバー ID
    lobby_channel_id: Mapped[str]      # ロビー VC の ID (unique)
    category_id: Mapped[str | None]    # 作成先カテゴリ ID
    default_user_limit: Mapped[int]    # デフォルト人数制限 (0 = 無制限)
    # relationship: sessions -> VoiceSession[]
```

### VoiceSession
作成された一時 VC を追跡。

```python
class VoiceSession(Base):
    id: Mapped[int]                    # PK
    lobby_id: Mapped[int]              # FK -> Lobby
    channel_id: Mapped[str]            # 作成された VC の ID (unique)
    owner_id: Mapped[str]              # オーナーの Discord ID
    name: Mapped[str]                  # チャンネル名
    user_limit: Mapped[int]            # 人数制限
    is_locked: Mapped[bool]            # ロック状態
    is_hidden: Mapped[bool]            # 非表示状態
    created_at: Mapped[datetime]
    # relationship: lobby -> Lobby
```

### VoiceSessionMember
VC 参加者の join 時刻を記録 (オーナー引き継ぎ用)。

```python
class VoiceSessionMember(Base):
    id: Mapped[int]
    voice_session_id: Mapped[int]      # FK -> VoiceSession (CASCADE)
    user_id: Mapped[str]
    joined_at: Mapped[datetime]
    # unique constraint: (voice_session_id, user_id)
```

### BumpConfig
Bump 監視の設定。

```python
class BumpConfig(Base):
    guild_id: Mapped[str]              # PK
    channel_id: Mapped[str]            # 監視対象チャンネル
    created_at: Mapped[datetime]
```

### BumpReminder
Bump リマインダーの状態。

```python
class BumpReminder(Base):
    id: Mapped[int]
    guild_id: Mapped[str]
    channel_id: Mapped[str]
    service_name: Mapped[str]          # "DISBOARD" or "ディス速報"
    remind_at: Mapped[datetime | None] # 次回リマインド時刻
    is_enabled: Mapped[bool]           # 通知有効/無効
    role_id: Mapped[str | None]        # カスタム通知ロール ID
    # unique constraint: (guild_id, service_name)
```

### StickyMessage
Sticky メッセージの設定。

```python
class StickyMessage(Base):
    channel_id: Mapped[str]            # PK
    guild_id: Mapped[str]
    message_id: Mapped[str | None]     # 現在の sticky メッセージ ID
    message_type: Mapped[str]          # "embed" or "text"
    title: Mapped[str]
    description: Mapped[str]
    color: Mapped[int | None]
    cooldown_seconds: Mapped[int]      # 再投稿までの最小間隔
    last_posted_at: Mapped[datetime | None]
    created_at: Mapped[datetime]
```

### RolePanel
ロールパネルの設定。

```python
class RolePanel(Base):
    id: Mapped[int]                    # PK
    guild_id: Mapped[str]              # Discord サーバー ID
    channel_id: Mapped[str]            # パネルを設置するチャンネル ID
    message_id: Mapped[str | None]     # パネルメッセージ ID
    panel_type: Mapped[str]            # "button" or "reaction"
    title: Mapped[str]                 # パネルタイトル
    description: Mapped[str | None]    # パネル説明文
    color: Mapped[int | None]          # Embed 色
    remove_reaction: Mapped[bool]      # リアクション自動削除
    use_embed: Mapped[bool]            # メッセージ形式 (True: Embed, False: Text)
    created_at: Mapped[datetime]
    # relationship: items -> RolePanelItem[]
```

### RolePanelItem
ロールパネルのロールアイテム。

```python
class RolePanelItem(Base):
    id: Mapped[int]                    # PK
    panel_id: Mapped[int]              # FK -> RolePanel (CASCADE)
    role_id: Mapped[str]               # 付与するロール ID
    emoji: Mapped[str]                 # ボタン/リアクション用絵文字
    label: Mapped[str | None]          # ボタンラベル (ボタン式のみ)
    style: Mapped[str]                 # ボタンスタイル (primary/secondary/success/danger)
    position: Mapped[int]              # 表示順序
    # unique constraint: (panel_id, emoji)
```

### TicketCategory
チケットカテゴリの設定。

```python
class TicketCategory(Base):
    id: Mapped[int]                    # PK
    guild_id: Mapped[str]              # Discord サーバー ID
    name: Mapped[str]                  # カテゴリ名 (例: "General Support")
    staff_role_id: Mapped[str]         # スタッフロール ID
    discord_category_id: Mapped[str | None]  # チケットチャンネル配置先カテゴリ
    channel_prefix: Mapped[str]        # チャンネル名接頭辞 (default "ticket-")
    form_questions: Mapped[str | None] # JSON 配列、最大5問
    is_enabled: Mapped[bool]           # 有効/無効
    created_at: Mapped[datetime]
    # relationship: panel_associations -> TicketPanelCategory[]
    # relationship: tickets -> Ticket[]
```

### TicketPanel
チケットパネル (Discord に送信される Embed + ボタン)。

```python
class TicketPanel(Base):
    id: Mapped[int]                    # PK
    guild_id: Mapped[str]              # Discord サーバー ID
    channel_id: Mapped[str]            # パネル送信先チャンネル
    message_id: Mapped[str | None]     # Discord メッセージ ID
    title: Mapped[str]                 # パネルタイトル
    description: Mapped[str | None]    # パネル説明
    created_at: Mapped[datetime]
    # relationship: category_associations -> TicketPanelCategory[]
```

### TicketPanelCategory
パネルとカテゴリの結合テーブル。

```python
class TicketPanelCategory(Base):
    id: Mapped[int]                    # PK
    panel_id: Mapped[int]              # FK -> TicketPanel (CASCADE)
    category_id: Mapped[int]           # FK -> TicketCategory (CASCADE)
    button_label: Mapped[str | None]   # ラベル上書き
    button_style: Mapped[str]          # ボタンスタイル (default "primary")
    button_emoji: Mapped[str | None]   # ボタン絵文字
    position: Mapped[int]              # 表示順序
    # unique constraint: (panel_id, category_id)
```

### Ticket
チケット本体。

```python
class Ticket(Base):
    id: Mapped[int]                    # PK
    guild_id: Mapped[str]              # Discord サーバー ID
    channel_id: Mapped[str | None]     # チケットチャンネル ID (クローズ後 None)
    user_id: Mapped[str]               # 作成者の Discord ID
    username: Mapped[str]              # 作成時のユーザー名
    category_id: Mapped[int]           # FK -> TicketCategory
    status: Mapped[str]                # "open" | "claimed" | "closed"
    claimed_by: Mapped[str | None]     # 担当スタッフ名
    closed_by: Mapped[str | None]      # クローズしたユーザー名
    close_reason: Mapped[str | None]   # クローズ理由
    transcript: Mapped[str | None]     # トランスクリプト全文 (Text)
    ticket_number: Mapped[int]         # ギルド内連番
    form_answers: Mapped[str | None]   # JSON 文字列
    created_at: Mapped[datetime]
    closed_at: Mapped[datetime | None]
    # unique constraint: (guild_id, ticket_number)
    # relationship: category -> TicketCategory
```

### AutoBanRule
AutoBan ルールの設定。

```python
class AutoBanRule(Base):
    id: Mapped[int]                       # PK
    guild_id: Mapped[str]                 # Discord サーバー ID
    rule_type: Mapped[str]                # "username_match" | "account_age" | "no_avatar"
                                          # | "role_acquired" | "vc_join" | "message_post"
    is_enabled: Mapped[bool]              # 有効/無効
    action: Mapped[str]                   # "ban" | "kick"
    pattern: Mapped[str | None]           # マッチパターン (username_match 用)
    use_wildcard: Mapped[bool]            # 部分一致 (username_match 用)
    threshold_hours: Mapped[int | None]   # アカウント年齢閾値 (時間、account_age 用、最大 336)
    threshold_seconds: Mapped[int | None] # JOIN後の閾値 (秒、role_acquired/vc_join/message_post 用、最大 3600)
    created_at: Mapped[datetime]
    # relationship: logs -> AutoBanLog[]
```

### AutoBanConfig
AutoBan のギルドごと設定 (ログチャンネル)。

```python
class AutoBanConfig(Base):
    guild_id: Mapped[str]              # PK (1ギルド1設定)
    log_channel_id: Mapped[str | None] # BAN/KICK ログ送信先チャンネル ID
```

### AutoBanLog
AutoBan 実行ログ。

```python
class AutoBanLog(Base):
    id: Mapped[int]                    # PK
    guild_id: Mapped[str]              # Discord サーバー ID
    user_id: Mapped[str]               # 対象ユーザー ID
    username: Mapped[str]              # 対象ユーザー名
    rule_id: Mapped[int]               # FK -> AutoBanRule (CASCADE)
    action_taken: Mapped[str]          # 実行されたアクション ("banned" | "kicked")
    reason: Mapped[str]                # 理由
    created_at: Mapped[datetime]
    # relationship: rule -> AutoBanRule
```

### DiscordGuild
ギルド情報のキャッシュ (Web 管理画面用)。

```python
class DiscordGuild(Base):
    guild_id: Mapped[str]              # PK
    guild_name: Mapped[str]            # サーバー名
    icon_hash: Mapped[str | None]      # アイコンハッシュ
    member_count: Mapped[int]          # メンバー数
    updated_at: Mapped[datetime]
```

### DiscordChannel
チャンネル情報のキャッシュ (Web 管理画面用)。

```python
class DiscordChannel(Base):
    id: Mapped[int]                    # PK
    guild_id: Mapped[str]              # Discord サーバー ID
    channel_id: Mapped[str]            # チャンネル ID
    channel_name: Mapped[str]          # チャンネル名
    channel_type: Mapped[int]          # チャンネルタイプ
    position: Mapped[int]              # 表示順序
    category_id: Mapped[str | None]    # 親カテゴリ ID
    updated_at: Mapped[datetime]
    # unique constraint: (guild_id, channel_id)
```

### DiscordRole
ロール情報のキャッシュ (Web 管理画面用)。

```python
class DiscordRole(Base):
    id: Mapped[int]                    # PK
    guild_id: Mapped[str]              # Discord サーバー ID
    role_id: Mapped[str]               # ロール ID
    role_name: Mapped[str]             # ロール名
    color: Mapped[int]                 # ロール色
    position: Mapped[int]              # 表示順序
    updated_at: Mapped[datetime]
    # unique constraint: (guild_id, role_id)
```

## 主要機能の設計

### 1. 一時 VC 機能 (`voice.py` + `control_panel.py`)

#### フロー
1. ユーザーがロビー VC に参加
2. `on_voice_state_update` でイベント検知
3. `VoiceSession` を DB に作成
4. 新しい VC を作成し、ユーザーを移動
5. コントロールパネル Embed + View を送信

#### コントロールパネル
- **永続 View**: `timeout=None` で Bot 再起動後もボタンが動作
- **custom_id**: `{action}:{voice_session_id}` 形式で識別
- **オーナー権限チェック**: 各ボタンの callback で `voice_session.owner_id` と比較

#### パネルボタン (4行構成)
- Row 1: 名前変更、人数制限、ビットレート、リージョン
- Row 2: ロック、非表示、年齢制限、譲渡
- Row 3: キック
- Row 4: ブロック、許可、カメラ禁止、カメラ許可

#### カメラ禁止機能
- `PermissionOverwrite(stream=False)` で配信権限を拒否
- Discord の `stream` 権限はカメラと画面共有の両方を制御
- 解除時は `PermissionOverwrite(stream=None)` で上書きを削除

#### パネル更新方式
- **`refresh_panel_embed()`**: 既存メッセージを `msg.edit()` で更新 (通常の設定変更時)
- **`repost_panel()`**: 旧パネル削除 → 新パネル送信 (オーナー譲渡時、`/panel` コマンド)

### 2. Bump リマインダー機能 (`bump.py`)

#### 対応サービス
| サービス | Bot ID | 検知キーワード |
|---------|--------|---------------|
| DISBOARD | 302050872383242240 | "表示順をアップ" (embed.description) |
| ディス速報 | 761562078095867916 | "アップ" (embed.title/description/message.content) |

#### 検知フロー
1. `on_message` で DISBOARD/ディス速報 Bot のメッセージを監視
2. `_detect_bump_success()` で bump 成功を判定
3. ユーザーが `Server Bumper` ロールを持っているか確認
4. `BumpReminder` を DB に upsert (remind_at = now + 2時間)
5. 検知 Embed + 通知設定ボタンを送信

#### リマインダー送信
- `@tasks.loop(seconds=30)` でループタスク実行
- `get_due_bump_reminders()` で送信予定時刻を過ぎたリマインダーを取得
- 通知先ロール (カスタム or デフォルト) にメンションして Embed 送信
- 送信後 `remind_at` をクリア

#### 通知設定 UI
- **BumpNotificationView**: 通知有効/無効トグル + ロール変更ボタン
- **BumpRoleSelectView**: ロール選択セレクトメニュー + デフォルトに戻すボタン
- サービスごと (DISBOARD/ディス速報) に独立して設定可能

### 3. Sticky メッセージ機能 (`sticky.py`)

#### フロー
1. `/sticky set` コマンドで設定 (Embed or Text を選択)
2. モーダルでタイトル・説明文・色・遅延を入力
3. `StickyMessage` を DB に保存
4. 初回 sticky メッセージを投稿

#### 再投稿フロー
1. `on_message` で新規メッセージを監視
2. 設定されているチャンネルならペンディング処理を開始
3. デバウンス: 遅延秒数後に再投稿 (連続投稿時は最後の1回のみ実行)
4. 古い sticky メッセージを削除
5. 新しい sticky メッセージを投稿
6. DB の `message_id` と `last_posted_at` を更新

#### デバウンス方式
```python
# ペンディングタスクを管理
_pending_tasks: dict[str, asyncio.Task[None]] = {}

async def _schedule_repost(channel_id: str, delay: float):
    # 既存タスクがあればキャンセル
    if channel_id in _pending_tasks:
        _pending_tasks[channel_id].cancel()
    # 新しいタスクをスケジュール
    _pending_tasks[channel_id] = asyncio.create_task(_delayed_repost(...))
```

### 4. ロールパネル機能 (`role_panel.py` + `role_panel_view.py` + `discord_api.py`)

#### 概要
ボタンまたはリアクションでロールを付与/解除できるパネルを作成する機能。
Web 管理画面からパネルを作成し、Discord に投稿・更新できる。

#### パネルタイプ
| タイプ | 説明 |
|--------|------|
| button | ボタンをクリックしてロールをトグル |
| reaction | 絵文字リアクションでロールをトグル |

#### メッセージ形式
| 形式 | 説明 |
|------|------|
| Embed | カラー付きの埋め込みメッセージ (カスタムカラー設定可能) |
| Text | プレーンテキストメッセージ |

#### フロー (ボタン式)
1. `/rolepanel create button` → Modal でタイトル・説明入力 → Embed 送信
2. `/rolepanel add @role 🎮 "ゲーマー"` → パネルにボタン追加
3. ユーザーがボタンクリック → ロール付与/解除 (トグル)

#### フロー (リアクション式)
1. `/rolepanel create reaction` → Modal でタイトル・説明入力 → Embed 送信
2. `/rolepanel add @role 🎮` → パネルにリアクション追加 (Bot が絵文字を付ける)
3. ユーザーがリアクション → ロール付与、リアクション外す → 解除

#### Web 管理画面からの作成フロー
1. `/rolepanels/new` → フォームでサーバー・チャンネル・タイトル・色等を入力
2. ロールアイテムを追加 (ドラッグ&ドロップで並べ替え可能)
3. パネルを作成 → DB に保存
4. 詳細ページから「Post to Discord」ボタンで Discord に投稿
5. `discord_api.py` が Discord REST API を直接呼び出してメッセージ送信

#### Discord REST API クライアント (`discord_api.py`)
Bot と Web アプリが別プロセスで動作するため、Web 画面からの投稿/更新は
Discord REST API を直接使用する。

```python
async def post_role_panel_to_discord(panel, items) -> tuple[bool, str | None, str | None]:
    """パネルを Discord に投稿 (新規)"""

async def edit_role_panel_in_discord(panel, items) -> tuple[bool, str | None]:
    """既存のパネルメッセージを編集"""

async def add_reactions_to_message(channel_id, message_id, items) -> tuple[bool, str | None]:
    """リアクション式パネルに絵文字リアクションを追加"""
```

#### 永続 View 設計
```python
class RolePanelView(discord.ui.View):
    def __init__(self, panel_id: int, items: list[RolePanelItem]):
        super().__init__(timeout=None)  # 永続
        self.panel_id = panel_id
        for item in items:
            self.add_item(RoleButton(panel_id, item))

class RoleButton(discord.ui.Button):
    # custom_id = f"role_panel:{panel_id}:{item_id}"
```

Bot 起動時に全パネルの View を登録:
```python
async def cog_load(self):
    for panel in await get_all_role_panels(session):
        items = await get_role_panel_items(session, panel.id)
        view = RolePanelView(panel.id, items)
        self.bot.add_view(view)
```

### 5. チケットシステム (`ticket.py` + `ticket_view.py`)

#### 概要
パネルベースのサポートチケットシステム。カテゴリごとにフォーム質問を設定でき、
プライベートチャンネルでスタッフが対応、クローズ時にトランスクリプトを保存する。

#### フロー
1. Web 管理画面からカテゴリとパネルを作成
2. パネルを Discord に投稿 (Embed + カテゴリボタン)
3. ユーザーがボタンをクリック → フォームモーダル表示
4. 回答送信 → プライベートチャンネル作成 + 開始 Embed 送信
5. スタッフが Claim ボタンで担当割り当て
6. `/ticket close` or Close ボタン → トランスクリプト保存 → チャンネル削除

#### チャンネル権限
```python
overwrites = {
    guild.default_role: PermissionOverwrite(view_channel=False),
    user: PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
    guild.me: PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
    staff_role: PermissionOverwrite(view_channel=True, send_messages=True),
}
```

#### 永続 View
- `TicketPanelView`: パネルの各カテゴリボタン (`custom_id: "ticket_panel:{panel_id}:{category_id}"`)
- `TicketControlView`: チケットチャンネル内の Claim/Close ボタン (`custom_id: "ticket_ctrl:{ticket_id}:..."`)
- `_sync_views_task` (60秒ループ): Web 管理画面で作成されたパネルを Bot 側に同期

#### トランスクリプト形式
```
=== Ticket #42 - General Support ===
Created by: username (123456789)
Created at: 2026-02-07 19:00

[2026-02-07 19:00:05] username: Hello, I need help
[2026-02-07 19:00:10] staff_user: How can I help you?
=== Closed by: staff_user at 2026-02-07 19:30 ===
```

#### イベントリスナー
- `on_guild_channel_delete`: チケットチャンネルが外部削除された場合の DB クリーンアップ
- `on_raw_message_delete`: パネルメッセージが削除された場合の DB クリーンアップ

### 6. AutoBan 機能 (`autoban.py`)

#### 概要
ルールに基づいてメンバーを自動 BAN/キックする。参加時チェック (username_match, account_age, no_avatar) と、参加後の行動チェック (role_acquired, vc_join, message_post) の2種類がある。

#### ルールタイプ
| タイプ | 説明 | イベント |
|--------|------|---------|
| `username_match` | ユーザー名パターンマッチ (完全一致/部分一致) | `on_member_join` |
| `account_age` | アカウント作成から N 時間以内 (最大 336h = 14日) | `on_member_join` |
| `no_avatar` | デフォルトアバター (アバター未設定) | `on_member_join` |
| `role_acquired` | JOIN 後 N 秒以内にロール取得 (最大 3600s) | `on_member_update` |
| `vc_join` | JOIN 後 N 秒以内に VC 参加 (最大 3600s) | `on_voice_state_update` |
| `message_post` | JOIN 後 N 秒以内にメッセージ投稿 (最大 3600s) | `on_message` |

#### イベントリスナー
- `on_member_join`: username_match, account_age, no_avatar ルールを評価
- `on_member_update`: `before.roles` vs `after.roles` でロール追加を検出 → role_acquired ルールを評価
- `on_voice_state_update`: VC 新規参加 (チャンネル移動は対象外) → vc_join ルールを評価
- `on_message`: メンバーのメッセージ投稿 → message_post ルールを評価

#### フロー
1. イベント検知 (Bot は無視)
2. ギルドの有効ルールを取得
3. 対象ルールタイプの条件をチェック
4. マッチ → BAN or キック実行 (メンバー情報を事前保存)
5. ログを DB に保存
6. `AutoBanConfig` にログチャンネルが設定されていれば Embed を送信

#### ログ Embed
BAN/KICK 実行時、`AutoBanConfig.log_channel_id` にリッチ Embed を送信:
- ユーザー情報 (名前、ID、アバター)
- アクション (BANNED/KICKED)
- 適用ルール (ID + タイプ)
- 理由
- アカウント作成日時、サーバー参加日時 (経過秒数付き)

#### スラッシュコマンド
- `/autoban add`: ルール追加 (タイプ・パターン・アクション・閾値等)
- `/autoban remove`: ルール削除
- `/autoban list`: ルール一覧表示
- `/autoban logs`: 実行ログ表示

### 7. 管理者コマンド (`admin.py`)

Bot オーナー/管理者用のメンテナンスコマンド。

#### /admin cleanup
ボットが退出したサーバー (orphaned) のデータをクリーンアップ。

```
1. 全 Lobby, BumpConfig, StickyMessage, RolePanel を取得
2. 現在参加しているギルド ID のセットを作成
3. 参加していないギルドのデータを削除
   - Bump の場合、チャンネルが削除されている場合も削除
4. 削除結果を Embed で報告
```

#### /admin stats
データベース統計情報を表示。

```
- ロビー数 (総数/孤立数)
- Bump 設定数 (総数/孤立数)
- Sticky メッセージ数 (総数/孤立数)
- ロールパネル数 (総数/孤立数)
- チケットカテゴリ数 (総数/孤立数)
- AutoBan ルール数 (総数/孤立数)
- 参加ギルド数
```

### 8. Web 管理画面 (`web/app.py`)

#### 認証フロー
1. 初回起動時: 環境変数の `ADMIN_EMAIL` / `ADMIN_PASSWORD` で管理者作成
2. ログイン: メール + パスワードで認証
3. セッション: 署名付き Cookie (itsdangerous)
4. パスワードリセット: SMTP 経由でリセットリンクを送信

#### セキュリティ機能
- **レート制限**: 5分間で5回までのログイン試行
- **セキュア Cookie**: HTTPS 環境でのみ Cookie 送信 (設定可能)
- **セッション有効期限**: 24時間
- **パスワードハッシュ**: bcrypt

#### エンドポイント
| パス | 説明 |
|------|------|
| `/` | ダッシュボード (ログイン必須) |
| `/login` | ログイン画面 |
| `/logout` | ログアウト |
| `/lobbies` | ロビー一覧 (サーバー名/チャンネル名表示) |
| `/bump` | Bump 設定一覧 (サーバー名/チャンネル名表示) |
| `/sticky` | Sticky メッセージ一覧 (サーバー名/チャンネル名表示) |
| `/rolepanels` | ロールパネル一覧 (サーバー名/チャンネル名表示) |
| `/rolepanels/new` | ロールパネル作成 (カラー選択・ロールアイテム設定) |
| `/rolepanels/{id}` | ロールパネル詳細・編集・Discord 投稿/更新 |
| `/rolepanels/{id}/post` | パネルを Discord に投稿 (POST) |
| `/rolepanels/{id}/items/{item_id}/delete` | ロールアイテム削除 |
| `/rolepanels/{id}/delete` | ロールパネル削除 |
| `/tickets` | チケット一覧 |
| `/tickets/categories` | チケットカテゴリ一覧 |
| `/tickets/categories/new` | チケットカテゴリ作成 |
| `/tickets/panels` | チケットパネル一覧 |
| `/tickets/panels/new` | チケットパネル作成 |
| `/tickets/panels/{id}/delete` | チケットパネル削除 (POST) |
| `/tickets/{ticket_id}` | チケット詳細・トランスクリプト |
| `/autoban` | AutoBan ルール一覧 |
| `/autoban/new` | AutoBan ルール作成 |
| `/autoban/{rule_id}/delete` | AutoBan ルール削除 (POST) |
| `/autoban/{rule_id}/toggle` | AutoBan ルール有効/無効切替 (POST) |
| `/autoban/logs` | AutoBan 実行ログ |
| `/autoban/settings` | AutoBan 設定 (ログチャンネル) |
| `/settings` | 設定画面 (パスワード変更等) |
| `/settings/maintenance` | メンテナンス画面 (統計/クリーンアップ) |
| `/forgot-password` | パスワードリセット |

#### サーバー名/チャンネル名表示機能
一覧ページでは、DiscordGuild/DiscordChannel キャッシュを使用して:
- キャッシュがある場合: サーバー名/チャンネル名を表示 (ID は小さくグレー)
- キャッシュがない場合: ID を黄色で表示 (孤立データの可能性)

#### メンテナンス画面
- **統計表示**: 各機能のレコード数と孤立数
- **リフレッシュ**: 統計を再計算
- **クリーンアップ**: 確認モーダル付きで孤立データを削除
  - 削除対象の内訳を表示
  - 合計件数を確認後に実行

### 9. Graceful シャットダウン (`main.py`)

#### SIGTERM ハンドラ
```python
def _handle_sigterm(_signum: int, _frame: FrameType | None) -> None:
    """Heroku のシャットダウン時に SIGTERM を受信"""
    logger.info("Received SIGTERM signal, initiating graceful shutdown...")
    if _bot is not None:
        asyncio.create_task(_shutdown_bot())

async def _shutdown_bot() -> None:
    """Bot を安全に停止"""
    if _bot is not None:
        await _bot.close()
```

### 10. Discord データ同期 (`utils.py`)

Bot が参加しているギルド/チャンネル/ロール情報を DB にキャッシュする。

```python
async def sync_discord_data(bot: commands.Bot, session: AsyncSession) -> None:
    """Bot 参加中の全ギルド情報を同期"""
    for guild in bot.guilds:
        # ギルド情報を upsert
        await upsert_discord_guild(session, guild)
        # チャンネル情報を同期 (テキスト系のみ)
        await sync_guild_channels(session, guild)
        # ロール情報を同期
        await sync_guild_roles(session, guild)
```

#### 同期タイミング
- Bot 起動時 (`on_ready`)
- ギルド参加/退出時
- チャンネル/ロール変更時 (イベント)

### 11. データベース接続設定 (`database/engine.py`)

#### SSL 接続 (Heroku 対応)
```python
DATABASE_REQUIRE_SSL = os.environ.get("DATABASE_REQUIRE_SSL", "").lower() == "true"

def _get_connect_args() -> dict[str, Any]:
    if DATABASE_REQUIRE_SSL:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False  # 自己署名証明書
        ssl_context.verify_mode = ssl.CERT_NONE
        return {"ssl": ssl_context}
    return {}
```

#### コネクションプール
```python
POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "5"))
MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW", "10"))

engine = create_async_engine(
    settings.async_database_url,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_pre_ping=True,  # 接続前にpingして無効な接続を検出
    connect_args=_get_connect_args(),
)
```

### 12. タイムゾーン設定 (`config.py` + `utils.py`)

`TIMEZONE_OFFSET` 環境変数で UTC からのオフセット (時間) を指定。
Web 管理画面とトランスクリプトの全日時表示に適用される。

```python
# config.py
timezone_offset: int = 0  # UTC offset in hours (例: 9 = JST)

# utils.py
def format_datetime(dt: datetime | None, fmt: str = "%Y-%m-%d %H:%M", *, fallback: str = "-") -> str:
    """settings.timezone_offset に基づいてローカル日時にフォーマット。"""
    if dt is None:
        return fallback
    tz = timezone(timedelta(hours=settings.timezone_offset))
    return dt.astimezone(tz).strftime(fmt)
```

適用箇所: `ticket_view.py` (トランスクリプト 3箇所)、`templates.py` (Web 管理画面 9箇所)

## 設計原則

### 1. 非同期ファースト
- 全ての DB 操作は `async/await`
- `asyncpg` ドライバを使用
- Cog のイベントハンドラも全て非同期

### 2. DB セッション管理
```python
# コンテキストマネージャで自動 commit/rollback
async with async_session() as session:
    result = await some_db_operation(session, ...)
```

### 3. 永続 View パターン
```python
class MyView(discord.ui.View):
    def __init__(self, some_id: int, ...):
        super().__init__(timeout=None)  # 永続化
        # custom_id に識別子を含める
        self.button.custom_id = f"action:{some_id}"
```

Bot 起動時にダミー View を登録:
```python
async def setup(bot):
    bot.add_view(MyView(0, ...))  # custom_id のプレフィックスでマッチ
```

### 4. エラーハンドリング
```python
# Discord API エラーは suppress で握りつぶすことが多い
with contextlib.suppress(discord.HTTPException):
    await message.delete()
```

### 5. 型ヒント
- 全ての関数に型ヒントを付与
- `mypy --strict` でチェック
- `Mapped[T]` で SQLAlchemy モデルの型を明示

### 6. ドキュメント (docstring)
Google スタイルの docstring を使用:
```python
def function(arg1: str, arg2: int) -> bool:
    """関数の説明。

    Args:
        arg1 (str): 引数1の説明。
        arg2 (int): 引数2の説明。

    Returns:
        bool: 返り値の説明。

    Raises:
        ValueError: エラーの説明。

    Examples:
        使用例::

            result = function("foo", 42)

    See Also:
        - :func:`related_function`: 関連する関数
    """
```

## テスト方針

### モック戦略
- `discord.py` のオブジェクトは `MagicMock(spec=discord.XXX)` でモック
- DB 操作は `patch("src.xxx.async_session")` でセッションをモック
- 個別の DB 関数も `patch()` でモック

### テストヘルパー
```python
def _make_message(...) -> MagicMock:
    """Discord Message のモックを作成"""

def _make_member(has_target_role: bool) -> MagicMock:
    """Discord Member のモックを作成"""

def _make_reminder(...) -> MagicMock:
    """BumpReminder のモックを作成"""
```

### テスト実行
```bash
# 通常実行
DISCORD_TOKEN=test-token pytest

# カバレッジ付き
DISCORD_TOKEN=test-token pytest --cov --cov-report=term-missing

# 特定ファイル
DISCORD_TOKEN=test-token pytest tests/cogs/test_bump.py -v
```

## 実装時の注意点

### 1. Discord ID は文字列で保存
- DB には `str` で保存 (bigint の精度問題を回避)
- 使用時に `int()` で変換

### 2. ロール検索
```python
# 名前で検索 (デフォルトロール)
role = discord.utils.get(guild.roles, name="Server Bumper")

# ID で検索 (カスタムロール)
role = guild.get_role(int(role_id))
```

### 3. Discord タイムスタンプ
```python
ts = int(datetime_obj.timestamp())
f"<t:{ts}:t>"  # 短い時刻 (例: 21:30)
f"<t:{ts}:R>"  # 相対時刻 (例: 2時間後)
f"<t:{ts}:F>"  # フル表示 (例: 2024年1月15日 21:30)
```

### 4. Embed の description は改行で構造化
```python
description = (
    f"**項目1:** {value1}\n"
    f"**項目2:** {value2}\n\n"
    f"説明文..."
)
```

### 5. 環境変数の URL 変換
```python
# Heroku は postgres:// を使用、SQLAlchemy は postgresql+asyncpg:// を要求
@property
def async_database_url(self) -> str:
    url = self.database_url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url
```

## よくあるタスク

### 新しいボタンを追加
1. `control_panel.py` の `ControlPanelView` にボタンを追加
2. callback でオーナー権限チェック
3. 処理後に `refresh_panel_embed()` または `repost_panel()` を呼ぶ
4. テストを追加

### 新しいスラッシュコマンドを追加
1. 適切な Cog に `@app_commands.command()` を追加
2. ギルド専用なら最初に `interaction.guild` をチェック
3. `interaction.response.send_message()` で応答
4. テストを追加

### DB モデルを変更
1. `models.py` を編集
2. `alembic revision --autogenerate -m "説明"` でマイグレーション生成
3. `alembic upgrade head` で適用
4. 関連する `db_service.py` の関数を更新
5. テストを更新

### 新しい Cog を追加
1. `src/cogs/` に新しいファイルを作成
2. `Cog` クラスを定義し、`setup()` 関数をエクスポート
3. `bot.py` の `setup_hook()` で `load_extension()` を追加
4. テストを追加

### 新しい Web エンドポイントを追加
1. `src/web/app.py` にルートを追加
2. 認証が必要なら `get_current_user()` を Depends に追加
3. テンプレートが必要なら `src/web/templates.py` に追加
4. テストを追加

## CI/CD

### GitHub Actions
- cspell (スペルチェック)
- JSON / YAML / TOML lint (構文チェック)
- Ruff format (フォーマットチェック)
- Ruff check (リンター)
- mypy 型チェック
- pytest + Codecov (カバレッジ 98%+)

### Heroku デプロイ
- `main` ブランチへの push でテストが実行される
- GitHub Actions で手動トリガーによりテスト → デプロイ
- デプロイ = Bot 再起動
- SIGTERM で graceful シャットダウン

**ローカルからの手動デプロイは禁止**
- バージョンの齟齬が発生する可能性がある
- テストの見逃しが起こる可能性がある
- 必ず GitHub Actions 経由でデプロイすること

### 必要な環境変数 (Heroku)
```
DISCORD_TOKEN=xxx
DATABASE_URL=(自動設定)
DATABASE_REQUIRE_SSL=true
```

## 関連リンク

- [discord.py ドキュメント](https://discordpy.readthedocs.io/)
- [SQLAlchemy 2.0 ドキュメント](https://docs.sqlalchemy.org/en/20/)
- [FastAPI ドキュメント](https://fastapi.tiangolo.com/)
- [Alembic ドキュメント](https://alembic.sqlalchemy.org/)
- [DISBOARD](https://disboard.org/)
