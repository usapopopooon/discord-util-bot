# 環境構築ガイド

## 環境変数

### 必須

| 変数名 | 説明 |
|--------|------|
| `DISCORD_TOKEN` | Discord Bot トークン |
| `DATABASE_URL` | PostgreSQL 接続 URL |

### オプション (Bot)

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `TIMEZONE_OFFSET` | `9` | UTC オフセット (DB 値優先) |
| `LOG_LEVEL` | `INFO` | ログレベル |

### オプション (API)

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `ADMIN_EMAIL` | `admin@example.com` | 初期管理者メールアドレス |
| `ADMIN_PASSWORD` | `changeme` | 初期管理者パスワード |
| `SESSION_SECRET_KEY` | (ランダム生成) | JWT 署名キー |
| `APP_URL` | `http://localhost:8000` | API 側で生成するメールリンクのベース URL |
| `FRONTEND_URL` | (未設定時 `APP_URL`) | チケットクローズログ内リンクのベース URL |
| `SECURE_COOKIE` | `true` | HTTPS のみ Cookie 送信 |
| `CORS_ORIGINS` | `http://localhost:3000` | CORS 許可オリジン (カンマ区切り) |

### オプション (Frontend)

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `API_URL` | `http://localhost:8000` | FastAPI の内部 URL (ビルド時に評価) |

### オプション (DB 接続)

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `DATABASE_REQUIRE_SSL` | `false` | SSL 接続を有効化 |
| `DB_POOL_SIZE` | `5` | コネクションプールサイズ |
| `DB_MAX_OVERFLOW` | `10` | オーバーフロー接続数 |

### オプション (SMTP)

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `SMTP_HOST` | (空) | SMTP サーバーホスト名 |
| `SMTP_PORT` | `587` | SMTP ポート番号 |
| `SMTP_USER` | (空) | SMTP 認証ユーザー名 |
| `SMTP_PASSWORD` | (空) | SMTP 認証パスワード |
| `SMTP_FROM_EMAIL` | (空) | 送信元メールアドレス |
| `SMTP_USE_TLS` | `true` | TLS 使用 |

## ローカル開発

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
| PostgreSQL | localhost:5432 |

Bot も起動する場合:
```bash
docker compose up
```

### 手動セットアップ

```bash
# Python バックエンド
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python -m src.main              # Bot
uvicorn src.web.app:app --reload  # API

# フロントエンド
cd frontend
npm ci
npm run dev
```

## テスト

### Python (pytest)

```bash
# Docker
docker compose run --rm --profile dev test

# ローカル
pytest -v --cov=src
```

### Frontend (Vitest)

```bash
# Docker
docker compose run --rm --profile dev frontend-test

# ローカル
cd frontend && npm run test:run
```

## Lint / 型チェック

```bash
# ローカル CI (全チェック)
python scripts/ci_check.py

# テスト込み
python scripts/ci_check.py --all

# Docker
docker compose run --rm --profile dev lint
```

## マイグレーション

```bash
# 適用
alembic upgrade head

# Docker
docker compose run --rm --profile dev migrate

# 新規作成
alembic revision --autogenerate -m "Add new table"
```

## Railway デプロイ

同一プロジェクト内に 3 サービス:

| サービス | Root Directory | Start Command |
|----------|----------------|---------------|
| bot | `/` | `alembic upgrade head && python -m src.main` |
| api | `/` | `alembic upgrade head && uvicorn src.web.app:app --host 0.0.0.0 --port $PORT` |
| frontend | `/frontend` | `npm run start` |

### frontend の環境変数

```
API_URL=http://api.railway.internal:<PORT>
```

api サービスの Private Networking を有効にし、`PORT` は api サービスの実際のポートを指定。
