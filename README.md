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

- **Sticky メッセージ**: チャンネル最下部に常駐するメッセージ
- **チケットシステム**: パネル + ボタンでチケット作成、スタッフ対応、トランスクリプト保存（操作ボタン: `クローズ` / `担当する`）
- **ロールパネル**: ボタン式 / リアクション式のロール自動付与
- **AutoMod**: 8種類のルール (ユーザー名、アカウント年齢、アバター、タイミング系、自己紹介必須) + BANリスト
- **VCGuard**: 監視対象 VC の人数制限を超過して入室したメンバーを自動切断
- **自動リアクション**: 指定チャンネルの投稿に設定済み絵文字を自動付与
- **イベントログ**: 25種類のサーバーイベントを記録 (Carl-bot 風カラー)
- **入室時ロール**: メンバー参加時に時限ロール自動付与
- **Welcome 画像**: メンバー参加時にカフェ風の画像付き welcome 投稿を送信
- **チャットロール**: 指定チャンネルに累計 N 回投稿でロール付与 (任意で期限付き)
- **Web 管理画面**: 全機能の設定・管理・ログ閲覧

## プロジェクト構成

```
├── src/                          # Python バックエンド
│   ├── main.py                   # Bot エントリーポイント
│   ├── bot.py                    # Bot クラス
│   ├── config.py                 # 設定管理
│   ├── constants.py              # 定数
│   ├── utils.py                  # ユーティリティ
│   ├── cogs/                     # Discord Bot 機能
│   ├── database/                 # SQLAlchemy モデル + エンジン
│   ├── services/                 # DB 操作 (ドメイン別サービス + ファサード)
│   ├── shared/                   # ドメイン非依存の共通ヘルパー
│   ├── features/                 # 機能単位移行用 facade
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
│       │   ├── api_sticky.py     # /api/v1/sticky
│       │   ├── api_rolepanel.py  # /api/v1/rolepanels
│       │   ├── api_automod.py    # /api/v1/automod
│       │   ├── api_ticket.py     # /api/v1/tickets
│       │   ├── api_joinrole.py   # /api/v1/joinrole
│       │   ├── api_chatrole.py   # /api/v1/chatrole
│       │   ├── api_auto_reaction.py # /api/v1/auto-reaction
│       │   ├── api_eventlog.py   # /api/v1/eventlog
│       │   ├── api_settings.py   # /api/v1/settings
│       │   ├── api_common.py     # /api/v1/guilds, channels, roles
│       │   ├── api_misc.py       # /api/v1/health, activity
│       │   └── (旧 HTML ルート)
│       └── templates/            # 旧 HTML テンプレート
├── frontend/                     # Next.js フロントエンド
│   ├── src/
│   │   ├── app/                  # App Router ページ
│   │   ├── components/           # UI コンポーネント
│   │   └── lib/                  # API クライアント・型定義
│   ├── Dockerfile                # 本番用
│   └── Dockerfile.dev            # 開発用
├── alembic/                      # DB マイグレーション
├── tests/                        # Python テスト
├── scripts/
│   └── ci_check.py               # ローカル CI (12 チェック)
├── Dockerfile                    # Python 本番用
├── Dockerfile.dev                # Python 開発用
├── docker-compose.yml            # ローカル開発環境
├── Procfile                      # Railway デプロイ
└── .github/workflows/ci.yml     # GitHub Actions CI (5 ジョブ)
```

## 開発環境

> [!IMPORTANT]
> このプロジェクトの標準手順は **Docker 実行** です。  
> 起動・テスト・CI 検証は必ず Docker (`docker compose ...`) を使ってください。

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
docker compose run --rm --profile dev lint  # Lint / 型チェック
docker compose run --rm --profile dev test  # Python テスト
docker compose run --rm --profile dev frontend-test  # Frontend テスト
```

`python scripts/ci_check.py` / `python scripts/ci_check.py --all` は補助用途です。
最終確認は Docker 実行結果を採用してください。

## CI / CD

### GitHub Actions (5 ジョブ並列)

| ジョブ | 内容 |
|--------|------|
| backend-lint | ruff, mypy, cspell, JSON/YAML/TOML lint |
| backend-test | pytest + PostgreSQL + カバレッジ |
| frontend-lint | tsc, ESLint, Prettier, cspell |
| frontend-test | Vitest |
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
