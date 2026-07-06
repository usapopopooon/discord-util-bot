"""Tests for welcome banner rendering."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from src.services.welcome_banner_service import (
    WelcomeBannerInput,
    WelcomeBannerService,
)


def _make_avatar_bytes() -> bytes:
    image = Image.new("RGBA", (256, 256), (245, 188, 218, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_create_renders_png_with_template_dimensions() -> None:
    service = WelcomeBannerService()

    output = service.create(
        WelcomeBannerInput(
            display_name="ちるちる",
            username="chill",
            guild_name="CHILLカフェ",
            headline_text="ちるちる さんが入店しました",
            member_count=128,
            avatar_bytes=_make_avatar_bytes(),
        )
    )

    with Image.open(BytesIO(output)) as image:
        assert image.size == (1100, 500)
        assert image.mode == "RGBA"


def test_create_uses_fallback_avatar_when_avatar_bytes_are_invalid() -> None:
    service = WelcomeBannerService()

    output = service.create(
        WelcomeBannerInput(
            display_name="ちるちる",
            username="chill",
            guild_name="CHILLカフェ",
            headline_text="ちるちる さんが入店しました",
            member_count=128,
            avatar_bytes=b"not an image",
        )
    )

    with Image.open(BytesIO(output)) as image:
        assert image.size == (1100, 500)
