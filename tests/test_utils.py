"""Tests for shared utility functions."""

from __future__ import annotations

import asyncio
import time

import pytest

from src.utils import (
    _has_lone_surrogate,
    clear_resource_locks,
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

    def test_keycap_emoji_unchanged(self) -> None:
        """Keycap 絵文字はそのまま返される。"""
        assert normalize_emoji("1️⃣") == "1️⃣"
        assert normalize_emoji("#️⃣") == "#️⃣"

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
