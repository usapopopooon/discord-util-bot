"""AutoMod feature package smoke tests."""

from src.features.automod import AutoModCog, api_router


def test_automod_feature_facade_exports() -> None:
    assert AutoModCog.__name__ == "AutoModCog"
    assert api_router is not None
