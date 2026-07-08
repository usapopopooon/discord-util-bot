"""Welcome feature package smoke tests."""

from src.features.welcome import (
    WELCOME_EMBED_COLOR,
    WelcomeBannerService,
    WelcomeCog,
    build_welcome_status_message,
)


def test_welcome_feature_facade_exports() -> None:
    assert WelcomeCog.__name__ == "WelcomeCog"
    assert WelcomeBannerService.__name__ == "WelcomeBannerService"
    assert WELCOME_EMBED_COLOR == 0xE0A2EB
    assert build_welcome_status_message(None).startswith("welcome投稿は無効です。")
