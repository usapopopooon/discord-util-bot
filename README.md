# Discord Util Bot

[![CI](https://github.com/usapopopooon/discord-util-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/usapopopooon/discord-util-bot/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/usapopopooon/discord-util-bot/graph/badge.svg)](https://codecov.io/gh/usapopopooon/discord-util-bot)

Discord サーバー運営を支援する多機能 Bot + Web 管理画面。

## アーキテクチャ

```
Browser → Next.js (frontend) → FastAPI (api) → PostgreSQL ← Discord Bot
```

| サービス | 技術 | 役割 |
|----------|------|------|
| **bot** | Python / discord.py | Discord Gateway 接続 |
| **api** | Python / FastAPI | JSON API (管理画面バックエンド) |
| **frontend** | Next.js / React 19 / shadcn/ui | 管理画面 UI |
| **db** | PostgreSQL 17 | データベース |

## 機能

- **一時 VC**: ロビー参加で個人用 VC 自動作成、ボタン UI で管理
- **Bump リマインダー**: DISBOARD / ディス速報 の bump 検出 → 2時間後通知
- **Sticky メッセージ**: チャンネル最下部に常駐するメッセージ
- **チケットシステム**: パネル + ボタンでチケット作成、スタッフ対応、トランスクリプト保存
- **ロールパネル**: ボタン式 / リアクション式のロール自動付与
- **AutoMod**: 8種類のルール (ユーザー名、アカウント年齢、アバター、タイミング系、自己紹介必須) + BANリスト
- **イベントログ**: 25種類のサーバーイベントを記録 (Carl-bot 風カラー)
- **入室時ロール**: メンバー参加時に時限ロール自動付与
- **Web 管理画面**: 全機能の設定・管理・ログ閲覧

## プロジェクト構成

```
├── src/                          # Python バックエンド
│   ├── main.py                   # Bot エントリーポイント
│   ├── bot.py                    # Bot クラス
│   ├── config.py                 # 設定管理
│   ├── constants.py              # 定数
│   ├── utils.py                  # ユーティリティ
│   ├── cogs/                     # Discord Bot 機能 (10 cogs)
│   ├── database/                 # SQLAlchemy モデル + エンジン
│   ├── services/                 # DB 操作 (ドメイン別 9 サービス + ファサード)
│   ├── ui/                       # Discord UI コンポーネント
│   └── web/                      # FastAPI
│       ├── app.py                # FastAPI アプリ (ファサード)
│       ├── security.py           # 認証・セッション・レート制限
│       ├── db_helpers.py         # DB クエリヘルパー
│       ├── jwt_auth.py           # JWT 認証
│       ├── discord_api.py        # Discord REST API クライアント
│       ├── email_service.py      # メール送信
│       ├── routes/               # ルートハンドラ
│       │   ├── api_auth.py       # /api/v1/auth/*
│       │   ├── api_lobbies.py    # /api/v1/lobbies
│       │   ├── api_sticky.py     # /api/v1/sticky
│       │   ├── api_bump.py       # /api/v1/bump
│       │   ├── api_rolepanel.py  # /api/v1/rolepanels
│       │   ├── api_automod.py    # /api/v1/automod
│       │   ├── api_ticket.py     # /api/v1/tickets
│       │   ├── api_joinrole.py   # /api/v1/joinrole
│       │   ├── api_eventlog.py   # /api/v1/eventlog
│       │   ├── api_settings.py   # /api/v1/settings
│       │   ├── api_misc.py       # /api/v1/health, activity
│       │   └── (旧 HTML ルート)
│       └── templates/            # 旧 HTML テンプレート (廃止予定)
├── frontend/                     # Next.js フロントエンド
│   ├── src/
│   │   ├── app/                  # App Router ページ (25 ページ)
│   │   ├── components/           # UI コンポーネント
│   │   └── lib/                  # API クライアント・型定義
│   ├── Dockerfile                # 本番用
│   └── Dockerfile.dev            # 開発用
├── alembic/                      # DB マイグレーション (36 リビジョン)
├── tests/                        # Python テスト (3580 テスト)
├── scripts/
│   └── ci_check.py               # ローカル CI (12 チェック)
├── Dockerfile                    # Python 本番用
├── Dockerfile.dev                # Python 開発用
├── docker-compose.yml            # ローカル開発環境
├── Procfile                      # Railway デプロイ
└── .github/workflows/ci.yml     # GitHub Actions CI (5 ジョブ)
```

## 開発環境

### Docker Compose (推奨)

```bash
cp .env.example .env  # DISCORD_TOKEN を設定
docker compose up db api frontend mailpit
```

| サービス | URL |
|----------|-----|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| Mailpit | http://localhost:8025 |

### 開発ツール

```bash
# Python テスト
docker compose run --rm --profile dev test

# Frontend テスト
docker compose run --rm --profile dev frontend-test

# Lint
docker compose run --rm --profile dev lint

# マイグレーション
docker compose run --rm --profile dev migrate
```

### ローカル CI

```bash
python scripts/ci_check.py        # Lint のみ (12 チェック)
python scripts/ci_check.py --all  # テスト + ビルド込み (15 チェック)
```

## CI / CD

### GitHub Actions (5 ジョブ並列)

| ジョブ | 内容 |
|--------|------|
| backend-lint | ruff, mypy, cspell, JSON/YAML/TOML lint |
| backend-test | pytest + PostgreSQL + カバレッジ |
| frontend-lint | tsc, ESLint, Prettier, cspell |
| frontend-test | Vitest (62 テスト) |
| frontend-build | Next.js ビルド (lint + test 完了後) |

### Railway デプロイ

同一プロジェクト内に 3 サービス:

| サービス | Root Directory | Start Command |
|----------|----------------|---------------|
| bot | `/` | `alembic upgrade head && python -m src.main` |
| api | `/` | `alembic upgrade head && uvicorn src.web.app:app --host 0.0.0.0 --port $PORT` |
| frontend | `/frontend` | `npm run start` |

## License

[MIT License](LICENSE.md)
