# アーキテクチャ

## 全体構成

```
Browser → Next.js (frontend) → FastAPI (api) → PostgreSQL ← Discord Bot
```

3 プロセス構成。同一 DB を共有。

## 技術スタック

### バックエンド (Python 3.12)

- **discord.py 2.x** — Discord Bot
- **FastAPI** — JSON API
- **SQLAlchemy 2.x (async)** — ORM
- **PostgreSQL 17** — DB
- **Alembic** — マイグレーション
- **PyJWT** — JWT 認証
- **bcrypt** — パスワードハッシュ
- **pytest** — テスト (3580 テスト)

### フロントエンド (Node.js 24)

- **Next.js 16** — App Router
- **React 19** — UI
- **TypeScript** — 型安全
- **Tailwind CSS v4** — スタイリング
- **shadcn/ui** — コンポーネント (ダークテーマ)
- **Vitest** — テスト (62 テスト)

### CI

- **GitHub Actions** — 5 ジョブ並列
- **Ruff** — Python lint / format
- **mypy** — Python 型チェック
- **ESLint** — Frontend lint
- **Prettier** — Frontend format
- **cspell** — スペルチェック (Python + Frontend)

## ディレクトリ構成

```
src/
├── main.py                    # Bot エントリーポイント
├── bot.py                     # Bot クラス
├── config.py                  # 設定管理
├── constants.py               # 定数
├── utils.py                   # ユーティリティ
├── cogs/                      # Bot 機能 (10 cogs)
│   ├── admin.py               # 管理コマンド
│   ├── voice.py               # 一時 VC
│   ├── bump.py                # Bump リマインダー
│   ├── sticky.py              # Sticky メッセージ
│   ├── role_panel.py          # ロールパネル
│   ├── ticket.py              # チケット
│   ├── automod.py             # AutoMod
│   ├── eventlog.py            # イベントログ (25 種類)
│   ├── _eventlog_helpers.py   # ログ Embed ヘルパー
│   ├── join_role.py           # 入室時ロール
│   └── health.py              # ヘルスチェック
├── core/                      # コア機能
├── database/
│   ├── engine.py              # SQLAlchemy エンジン
│   └── models.py              # DB モデル
├── services/                  # DB 操作 (9 ドメインサービス + ファサード)
├── ui/                        # Discord UI コンポーネント
└── web/
    ├── app.py                 # FastAPI アプリ (ファサード + re-export)
    ├── security.py            # 認証・セッション・レート制限
    ├── db_helpers.py          # DB クエリヘルパー
    ├── jwt_auth.py            # JWT 認証
    ├── discord_api.py         # Discord REST API
    ├── email_service.py       # メール送信
    └── routes/
        ├── api_auth.py        # /api/v1/auth
        ├── api_lobbies.py     # /api/v1/lobbies
        ├── api_sticky.py      # /api/v1/sticky
        ├── api_bump.py        # /api/v1/bump
        ├── api_rolepanel.py   # /api/v1/rolepanels
        ├── api_automod.py     # /api/v1/automod
        ├── api_ticket.py      # /api/v1/tickets
        ├── api_joinrole.py    # /api/v1/joinrole
        ├── api_eventlog.py    # /api/v1/eventlog
        ├── api_settings.py    # /api/v1/settings
        ├── api_misc.py        # /api/v1/health, activity
        └── (旧 HTML ルート)   # 廃止予定

frontend/
├── src/
│   ├── app/                   # Next.js ページ (25 ページ)
│   │   ├── login/
│   │   └── dashboard/
│   │       ├── lobbies/
│   │       ├── sticky/
│   │       ├── bump/
│   │       ├── automod/       # rules, new, edit, logs, banlist, settings
│   │       ├── roles/         # list, new, detail
│   │       ├── tickets/       # list, detail, panels/*
│   │       ├── joinrole/
│   │       ├── eventlog/
│   │       ├── activity/
│   │       ├── health/
│   │       ├── settings/
│   │       ├── maintenance/
│   │       └── banlogs/
│   ├── components/            # 再利用コンポーネント
│   │   ├── ui/                # shadcn/ui
│   │   ├── sidebar.tsx
│   │   ├── data-table.tsx
│   │   ├── delete-button.tsx
│   │   ├── toggle-button.tsx
│   │   └── guild-channel-selector.tsx
│   └── lib/
│       ├── api.ts             # サーバーサイド API クライアント
│       ├── client-api.ts      # クライアントサイド API クライアント
│       ├── types.ts           # 型定義
│       └── utils.ts           # cn() ユーティリティ
├── Dockerfile                 # 本番用
└── Dockerfile.dev             # 開発用
```

## API 設計

### 認証

- JWT (HttpOnly Cookie, HS256)
- `POST /api/v1/auth/login` でトークン発行
- Cookie `session` で認証状態管理

### エンドポイント (70+)

| プレフィックス | 内容 |
|---------------|------|
| `/api/v1/auth` | 認証 (login, logout, me, setup-status) |
| `/api/v1/lobbies` | ロビー管理 |
| `/api/v1/sticky` | Sticky メッセージ |
| `/api/v1/bump` | Bump 設定 + リマインダー |
| `/api/v1/rolepanels` | ロールパネル + アイテム + Discord 投稿 |
| `/api/v1/automod` | ルール CRUD + ログ + 設定 + BANリスト |
| `/api/v1/tickets` | チケット + パネル + カテゴリ |
| `/api/v1/joinrole` | 入室時ロール |
| `/api/v1/eventlog` | イベントログ設定 |
| `/api/v1/settings` | ダッシュボード + 設定 + メンテナンス |
| `/api/v1/health` | ヘルスチェック + モニタリング設定 |
| `/api/v1/activity` | Bot アクティビティ |
| `/api/v1/banlogs` | BAN ログ |

### Next.js → API 通信

- `next.config.ts` の `rewrites` で `/api/v1/*` を FastAPI にプロキシ
- サーバーコンポーネント: `lib/api.ts` (Cookie 転送)
- クライアントコンポーネント: `lib/client-api.ts` (同一オリジン)

## DB モデル

- `AdminUser` — 管理者
- `Lobby` / `VoiceSession` / `VoiceSessionMember` — 一時 VC
- `BumpConfig` / `BumpReminder` — Bump
- `StickyMessage` — Sticky
- `RolePanel` / `RolePanelItem` — ロールパネル
- `AutoModRule` / `AutoModConfig` / `AutoModLog` / `AutoModIntroPost` / `AutoModBanList` — AutoMod
- `BanLog` — BAN ログ
- `TicketCategory` / `TicketPanel` / `TicketPanelCategory` / `Ticket` — チケット
- `JoinRoleConfig` / `JoinRoleAssignment` — 入室時ロール
- `EventLogConfig` — イベントログ
- `DiscordGuild` / `DiscordChannel` / `DiscordRole` — Discord キャッシュ
- `SiteSettings` — サイト設定 (タイムゾーン)
- `HealthConfig` — ヘルスモニタリング
- `BotActivity` — Bot アクティビティ
- `ProcessedEvent` — イベント重複防止

## Multi-Instance 対策

デプロイ時に新旧インスタンスが同時稼働するため:

- **Interaction**: `defer()` で排他 (HTTPException で早期 return)
- **on_message 等**: DB アトミック操作で排他 (`claim_*` パターン)
- **冪等な操作にはガード不要**: `add_roles`, `ban`, DB upsert 等
