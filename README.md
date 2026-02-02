# Discord Util Bot

[![CI](https://github.com/usapopopooon/discord-util-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/usapopopooon/discord-util-bot/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/usapopopooon/discord-util-bot/graph/badge.svg)](https://codecov.io/gh/usapopopooon/discord-util-bot)

Discord の一時ボイスチャンネル管理 Bot。ロビー VC に参加すると専用のボイスチャンネルが自動作成され、全員退出すると自動削除される。Bump リマインダー、Sticky メッセージ、Web 管理画面も搭載。

## 機能

### 一時 VC 機能
- **自動 VC 作成**: ロビーチャンネルに参加すると個人用 VC が作成される
- **ボタン UI コントロールパネル**: コマンド不要でチャンネルを管理
  - 🏷️ 名前変更
  - 👥 人数制限
  - 🔊 ビットレート変更
  - 🌏 リージョン変更
  - 🔒 ロック / アンロック
  - 🙈 非表示 / 表示
  - 🔞 年齢制限
  - 👑 オーナー譲渡
  - 👟 キック
  - 🚫 ブロック
  - ✅ 許可 (ロック時に特定ユーザーを許可)
  - 📵 カメラ禁止 (特定ユーザーのカメラ/配信を禁止)
  - 📹 カメラ許可 (カメラ禁止を解除)
- **自動クリーンアップ**: 全員退出したチャンネルは自動削除
- **複数ロビー対応**: サーバーごとに複数のロビーチャンネルを設定可能

### Bump リマインダー機能
- **DISBOARD / ディス速報対応**: 両サービスの bump 成功メッセージを自動検出
- **2時間後通知**: bump 成功から2時間後にリマインダーを送信
- **Server Bumper ロール必須**: bump を実行したユーザーが `Server Bumper` ロールを持っている場合のみリマインダーを登録
- **通知カスタマイズ**: サービスごとに通知の有効/無効、メンションロールを設定可能
  - デフォルト通知先: `Server Bumper` ロール
  - ボタンからサービスごとに任意のロールに変更可能
- **自動検出**: `/bump setup` 時にチャンネル履歴から直近の bump を検出し、次回通知時刻を計算
- **設定状況の表示**: bump 検知時・セットアップ時に現在の通知先ロールを表示

### Sticky メッセージ機能
- **常に最下部に表示**: チャンネルに常に最新位置に表示されるメッセージを設定
- **Embed / テキスト対応**: Embed 形式またはプレーンテキスト形式を選択可能
- **デバウンス方式**: 連続投稿時の負荷を軽減 (遅延秒数を設定可能)
- **Bot 再起動対応**: DB から設定を復元して動作継続

### ロールパネル機能
- **ボタン式 / リアクション式**: 2つの入力方式から選択可能
- **複数ロール対応**: 1パネルに複数のロールボタン/リアクションを設置
- **トグル式動作**: クリックで付与、もう1回で解除
- **永続 View**: Bot 再起動後もボタンが動作
- **Web 管理画面連携**: パネルの作成・管理が可能

### Web 管理画面
- **ダッシュボード**: ロビー、Bump 設定、Sticky メッセージの一覧表示
- **認証機能**: メール / パスワードによるログイン
- **パスワードリセット**: SMTP 経由でリセットメールを送信
- **セキュリティ**: レート制限、セキュア Cookie、セッション管理

### その他
- **ヘルスモニタリング**: 10 分ごとにハートビート Embed を送信し死活監視
- **Graceful シャットダウン**: SIGTERM 受信時に安全に Bot を停止 (Heroku 対応)
- **SSL 接続**: Heroku Postgres など SSL を要求するデータベースに対応
- **コネクションプール**: データベース接続数を制限し、クラウド環境に最適化

## クイックスタート

```bash
git clone https://github.com/usapopopooon/discord-util-bot.git
cd discord-util-bot
cp .env.example .env  # DISCORD_TOKEN を設定
make run              # または docker-compose up -d
```

詳細な環境構築・開発ガイドは [docs/SETUP.md](docs/SETUP.md) を参照。

## スラッシュコマンド

### 一時 VC コマンド

| コマンド | 説明 |
|---------|------|
| `/vc lobby` | ロビー VC を作成 (管理者のみ) |
| `/vc panel` | コントロールパネルを再投稿 |

### Bump コマンド

| コマンド | 説明 |
|---------|------|
| `/bump setup` | Bump 監視を開始 (実行したチャンネルを監視) |
| `/bump status` | Bump 監視の設定状況を確認 |
| `/bump disable` | Bump 監視を停止 |

### Sticky コマンド

| コマンド | 説明 |
|---------|------|
| `/sticky set` | Sticky メッセージを設定 (Embed/テキスト選択) |
| `/sticky remove` | Sticky メッセージを削除 |
| `/sticky status` | Sticky メッセージの設定状況を確認 |

### ロールパネルコマンド

| コマンド | 説明 |
|---------|------|
| `/rolepanel create <type>` | パネルを作成 (type: button/reaction) |
| `/rolepanel add <role> <emoji> [label]` | ロールボタン/リアクションを追加 |
| `/rolepanel remove <emoji>` | ロールボタン/リアクションを削除 |
| `/rolepanel delete` | パネルを削除 |
| `/rolepanel list` | 設定済みパネル一覧 |

## コントロールパネル

ロビーに参加して VC が作成されると、チャンネルにコントロールパネル Embed が送信される。オーナーのみがボタンを操作できる。

| ボタン | 説明 |
|--------|------|
| 🏷️ 名前変更 | チャンネル名を変更 (モーダル入力) |
| 👥 人数制限 | 接続人数の上限を設定 (0 = 無制限) |
| 🔊 ビットレート | 音声ビットレートを選択 |
| 🌏 リージョン | ボイスリージョンを選択 |
| 🔒 ロック | チャンネルをロック / アンロック |
| 🙈 非表示 | チャンネルを非表示 / 表示 |
| 🔞 年齢制限 | NSFW の切り替え |
| 👑 譲渡 | オーナー権限を他のユーザーに譲渡 |
| 👟 キック | ユーザーをチャンネルからキック |
| 🚫 ブロック | ユーザーをブロック (キック + 接続拒否) |
| ✅ 許可 | ロック時に特定ユーザーの接続を許可 |
| 📵 カメラ禁止 | 特定ユーザーのカメラ / 配信を禁止 |
| 📹 カメラ許可 | カメラ禁止を解除 |

## プロジェクト構成

```
src/
├── main.py              # エントリーポイント (SIGTERM ハンドラ含む)
├── bot.py               # Bot クラス定義
├── config.py            # pydantic-settings による設定管理
├── constants.py         # アプリケーション定数
├── cogs/
│   ├── admin.py         # 管理者用コマンド (/vc lobby)
│   ├── voice.py         # VC 自動作成・削除、/vc コマンド
│   ├── bump.py          # Bump リマインダー (/bump コマンド)
│   ├── sticky.py        # Sticky メッセージ (/sticky コマンド)
│   ├── role_panel.py    # ロールパネル (/rolepanel コマンド)
│   └── health.py        # ハートビート死活監視
├── core/
│   ├── permissions.py   # Discord 権限ヘルパー
│   ├── validators.py    # 入力バリデーション
│   └── builders.py      # チャンネル作成ビルダー
├── database/
│   ├── engine.py        # SQLAlchemy 非同期エンジン (SSL/プール設定)
│   └── models.py        # DB モデル定義
├── services/
│   └── db_service.py    # DB CRUD 操作
├── ui/
│   ├── control_panel.py # コントロールパネル UI (View / Button / Select)
│   └── role_panel_view.py # ロールパネル UI (View / Button / Modal)
└── web/
    ├── app.py           # FastAPI Web 管理画面
    ├── email_service.py # メール送信サービス
    └── templates.py     # HTML テンプレート
```

## 開発

```bash
make test       # テスト実行
make lint       # リンター実行
make typecheck  # 型チェック
```

詳細な開発ガイド (Make コマンド、テスト、マイグレーション、CI) は [docs/SETUP.md](docs/SETUP.md) を参照。

## アーキテクチャ

詳細なアーキテクチャ・設計ドキュメントは [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) を参照。

## License

MIT
