# Feature Migration Baseline (Steps 1-5)

このドキュメントは、以下の5ステップをこのリポジトリで実行済みにするための基準です。

## 1. 共通化対象の固定 (ドメイン非依存のみ)

共通化対象:
- 入力検証: `src/shared/validators.py`
- 文字列/選択肢ビルド: `src/shared/builders.py`
- 権限計算(純粋関数): `src/shared/permissions.py`
- 非同期ロック管理: `src/shared/concurrency.py`

非対象 (feature内に残す):
- AutoMod の判定ルール
- Ticket の状態遷移
- Sticky の再投稿戦略

## 2. ドメイン依存ロジックの分離方針

- 共通層は「Discord/Ticket/AutoMod という語彙」に依存しない。
- feature固有ロジックは既存の `src/cogs/*` と `src/services/*_service.py` を維持。

## 3. 共通モジュールを薄く維持

- `src/shared` は純粋関数と軽量ユーティリティのみ。
- DB セッションやルート定義のような結合の強い関心事は移さない。

## 4. 機能単位移行の入口を用意

Feature package facade:
- `src/features/sticky/__init__.py`
- `src/features/automod/__init__.py`
- `src/features/ticket/__init__.py`

これにより、今後 feature 単位で import 経路を段階移行できる。

## 5. 互換レイヤーの整理 (2026-05-09 更新)

- `src/core/*` shim は削除し、`src/shared/*` を正規 import 経路に統一。
- `src/services/db_service.py` 互換モジュールも削除し、`src.services` を正規入口に統一。
- `src/utils.py` のロックAPIは公開契約を維持しつつ、実装を安定化。

互換維持コストを断ち切り、将来の変更を feature 単位で安全に進められる状態。
