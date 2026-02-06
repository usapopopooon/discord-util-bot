# 環境構築ガイド

Discord Util Bot の環境構築・開発・デプロイに関するドキュメント。

## 目次

- [環境変数](#環境変数)
- [セットアップ](#セットアップ)
  - [ローカル開発 (Make)](#ローカル開発-make)
  - [ローカル開発 (手動)](#ローカル開発-手動)
  - [Docker Compose](#docker-compose)
  - [Heroku へのデプロイ](#heroku-へのデプロイ)
- [開発](#開発)
  - [Make コマンド](#make-コマンド)
  - [テスト](#テスト)
  - [マイグレーション](#マイグレーション)
  - [CI](#ci)
- [クロスプラットフォーム対応](#クロスプラットフォーム対応)

## 環境変数

### 必須

| 変数名 | 説明 |
|--------|------|
| `DISCORD_TOKEN` | Discord Bot トークン |

### オプション (Bot)

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `DATABASE_URL` | `postgresql+asyncpg://user@localhost/discord_util_bot` | PostgreSQL 接続 URL |
| `HEALTH_CHANNEL_ID` | `0` | ヘルスチェック Embed を送信するチャンネル ID (0 = 無効) |
| `BUMP_CHANNEL_ID` | `0` | Bump リマインダー用チャンネル ID (0 = 無効) |

### オプション (データベース接続)

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `DATABASE_REQUIRE_SSL` | `false` | SSL 接続を有効化 (Heroku Postgres 用) |
| `DB_POOL_SIZE` | `5` | コネクションプールサイズ |
| `DB_MAX_OVERFLOW` | `10` | オーバーフロー接続数 |

### オプション (Web 管理画面)

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `ADMIN_EMAIL` | `admin@example.com` | 初期管理者メールアドレス |
| `ADMIN_PASSWORD` | `changeme` | 初期管理者パスワード |
| `SESSION_SECRET_KEY` | (ランダム生成) | セッション署名キー (再起動後もセッション維持する場合は設定) |
| `SECURE_COOKIE` | `true` | HTTPS 環境でのみ Cookie を送信 |
| `APP_URL` | `http://localhost:8000` | パスワードリセットリンク用 URL |

### オプション (SMTP / メール送信)

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `SMTP_HOST` | (空) | SMTP サーバーホスト名 (設定時にメール機能有効) |
| `SMTP_PORT` | `587` | SMTP ポート番号 |
| `SMTP_USER` | (空) | SMTP 認証ユーザー名 |
| `SMTP_PASSWORD` | (空) | SMTP 認証パスワード |
| `SMTP_FROM_EMAIL` | (空) | 送信元メールアドレス |
| `SMTP_USE_TLS` | `true` | TLS を使用するかどうか |

## セットアップ

### ローカル開発 (Make)

```bash
git clone https://github.com/usapopopooon/discord-util-bot.git
cd discord-util-bot
cp .env.example .env  # DISCORD_TOKEN を設定
make run
```

### ローカル開発 (手動)

```bash
git clone https://github.com/usapopopooon/discord-util-bot.git
cd discord-util-bot
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env  # DISCORD_TOKEN を設定

# マイグレーション実行
alembic upgrade head

# Bot 起動
python -m src.main
```

### Docker Compose

```bash
cp .env.example .env  # DISCORD_TOKEN を設定
docker-compose up -d
```

PostgreSQL と Bot が一緒に起動する。

### Heroku へのデプロイ

1. 必要な環境変数を設定:
   - `DISCORD_TOKEN`: Bot トークン
   - `DATABASE_URL`: Heroku Postgres の URL (自動設定される)
   - `DATABASE_REQUIRE_SSL`: `true`

2. Procfile で Bot を起動:
   ```
   worker: python -m src.main
   ```

3. Web 管理画面を使用する場合:
   ```
   web: uvicorn src.web.app:app --host 0.0.0.0 --port $PORT
   ```

4. デプロイは GitHub Actions から手動トリガーで実行:
   - **ローカルからの手動デプロイは禁止** (バージョン齟齬・テスト見逃し防止)
   - `main` ブランチへの push → CI テスト実行
   - GitHub Actions で手動トリガー → テスト → デプロイ

## 開発

### Make コマンド

| コマンド | 説明 |
|---------|------|
| `make setup` | venv 作成 + 依存関係インストール |
| `make run` | Bot を起動 |
| `make test` | テスト実行 |
| `make test-db` | PostgreSQL コンテナを使ったテスト実行 |
| `make lint` | Ruff リンター実行 |
| `make typecheck` | mypy 型チェック実行 |
| `make spellcheck` | cspell スペルチェック実行 |
| `make ci` | CI と同じ全チェックを実行 |
| `make clean` | venv とキャッシュを削除 |

### テスト

```bash
# テスト実行
make test

# カバレッジ付き
.venv/bin/pytest --cov --cov-report=html

# 特定のテストファイル
.venv/bin/pytest tests/cogs/test_sticky.py -v
```

#### PostgreSQL を使ったテスト

ローカルで PostgreSQL コンテナを使ってテストを実行するスクリプトを提供しています。

```bash
# Linux / macOS (Bash)
./scripts/test-with-db.sh

# Windows (PowerShell)
.\scripts\test-with-db.ps1

# 全 OS (Python)
python scripts/test_with_db.py
```

オプション:

| オプション | 説明 |
|-----------|------|
| `-v` | verbose モードで実行 |
| `-k <pattern>` | パターンにマッチするテストのみ実行 |
| `--keep` | テスト後コンテナを停止しない |

### マイグレーション

```bash
# マイグレーション作成
alembic revision --autogenerate -m "Add new table"

# マイグレーション適用
alembic upgrade head

# ロールバック
alembic downgrade -1
```

### CI

GitHub Actions で以下を自動実行:
- cspell (スペルチェック)
- JSON / YAML / TOML lint (構文チェック)
- Ruff format (フォーマットチェック)
- Ruff check (リンター)
- mypy (型チェック)
- pytest + Codecov (テスト + カバレッジ 98%+)

## クロスプラットフォーム対応

このプロジェクトは macOS / Linux を主な開発環境としていますが、Windows でも開発可能です。

### Windows での開発

| 機能 | 対応状況 | 備考 |
|-----|---------|------|
| Python コード | 完全対応 | シグナルハンドリングは try/except でフォールバック |
| Docker Compose | 完全対応 | Docker Desktop for Windows を使用 |
| テストスクリプト | 完全対応 | PowerShell / Python 版を提供 |
| Make コマンド | 非対応 | 手動コマンドまたは WSL2 を使用 |

### スクリプト一覧

| スクリプト | 対象環境 | 説明 |
|-----------|---------|------|
| `scripts/test-with-db.sh` | Linux / macOS | Bash 版テストスクリプト |
| `scripts/test-with-db.ps1` | Windows | PowerShell 版テストスクリプト |
| `scripts/test_with_db.py` | 全 OS | クロスプラットフォーム Python スクリプト |

### 推奨環境

Windows で完全な互換性を得るには、以下のいずれかを推奨:

1. **WSL2 + Docker Desktop** (推奨)
   - Linux 環境で開発できるため、全てのスクリプトがそのまま動作
   - Docker Desktop の WSL2 バックエンドを有効化

2. **PowerShell + Docker Desktop**
   - ネイティブ Windows 環境
   - 提供されている PowerShell スクリプトを使用

3. **Python スクリプト**
   - `python scripts/test_with_db.py` で全 OS 共通のテスト実行
