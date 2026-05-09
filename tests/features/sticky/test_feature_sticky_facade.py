"""Sticky feature package smoke tests."""

from src.features.sticky import StickyCog, api_router


def test_sticky_feature_facade_exports() -> None:
    assert StickyCog.__name__ == "StickyCog"
    assert api_router is not None
