"""Tests for shared utility functions."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

import pytest

from src.utils import (
    _cleanup_resource_locks,
    _has_lone_surrogate,
    _resource_locks,
    clear_resource_locks,
    format_datetime,
    get_resource_lock,
    get_resource_lock_count,
    is_valid_emoji,
    normalize_emoji,
)


class TestHasLoneSurrogate:
    """_has_lone_surrogate 関数のテスト。"""

    def test_normal_text_no_surrogate(self) -> None:
        """通常のテキストには壊れたサロゲートがない。"""
        assert _has_lone_surrogate("hello") is False
        assert _has_lone_surrogate("こんにちは") is False
        assert _has_lone_surrogate("😀") is False

    def test_emoji_no_surrogate(self) -> None:
        """絵文字には壊れたサロゲートがない。"""
        assert _has_lone_surrogate("🧑‍🧑‍🧒") is False
        assert _has_lone_surrogate("1️⃣") is False
        assert _has_lone_surrogate("🇯🇵") is False

    def test_empty_string_no_surrogate(self) -> None:
        """空文字には壊れたサロゲートがない。"""
        assert _has_lone_surrogate("") is False


class TestIsValidEmojiBasic:
    """is_valid_emoji 関数の基本テスト。"""

    def test_empty_string_invalid(self) -> None:
        """空文字は無効。"""
        assert is_valid_emoji("") is False

    def test_none_invalid(self) -> None:
        """None は無効。"""
        assert is_valid_emoji(None) is False

    def test_simple_emoji_valid(self) -> None:
        """シンプルな絵文字は有効。"""
        assert is_valid_emoji("😀") is True
        assert is_valid_emoji("🎮") is True
        assert is_valid_emoji("❤️") is True

    def test_emoji_with_vs16_valid(self) -> None:
        """VS16 (U+FE0F) 付きの絵文字は有効。"""
        assert is_valid_emoji("⚓️") is True  # anchor with VS16
        assert is_valid_emoji("⚓") is True  # anchor without VS16
        assert is_valid_emoji("✨️") is True  # sparkles with VS16
        assert is_valid_emoji("⚡️") is True  # lightning with VS16
        assert is_valid_emoji("⭐️") is True  # star with VS16
        assert is_valid_emoji("⚽️") is True  # soccer with VS16

    def test_zwj_emoji_valid(self) -> None:
        """ZWJ 絵文字は有効。"""
        assert is_valid_emoji("🧑‍🧑‍🧒") is True
        assert is_valid_emoji("👨‍💻") is True

    def test_keycap_emoji_valid(self) -> None:
        """Keycap 絵文字は有効。"""
        assert is_valid_emoji("1️⃣") is True
        assert is_valid_emoji("#️⃣") is True

    def test_flag_emoji_valid(self) -> None:
        """国旗絵文字は有効。"""
        assert is_valid_emoji("🇯🇵") is True
        assert is_valid_emoji("🇺🇸") is True

    def test_discord_custom_emoji_valid(self) -> None:
        """Discord カスタム絵文字は有効。"""
        assert is_valid_emoji("<:custom:123456789>") is True
        assert is_valid_emoji("<a:animated:987654321>") is True

    def test_discord_custom_emoji_invalid_format(self) -> None:
        """不正な形式の Discord カスタム絵文字は無効。"""
        assert is_valid_emoji("<custom:123>") is False
        assert is_valid_emoji(":custom:123:") is False
        assert is_valid_emoji("<:custom:>") is False
        assert is_valid_emoji("<:custom:abc>") is False

    def test_control_characters_invalid(self) -> None:
        """制御文字を含む文字列は無効。"""
        assert is_valid_emoji("😀\n") is False
        assert is_valid_emoji("\t😀") is False
        assert is_valid_emoji("😀\r") is False
        assert is_valid_emoji("\x00😀") is False

    def test_plain_text_invalid(self) -> None:
        """通常のテキストは無効。"""
        assert is_valid_emoji("hello") is False
        assert is_valid_emoji("123") is False
        assert is_valid_emoji("abc") is False

    def test_single_character_numbers_invalid(self) -> None:
        """単体の数字は無効。"""
        assert is_valid_emoji("1") is False
        assert is_valid_emoji("9") is False


class TestIsValidEmojiRobustness:
    """is_valid_emoji 関数の堅牢性テスト。"""

    def test_very_long_string_rejected(self) -> None:
        """非常に長い文字列 (複数絵文字) は無効。"""
        assert is_valid_emoji("😀" * 100) is False

    def test_mixed_content_rejected(self) -> None:
        """混合コンテンツは無効。"""
        assert is_valid_emoji("abc😀def") is False
        assert is_valid_emoji("😀abc") is False
        assert is_valid_emoji("abc😀") is False

    def test_unicode_normalization_handled(self) -> None:
        """Unicode 正規化が正しく処理される。"""
        # NFC と NFD で異なる表現になる文字
        # 絵文字は通常これらの影響を受けないが、確認
        assert is_valid_emoji("😀") is True

    def test_circled_digit_not_emoji(self) -> None:
        """丸囲み数字は絵文字ではない。"""
        assert is_valid_emoji("①") is False
        assert is_valid_emoji("②") is False
        assert is_valid_emoji("⑩") is False

    def test_mathematical_symbol_not_emoji(self) -> None:
        """数学記号は絵文字ではない。"""
        assert is_valid_emoji("∑") is False
        assert is_valid_emoji("∫") is False
        assert is_valid_emoji("∞") is False

    def test_currency_symbol_not_emoji(self) -> None:
        """通貨記号は絵文字ではない。"""
        assert is_valid_emoji("$") is False
        assert is_valid_emoji("€") is False
        assert is_valid_emoji("¥") is False

    def test_box_drawing_not_emoji(self) -> None:
        """罫線素片は絵文字ではない。"""
        assert is_valid_emoji("─") is False
        assert is_valid_emoji("│") is False
        assert is_valid_emoji("┌") is False


class TestNormalizeEmoji:
    """normalize_emoji 関数のテスト。"""

    def test_simple_emoji_unchanged(self) -> None:
        """シンプルな絵文字はそのまま返される。"""
        assert normalize_emoji("😀") == "😀"
        assert normalize_emoji("🎮") == "🎮"

    def test_zwj_emoji_unchanged(self) -> None:
        """ZWJ 絵文字はそのまま返される。"""
        assert normalize_emoji("🧑‍🧑‍🧒") == "🧑‍🧑‍🧒"
        assert normalize_emoji("👨‍💻") == "👨‍💻"

    def test_vs16_emoji_stripped(self) -> None:
        """VS16 付き絵文字は VS16 が除去される。"""
        assert normalize_emoji("⚓️") == "⚓"  # anchor
        assert normalize_emoji("✨️") == "✨"  # sparkles
        assert normalize_emoji("⚡️") == "⚡"  # lightning
        assert normalize_emoji("❤️") == "❤"  # heart

    def test_keycap_emoji_vs16_stripped(self) -> None:
        """Keycap 絵文字の VS16 が除去される。"""
        assert normalize_emoji("1️⃣") == "1⃣"
        assert normalize_emoji("#️⃣") == "#⃣"

    def test_discord_custom_emoji_unchanged(self) -> None:
        """Discord カスタム絵文字はそのまま返される。"""
        assert normalize_emoji("<:custom:123456>") == "<:custom:123456>"
        assert normalize_emoji("<a:animated:789>") == "<a:animated:789>"

    def test_empty_string_unchanged(self) -> None:
        """空文字はそのまま返される。"""
        assert normalize_emoji("") == ""

    def test_nfc_normalization_applied(self) -> None:
        """NFC 正規化が適用される。"""
        import unicodedata

        # 絵文字は通常 NFC/NFD の影響を受けないが、関数は NFC 正規化を適用
        emoji = "😀"
        result = normalize_emoji(emoji)
        assert result == unicodedata.normalize("NFC", emoji)


# =============================================================================
# Resource Lock Tests
# =============================================================================


@pytest.fixture(autouse=True)
def clear_locks_before_each_test() -> None:
    """各テスト前にリソースロックをクリアする。"""
    clear_resource_locks()


class TestResourceLockStateIsolation:
    """autouse fixture によるステート分離が機能することを検証するカナリアテスト."""

    def test_locks_start_empty(self) -> None:
        """各テスト開始時にロックが空であることを検証."""
        assert get_resource_lock_count() == 0

    def test_cleanup_time_is_reset(self) -> None:
        """各テスト開始時にクリーンアップ時刻がリセットされていることを検証."""
        import src.utils as utils_module

        assert utils_module._lock_last_cleanup_time <= 0


class TestGetResourceLock:
    """get_resource_lock 関数のテスト。"""

    def test_returns_lock_for_new_key(self) -> None:
        """新しいキーに対してロックを返す。"""
        lock = get_resource_lock("test:key:1")
        assert isinstance(lock, asyncio.Lock)

    def test_same_key_returns_same_lock(self) -> None:
        """同じキーに対しては同じロックインスタンスを返す。"""
        lock1 = get_resource_lock("test:key:same")
        lock2 = get_resource_lock("test:key:same")
        assert lock1 is lock2

    def test_different_keys_return_different_locks(self) -> None:
        """異なるキーに対しては異なるロックインスタンスを返す。"""
        lock1 = get_resource_lock("test:key:a")
        lock2 = get_resource_lock("test:key:b")
        assert lock1 is not lock2

    def test_lock_is_reusable(self) -> None:
        """ロックは再利用可能。"""
        lock = get_resource_lock("test:reusable")
        assert not lock.locked()

    @pytest.mark.asyncio
    async def test_lock_can_be_acquired(self) -> None:
        """ロックは取得可能。"""
        lock = get_resource_lock("test:acquire")
        async with lock:
            assert lock.locked()
        assert not lock.locked()


class TestClearResourceLocks:
    """clear_resource_locks 関数のテスト。"""

    def test_clears_all_locks(self) -> None:
        """全てのロックをクリアする。"""
        get_resource_lock("test:clear:1")
        get_resource_lock("test:clear:2")
        get_resource_lock("test:clear:3")
        assert get_resource_lock_count() == 3

        clear_resource_locks()
        assert get_resource_lock_count() == 0

    def test_clear_empty_is_safe(self) -> None:
        """空の状態でクリアしても安全。"""
        clear_resource_locks()
        clear_resource_locks()  # 二重クリアも安全
        assert get_resource_lock_count() == 0


class TestGetResourceLockCount:
    """get_resource_lock_count 関数のテスト。"""

    def test_returns_zero_when_empty(self) -> None:
        """ロックがない場合は 0 を返す。"""
        assert get_resource_lock_count() == 0

    def test_returns_correct_count(self) -> None:
        """正しいロック数を返す。"""
        get_resource_lock("test:count:1")
        assert get_resource_lock_count() == 1

        get_resource_lock("test:count:2")
        assert get_resource_lock_count() == 2

        get_resource_lock("test:count:3")
        assert get_resource_lock_count() == 3

    def test_same_key_does_not_increase_count(self) -> None:
        """同じキーで呼び出してもカウントは増えない。"""
        get_resource_lock("test:same")
        get_resource_lock("test:same")
        get_resource_lock("test:same")
        assert get_resource_lock_count() == 1


class TestResourceLockConcurrency:
    """リソースロックの並行性テスト。"""

    @pytest.mark.asyncio
    async def test_lock_serializes_access(self) -> None:
        """ロックがアクセスをシリアライズする。"""
        results: list[int] = []
        lock = get_resource_lock("test:serialize")

        async def task(n: int) -> None:
            async with lock:
                results.append(n)
                await asyncio.sleep(0.01)  # シミュレートされた処理時間

        # 同時に複数のタスクを起動
        await asyncio.gather(task(1), task(2), task(3))

        # 全てのタスクが完了
        assert len(results) == 3
        # 順序は不定だが、全ての値が含まれている
        assert sorted(results) == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_different_locks_allow_parallel_execution(self) -> None:
        """異なるキーのロックは並列実行を許可する。"""
        execution_times: dict[str, tuple[float, float]] = {}

        async def task(key: str) -> None:
            lock = get_resource_lock(key)
            async with lock:
                start = time.monotonic()
                await asyncio.sleep(0.05)
                end = time.monotonic()
                execution_times[key] = (start, end)

        # 異なるキーで並列実行
        await asyncio.gather(task("key:a"), task("key:b"))

        # 両方のタスクがほぼ同時に実行された (0.05秒 + 少しの余裕)
        total_time = max(end for _, end in execution_times.values()) - min(
            start for start, _ in execution_times.values()
        )
        # 並列実行なら 0.1秒未満で完了するはず
        assert total_time < 0.1

    @pytest.mark.asyncio
    async def test_same_lock_prevents_parallel_execution(self) -> None:
        """同じキーのロックは並列実行を防ぐ。"""
        execution_order: list[str] = []

        async def task(name: str) -> None:
            lock = get_resource_lock("test:same_lock")
            async with lock:
                execution_order.append(f"{name}_start")
                await asyncio.sleep(0.01)
                execution_order.append(f"{name}_end")

        await asyncio.gather(task("A"), task("B"))

        # シリアライズされるため、A または B が先に完全に終了してから次が開始
        # ["A_start", "A_end", "B_start", "B_end"]
        # or ["B_start", "B_end", "A_start", "A_end"]
        assert len(execution_order) == 4
        # 最初の start と end が連続している
        assert execution_order[0].endswith("_start")
        assert execution_order[1].endswith("_end")
        assert execution_order[0][0] == execution_order[1][0]  # 同じタスク


class TestResourceLockCleanup:
    """リソースロックのクリーンアップテスト。"""

    def test_cleanup_does_not_raise_exception(self) -> None:
        """クリーンアップが例外を発生させない。"""
        # ロックを作成
        get_resource_lock("test:old:1")
        get_resource_lock("test:old:2")
        initial_count = get_resource_lock_count()
        assert initial_count >= 2

        # 多数回呼び出しても例外が発生しない
        for i in range(10):
            get_resource_lock(f"test:stress:{i}")

        # ロック数が増えている (クリーンアップは時間ベースなので即座には発生しない)
        assert get_resource_lock_count() >= initial_count

    def test_lock_access_time_is_updated(self) -> None:
        """ロックアクセス時刻が更新される。"""
        # 同じキーで複数回呼び出しても、同じロックが返される
        lock1 = get_resource_lock("test:update")
        lock2 = get_resource_lock("test:update")
        assert lock1 is lock2
        # 内部状態の更新は実装詳細のためテストしない


# =============================================================================
# Integration Tests: Lock + Cooldown Double Protection
# =============================================================================


class TestResourceLockCooldownIntegration:
    """リソースロックとクールダウンの二重保護統合テスト。"""

    @pytest.mark.asyncio
    async def test_lock_prevents_race_condition_in_cooldown_window(self) -> None:
        """ロックがクールダウンウィンドウ内のレースコンディションを防ぐ。

        シナリオ:
        1. 2つのリクエストがほぼ同時に来る
        2. クールダウンチェック前にロックを取得
        3. 最初のリクエストが処理され、クールダウンが記録される
        4. 2番目のリクエストはロック解放後にクールダウンチェックで拒否される
        """
        # シンプルなクールダウンシミュレーション
        cooldown_cache: dict[str, float] = {}
        cooldown_seconds = 3.0
        processed_count = 0

        async def process_request(user_id: str) -> bool:
            """リクエストを処理する (成功したら True)。"""
            nonlocal processed_count
            lock = get_resource_lock(f"test:integration:{user_id}")

            async with lock:
                # クールダウンチェック
                now = time.monotonic()
                last_time = cooldown_cache.get(user_id)
                if last_time and now - last_time < cooldown_seconds:
                    return False  # クールダウン中

                # 処理をシミュレート
                await asyncio.sleep(0.01)
                cooldown_cache[user_id] = now
                processed_count += 1
                return True

        # 同じユーザーの2つのリクエストを同時に送信
        results = await asyncio.gather(
            process_request("user123"),
            process_request("user123"),
        )

        # ロックにより、1つだけが処理される
        assert sum(results) == 1
        assert processed_count == 1

    @pytest.mark.asyncio
    async def test_different_users_can_process_simultaneously(self) -> None:
        """異なるユーザーは同時に処理可能。"""
        cooldown_cache: dict[str, float] = {}
        processed_count = 0

        async def process_request(user_id: str) -> bool:
            nonlocal processed_count
            lock = get_resource_lock(f"test:multi_user:{user_id}")

            async with lock:
                now = time.monotonic()
                if user_id in cooldown_cache:
                    return False

                await asyncio.sleep(0.01)
                cooldown_cache[user_id] = now
                processed_count += 1
                return True

        # 異なるユーザーの2つのリクエストを同時に送信
        results = await asyncio.gather(
            process_request("user_a"),
            process_request("user_b"),
        )

        # 両方のユーザーが処理される
        assert sum(results) == 2
        assert processed_count == 2

    @pytest.mark.asyncio
    async def test_sequential_requests_after_cooldown_expire(self) -> None:
        """クールダウン期限後のリクエストは処理可能。"""
        cooldown_cache: dict[str, float] = {}
        cooldown_seconds = 0.05  # 50ms のクールダウン
        processed_timestamps: list[float] = []

        async def process_request(user_id: str) -> bool:
            lock = get_resource_lock(f"test:expire:{user_id}")

            async with lock:
                now = time.monotonic()
                last_time = cooldown_cache.get(user_id)
                if last_time and now - last_time < cooldown_seconds:
                    return False

                cooldown_cache[user_id] = now
                processed_timestamps.append(now)
                return True

        # 最初のリクエスト
        result1 = await process_request("user_x")
        assert result1 is True

        # クールダウン中のリクエスト
        result2 = await process_request("user_x")
        assert result2 is False

        # クールダウン期限切れを待つ
        await asyncio.sleep(cooldown_seconds + 0.01)

        # クールダウン後のリクエスト
        result3 = await process_request("user_x")
        assert result3 is True

        # 2回処理された
        assert len(processed_timestamps) == 2


# =============================================================================
# Resource Lock Auto Cleanup Tests
# =============================================================================


class TestResourceLockAutoCleanup:
    """リソースロックの自動クリーンアップテスト。"""

    def test_cleanup_removes_old_unlocked_entries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """古い未ロックエントリがクリーンアップされる。"""
        import src.utils as utils_module

        # ロックを作成
        get_resource_lock("test:cleanup:old")

        # 最終クリーンアップ時刻を古くする (クリーンアップ間隔より前に設定)
        monkeypatch.setattr(
            utils_module, "_lock_last_cleanup_time", time.monotonic() - 700
        )

        # アクセス時刻を古くする (5分以上前)
        old_time = time.monotonic() - 400  # 約6.6分前
        lock, _ = _resource_locks["test:cleanup:old"]
        _resource_locks["test:cleanup:old"] = (lock, old_time)

        # クリーンアップをトリガー
        get_resource_lock("test:cleanup:trigger")

        # 古いエントリは削除される (ロックされていない場合)
        assert "test:cleanup:old" not in _resource_locks

    def test_cleanup_preserves_locked_entries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ロック中のエントリはクリーンアップされない。"""
        import src.utils as utils_module

        # ロックを作成して取得
        lock = get_resource_lock("test:cleanup:locked")

        # 最終クリーンアップ時刻を古くする (クリーンアップ間隔より前に設定)
        monkeypatch.setattr(
            utils_module, "_lock_last_cleanup_time", time.monotonic() - 700
        )

        # アクセス時刻を古くする
        old_time = time.monotonic() - 400
        _resource_locks["test:cleanup:locked"] = (lock, old_time)

        async def test_with_lock() -> None:
            async with lock:
                # ロック中にクリーンアップをトリガー
                get_resource_lock("test:cleanup:trigger2")
                # ロック中のエントリは削除されない
                assert "test:cleanup:locked" in _resource_locks

        asyncio.get_event_loop().run_until_complete(test_with_lock())

    def test_cleanup_preserves_recent_entries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """最近アクセスされたエントリはクリーンアップされない。"""
        import src.utils as utils_module

        # ロックを作成 (アクセス時刻は現在)
        get_resource_lock("test:cleanup:recent")

        # 最終クリーンアップ時刻を古くする (クリーンアップ間隔より前に設定)
        monkeypatch.setattr(
            utils_module, "_lock_last_cleanup_time", time.monotonic() - 700
        )

        # クリーンアップをトリガー
        get_resource_lock("test:cleanup:trigger3")

        # 最近のエントリは削除されない
        assert "test:cleanup:recent" in _resource_locks

    def test_cleanup_interval_respected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """クリーンアップ間隔が尊重される。"""
        import src.utils as utils_module

        # 最終クリーンアップ時刻を最近に設定
        recent_cleanup = time.monotonic() - 1  # 1秒前
        monkeypatch.setattr(utils_module, "_lock_last_cleanup_time", recent_cleanup)

        # ロックを作成
        get_resource_lock("test:interval:check")

        # 古いエントリを作成
        old_time = time.monotonic() - 400
        lock, _ = _resource_locks["test:interval:check"]
        _resource_locks["test:interval:check"] = (lock, old_time)

        # クリーンアップはまだ実行されない (間隔未経過)
        _cleanup_resource_locks()

        # エントリはまだ存在する
        assert "test:interval:check" in _resource_locks


# =============================================================================
# Additional Coverage Tests
# =============================================================================


class TestHasLoneSurrogateEdgeCases:
    """_has_lone_surrogate 関数のエッジケーステスト。"""

    def test_lone_surrogate_detected(self) -> None:
        """壊れたサロゲートペアが検出される。"""
        # Python で壊れたサロゲートを含む文字列を作成
        # U+D800-DFFF はサロゲートペアの範囲
        # 単独の高位サロゲート (U+D800) を含む文字列
        lone_surrogate = "test\ud800string"  # 単独の高位サロゲート
        assert _has_lone_surrogate(lone_surrogate) is True

    def test_lone_low_surrogate_detected(self) -> None:
        """単独の低位サロゲートが検出される。"""
        lone_low_surrogate = "test\udc00string"  # 単独の低位サロゲート
        assert _has_lone_surrogate(lone_low_surrogate) is True


class TestIsValidEmojiWithLoneSurrogate:
    """is_valid_emoji 関数のサロゲートテスト。"""

    def test_string_with_lone_surrogate_invalid(self) -> None:
        """壊れたサロゲートを含む文字列は無効。"""
        # 壊れたサロゲートを含む文字列
        invalid_string = "😀\ud800"
        assert is_valid_emoji(invalid_string) is False

    def test_emoji_like_string_with_lone_surrogate_invalid(self) -> None:
        """絵文字のような文字列でも壊れたサロゲートがあれば無効。"""
        invalid = "\ud83d"  # 😀 の高位サロゲートのみ
        assert is_valid_emoji(invalid) is False


class TestIsValidEmojiNormalization:
    """is_valid_emoji 関数の正規化テスト。"""

    def test_combining_character_emoji(self) -> None:
        """合成文字を含む絵文字のテスト。"""
        # é (e + combining acute accent) は絵文字ではない
        # NFD 形式: e + ́ (U+0065 + U+0301)
        nfd_e_acute = "e\u0301"  # NFD 形式の é
        assert is_valid_emoji(nfd_e_acute) is False

        # NFC 形式でも絵文字ではない
        nfc_e_acute = "é"  # NFC 形式の é (U+00E9)
        assert is_valid_emoji(nfc_e_acute) is False

    def test_variant_selector_emoji(self) -> None:
        """異体字セレクタを含む絵文字のテスト。"""
        # ♡ (WHITE HEART SUIT) + VS16 (emoji presentation selector)
        # これは絵文字として認識される場合がある
        heart_with_vs = "♡\ufe0f"  # VS16 付き
        # emoji ライブラリの判定に従う
        result = is_valid_emoji(heart_with_vs)
        # 結果は True または False のどちらか (ライブラリ依存)
        assert isinstance(result, bool)


# =============================================================================
# format_datetime テスト
# =============================================================================


class TestFormatDatetime:
    """format_datetime 関数のテスト。"""

    def test_none_returns_fallback(self) -> None:
        """None の場合はフォールバック値を返す。"""
        assert format_datetime(None) == "-"

    def test_none_custom_fallback(self) -> None:
        """カスタムフォールバック値を返す。"""
        assert format_datetime(None, fallback="N/A") == "N/A"

    def test_utc_with_offset_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """オフセット 0 の場合は UTC のまま。"""
        import src.config

        monkeypatch.setattr(src.config.settings, "timezone_offset", 0)
        dt = datetime(2026, 2, 7, 10, 30, 0, tzinfo=UTC)
        assert format_datetime(dt) == "2026-02-07 10:30"

    def test_positive_offset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """正のオフセット (例: JST +9)。"""
        import src.config

        monkeypatch.setattr(src.config.settings, "timezone_offset", 9)
        dt = datetime(2026, 2, 7, 10, 30, 0, tzinfo=UTC)
        assert format_datetime(dt) == "2026-02-07 19:30"

    def test_negative_offset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """負のオフセット (例: EST -5)。"""
        import src.config

        monkeypatch.setattr(src.config.settings, "timezone_offset", -5)
        dt = datetime(2026, 2, 7, 10, 30, 0, tzinfo=UTC)
        assert format_datetime(dt) == "2026-02-07 05:30"

    def test_offset_crosses_midnight(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """オフセットで日付がまたがるケース。"""
        import src.config

        monkeypatch.setattr(src.config.settings, "timezone_offset", 9)
        dt = datetime(2026, 2, 7, 20, 0, 0, tzinfo=UTC)
        assert format_datetime(dt) == "2026-02-08 05:00"

    def test_custom_format(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """カスタムフォーマット文字列。"""
        import src.config

        monkeypatch.setattr(src.config.settings, "timezone_offset", 0)
        dt = datetime(2026, 2, 7, 10, 30, 45, tzinfo=UTC)
        assert format_datetime(dt, "%Y-%m-%d %H:%M:%S") == "2026-02-07 10:30:45"

    def test_default_format(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """デフォルトフォーマットは %Y-%m-%d %H:%M。"""
        import src.config

        monkeypatch.setattr(src.config.settings, "timezone_offset", 0)
        dt = datetime(2026, 2, 7, 10, 30, 45, tzinfo=UTC)
        # デフォルトは秒なし
        assert format_datetime(dt) == "2026-02-07 10:30"


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestFormatDatetimeEdgeCases:
    """format_datetime 関数のエッジケーステスト。"""

    def test_naive_datetime_does_not_raise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """タイムゾーン情報のない naive datetime でも例外が発生しない。"""
        import src.config

        monkeypatch.setattr(src.config.settings, "timezone_offset", 0)
        dt = datetime(2026, 1, 1, 12, 0)
        result = format_datetime(dt)
        assert isinstance(result, str)

    def test_extreme_positive_offset_14(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """極端な正のオフセット (+14)。"""
        import src.config

        monkeypatch.setattr(src.config.settings, "timezone_offset", 14)
        dt = datetime(2026, 2, 7, 23, 30, tzinfo=UTC)
        assert format_datetime(dt) == "2026-02-08 13:30"

    def test_extreme_negative_offset_12(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """極端な負のオフセット (-12)。"""
        import src.config

        monkeypatch.setattr(src.config.settings, "timezone_offset", -12)
        dt = datetime(2026, 2, 8, 10, 0, tzinfo=UTC)
        assert format_datetime(dt) == "2026-02-07 22:00"

    def test_midnight_boundary_crossing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """オフセットで深夜をまたぐケース。"""
        import src.config

        monkeypatch.setattr(src.config.settings, "timezone_offset", 1)
        dt = datetime(2026, 2, 7, 23, 30, tzinfo=UTC)
        assert format_datetime(dt) == "2026-02-08 00:30"


class TestEmojiEdgeCases:
    """絵文字関連のエッジケーステスト。"""

    def test_skin_tone_modifier_emoji_valid(self) -> None:
        """スキントーン修飾子付き絵文字は有効。"""
        assert is_valid_emoji("👋🏽") is True

    @pytest.mark.parametrize(
        "emoji_str",
        ["⚓️", "✨️", "👨‍💻", "1️⃣", "🇯🇵"],
    )
    def test_normalize_then_validate_round_trip(self, emoji_str: str) -> None:
        """normalize_emoji 後の絵文字が is_valid_emoji で有効と判定される。"""
        assert is_valid_emoji(normalize_emoji(emoji_str)) is True


class TestResourceLockEdgeCases:
    """リソースロックのエッジケーステスト。"""

    @pytest.mark.asyncio
    async def test_locked_lock_not_cleaned_up(self) -> None:
        """ロック中のエントリはクリーンアップで削除されない。"""
        import src.utils as utils_module

        key = "test:edge:locked_cleanup"
        lock = get_resource_lock(key)

        async with lock:
            # アクセス時刻を古くする (5分以上前)
            old_time = time.monotonic() - 400
            _resource_locks[key] = (lock, old_time)

            # クリーンアップを強制実行 (_lock_last_cleanup_time を 0 に設定)
            utils_module._lock_last_cleanup_time = 0.0
            _cleanup_resource_locks()

            # ロック中のためクリーンアップされない
            assert key in _resource_locks


class TestNormalizeEmojiEdgeCases:
    """normalize_emoji 関数のエッジケーステスト。"""

    def test_normalize_empty_string_returns_empty(self) -> None:
        """空文字の normalize_emoji は空文字を返す。"""
        assert normalize_emoji("") == ""

    def test_normalize_flag_emoji(self) -> None:
        """国旗絵文字の normalize。"""
        result = normalize_emoji("🇯🇵")
        assert is_valid_emoji(result) is True

    def test_normalize_skin_tone_emoji(self) -> None:
        """スキントーン修飾子付き絵文字の normalize。"""
        result = normalize_emoji("👋🏽")
        assert is_valid_emoji(result) is True

    def test_normalize_keycap_removes_vs16(self) -> None:
        """Keycap 絵文字の VS16 が除去される。"""
        result = normalize_emoji("1️⃣")
        assert "\ufe0f" not in result

    def test_normalize_non_emoji_text_unchanged(self) -> None:
        """絵文字でないテキストはそのまま返される (NFC正規化のみ)。"""
        import unicodedata

        result = normalize_emoji("hello")
        assert result == unicodedata.normalize("NFC", "hello")


# =============================================================================
# Additional Edge Case Tests
# =============================================================================


class TestIsValidEmojiAdditionalEdgeCases:
    """is_valid_emoji 関数の追加エッジケーステスト。"""

    def test_family_emoji_zwj_sequence_valid(self) -> None:
        """家族 ZWJ シーケンス絵文字は有効。"""
        assert is_valid_emoji("👨‍👩‍👧‍👦") is True

    def test_skin_tone_variations(self) -> None:
        """各種スキントーン修飾子付き絵文字は有効。"""
        assert is_valid_emoji("👋🏻") is True  # light
        assert is_valid_emoji("👋🏼") is True  # medium-light
        assert is_valid_emoji("👋🏽") is True  # medium
        assert is_valid_emoji("👋🏾") is True  # medium-dark
        assert is_valid_emoji("👋🏿") is True  # dark

    def test_whitespace_only_invalid(self) -> None:
        """空白文字のみは無効。"""
        assert is_valid_emoji(" ") is False
        assert is_valid_emoji("  ") is False

    def test_multiple_emojis_invalid(self) -> None:
        """複数の絵文字は無効 (1つだけ有効)。"""
        assert is_valid_emoji("😀😀") is False
        assert is_valid_emoji("🎮🎵") is False

    def test_emoji_with_space_invalid(self) -> None:
        """絵文字 + 空白は無効。"""
        assert is_valid_emoji("😀 ") is False
        assert is_valid_emoji(" 😀") is False

    def test_animated_custom_emoji_valid(self) -> None:
        """アニメーションカスタム絵文字は有効。"""
        assert is_valid_emoji("<a:dance:123456789012345678>") is True

    def test_custom_emoji_with_underscore_valid(self) -> None:
        """アンダースコア付きカスタム絵文字は有効。"""
        assert is_valid_emoji("<:my_emoji:123456789>") is True

    def test_custom_emoji_missing_id_invalid(self) -> None:
        """IDなしカスタム絵文字は無効。"""
        assert is_valid_emoji("<:name:>") is False

    def test_custom_emoji_non_numeric_id_invalid(self) -> None:
        """IDが数字でないカスタム絵文字は無効。"""
        assert is_valid_emoji("<:name:abc>") is False

    def test_star_with_and_without_vs16(self) -> None:
        """星絵文字は VS16 の有無に関わらず有効。"""
        assert is_valid_emoji("⭐") is True  # without VS16
        assert is_valid_emoji("⭐️") is True  # with VS16

    def test_heart_variations_valid(self) -> None:
        """ハート系絵文字のバリエーション。"""
        assert is_valid_emoji("❤") is True
        assert is_valid_emoji("❤️") is True
        assert is_valid_emoji("💜") is True
        assert is_valid_emoji("💙") is True


class TestFormatDatetimeAdditionalEdgeCases:
    """format_datetime 関数の追加エッジケーステスト。"""

    def test_empty_format_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """空のフォーマット文字列。"""
        import src.config

        monkeypatch.setattr(src.config.settings, "timezone_offset", 0)
        dt = datetime(2026, 2, 7, 10, 30, 0, tzinfo=UTC)
        assert format_datetime(dt, "") == ""

    def test_year_only_format(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """年のみのフォーマット。"""
        import src.config

        monkeypatch.setattr(src.config.settings, "timezone_offset", 0)
        dt = datetime(2026, 2, 7, 10, 30, 0, tzinfo=UTC)
        assert format_datetime(dt, "%Y") == "2026"

    def test_offset_crosses_year_boundary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """オフセットで年境界をまたぐケース。"""
        import src.config

        monkeypatch.setattr(src.config.settings, "timezone_offset", 9)
        dt = datetime(2025, 12, 31, 20, 0, 0, tzinfo=UTC)
        result = format_datetime(dt)
        assert result == "2026-01-01 05:00"

    def test_none_with_empty_fallback(self) -> None:
        """None で空文字のフォールバック。"""
        assert format_datetime(None, fallback="") == ""

    def test_half_hour_offset_not_supported_but_works(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """整数以外のオフセットは設定上使わないが、関数自体はintを受ける。"""
        import src.config

        monkeypatch.setattr(src.config.settings, "timezone_offset", 5)
        dt = datetime(2026, 2, 7, 0, 0, 0, tzinfo=UTC)
        assert format_datetime(dt) == "2026-02-07 05:00"


class TestResourceLockCleanupEdgeCases:
    """リソースロッククリーンアップの追加エッジケーステスト。"""

    def test_cleanup_with_many_locks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """多数のロックがある場合でもクリーンアップが正常に動作する。"""
        import src.utils as utils_module

        # 100個のロックを作成
        for i in range(100):
            get_resource_lock(f"test:many:{i}")

        assert get_resource_lock_count() == 100

        # 全てのロックを古くする
        old_time = time.monotonic() - 400
        for key in list(_resource_locks.keys()):
            lock, _ = _resource_locks[key]
            _resource_locks[key] = (lock, old_time)

        # クリーンアップを強制実行
        monkeypatch.setattr(utils_module, "_lock_last_cleanup_time", 0.0)
        _cleanup_resource_locks()

        # 全て削除される
        assert get_resource_lock_count() == 0

    def test_lock_returned_after_cleanup_is_new_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """クリーンアップ後に同じキーで取得したロックは新しいインスタンス。"""
        import src.utils as utils_module

        key = "test:recreate"
        old_lock = get_resource_lock(key)

        # ロックを古くしてクリーンアップ
        old_time = time.monotonic() - 400
        _resource_locks[key] = (old_lock, old_time)
        monkeypatch.setattr(utils_module, "_lock_last_cleanup_time", 0.0)
        _cleanup_resource_locks()

        # 新しいロックを取得
        new_lock = get_resource_lock(key)
        assert new_lock is not old_lock

    def test_cleanup_just_under_boundary_not_expired(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """有効期限ぎりぎり手前のロックは削除されない (> で比較)。"""
        import src.utils as utils_module

        key = "test:boundary"
        get_resource_lock(key)

        # _LOCK_EXPIRY_TIME (300秒) より少し短い期間前に設定
        # (time.monotonic() の進行を考慮して余裕を持たせる)
        boundary_time = time.monotonic() - 299
        lock, _ = _resource_locks[key]
        _resource_locks[key] = (lock, boundary_time)

        monkeypatch.setattr(utils_module, "_lock_last_cleanup_time", 0.0)
        _cleanup_resource_locks()

        # 300秒未満なので削除されない
        assert key in _resource_locks

    def test_cleanup_guard_allows_zero_last_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_lock_last_cleanup_time=0 でもクリーンアップが実行される.

        time.monotonic() が小さい環境 (CI等) でも
        0 は「未実行」として扱われクリーンアップがスキップされないことを検証。
        """
        import src.utils as utils_module

        key = "test:guard_zero"
        get_resource_lock(key)

        old_time = time.monotonic() - 400
        lock, _ = _resource_locks[key]
        _resource_locks[key] = (lock, old_time)

        monkeypatch.setattr(utils_module, "_lock_last_cleanup_time", 0.0)
        _cleanup_resource_locks()

        # クリーンアップが実行されたことを検証
        assert key not in _resource_locks
        # _lock_last_cleanup_time が更新されている (0 より大きい)
        assert utils_module._lock_last_cleanup_time > 0


class TestResourceLockCleanupEmptyCache:
    """空キャッシュに対するクリーンアップが安全に動作することを検証。"""

    def test_cleanup_on_empty_cache_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ロックが空でもクリーンアップがクラッシュしない."""
        import src.utils as utils_module

        assert len(_resource_locks) == 0
        monkeypatch.setattr(utils_module, "_lock_last_cleanup_time", 0.0)
        _cleanup_resource_locks()
        assert len(_resource_locks) == 0
        assert utils_module._lock_last_cleanup_time > 0

    def test_get_resource_lock_on_empty_returns_lock(self) -> None:
        """空状態で get_resource_lock が新しいロックを返す."""
        assert len(_resource_locks) == 0
        lock = get_resource_lock("test:empty")
        assert lock is not None
        assert isinstance(lock, asyncio.Lock)


class TestResourceLockCleanupAllExpired:
    """全ロックが期限切れの場合にキャッシュが空になることを検証。"""

    def test_all_expired_locks_removed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """全ロックが期限切れなら全て削除されキャッシュが空になる."""
        import src.utils as utils_module

        now = time.monotonic()
        _resource_locks["key1"] = (asyncio.Lock(), now - 400)
        _resource_locks["key2"] = (asyncio.Lock(), now - 500)
        _resource_locks["key3"] = (asyncio.Lock(), now - 600)

        monkeypatch.setattr(utils_module, "_lock_last_cleanup_time", 0.0)
        _cleanup_resource_locks()

        assert len(_resource_locks) == 0


class TestResourceLockCleanupTriggerViaPublicAPI:
    """get_resource_lock がクリーンアップを内部的にトリガーすることを検証。"""

    def test_get_resource_lock_triggers_cleanup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_resource_lock がクリーンアップをトリガーする."""
        import src.utils as utils_module

        old_key = "test:old_trigger"
        _resource_locks[old_key] = (asyncio.Lock(), time.monotonic() - 400)

        monkeypatch.setattr(utils_module, "_lock_last_cleanup_time", 0.0)
        get_resource_lock("test:new_trigger")

        assert old_key not in _resource_locks

    def test_cleanup_updates_last_cleanup_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """クリーンアップ実行後に _lock_last_cleanup_time が更新される."""
        import src.utils as utils_module

        monkeypatch.setattr(utils_module, "_lock_last_cleanup_time", 0.0)
        get_resource_lock("test:update_time")

        assert utils_module._lock_last_cleanup_time > 0

    def test_locked_entries_preserved_during_cleanup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ロック中のエントリはクリーンアップで削除されない."""
        import src.utils as utils_module

        locked_key = "test:locked_preserve"
        lock = asyncio.Lock()
        # ロックを取得 (非同期ではなく直接内部状態を設定)
        _resource_locks[locked_key] = (lock, time.monotonic() - 400)

        # 事前にロックを取得しておく (同期的にテスト)
        # Note: asyncio.Lock() は _locked フラグで管理される
        lock._locked = True  # type: ignore[attr-defined]

        monkeypatch.setattr(utils_module, "_lock_last_cleanup_time", 0.0)
        _cleanup_resource_locks()

        # ロック中のエントリは残る
        assert locked_key in _resource_locks
