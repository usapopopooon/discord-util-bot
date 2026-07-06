"""Welcome バナー画像を生成するサービス。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

__all__ = ["WelcomeBannerInput", "WelcomeBannerService"]

WelcomeFont = ImageFont.FreeTypeFont | ImageFont.ImageFont


@dataclass(frozen=True, slots=True)
class WelcomeBannerInput:
    """welcome バナーに描画する内容。"""

    display_name: str
    username: str
    guild_name: str
    headline_text: str
    member_count: int | None = None
    avatar_bytes: bytes | None = None


@dataclass(frozen=True, slots=True)
class FittedText:
    text: str
    font: WelcomeFont
    font_size: int


class WelcomeBannerService:
    """テンプレート画像へ丸アイコンと welcome テキストを合成する。"""

    def __init__(self, template_path: Path | None = None) -> None:
        self.template_path = template_path or _default_template_path()

    def create(self, input_data: WelcomeBannerInput) -> bytes:
        """welcome バナー PNG を生成する。"""
        with Image.open(self.template_path) as template_image:
            template = template_image.convert("RGBA")

        width, height = template.size
        avatar_size = round(height * 0.5)
        avatar_top = round(height * 0.1)
        avatar_left = round((width - avatar_size) / 2)

        avatar = self._create_avatar(input_data, avatar_size)
        template.alpha_composite(
            avatar,
            (
                avatar_left - round(avatar_size * 0.224),
                avatar_top - round(avatar_size * 0.224),
            ),
        )
        template.alpha_composite(self._create_text_layer(input_data, width, height))

        output = BytesIO()
        template.save(output, format="PNG")
        return output.getvalue()

    def _create_avatar(
        self, input_data: WelcomeBannerInput, avatar_size: int
    ) -> Image.Image:
        shadow_pad = round(avatar_size * 0.224)
        layer_size = avatar_size + shadow_pad * 2
        inner_size = round(avatar_size * 0.88)
        border = round((avatar_size - inner_size) / 2)
        center = shadow_pad + avatar_size / 2

        layer = Image.new("RGBA", (layer_size, layer_size), (0, 0, 0, 0))
        shadow = Image.new("RGBA", (layer_size, layer_size), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        radius = avatar_size / 2 - round(avatar_size * 0.04)
        shadow_draw.ellipse(
            (
                center - radius,
                center - radius + round(avatar_size * 0.016),
                center + radius,
                center + radius + round(avatar_size * 0.016),
            ),
            fill=(89, 66, 86, 54),
        )
        layer.alpha_composite(
            shadow.filter(ImageFilter.GaussianBlur(avatar_size * 0.034))
        )

        frame = Image.new("RGBA", (layer_size, layer_size), (0, 0, 0, 0))
        frame_draw = ImageDraw.Draw(frame)
        outer_radius = avatar_size / 2 - 2
        frame_draw.ellipse(
            (
                center - outer_radius,
                center - outer_radius,
                center + outer_radius,
                center + outer_radius,
            ),
            fill=(255, 255, 255, 242),
        )
        inset_radius = avatar_size / 2 - 7
        frame_draw.ellipse(
            (
                center - inset_radius,
                center - inset_radius,
                center + inset_radius,
                center + inset_radius,
            ),
            outline=(255, 255, 255, 240),
            width=max(4, round(avatar_size * 0.028)),
        )
        layer.alpha_composite(frame)

        avatar = self._load_avatar_image(input_data, inner_size)
        avatar.putalpha(_circle_mask(inner_size))
        layer.alpha_composite(avatar, (shadow_pad + border, shadow_pad + border))
        return layer

    def _load_avatar_image(
        self, input_data: WelcomeBannerInput, inner_size: int
    ) -> Image.Image:
        if input_data.avatar_bytes:
            try:
                with Image.open(BytesIO(input_data.avatar_bytes)) as avatar_image:
                    return ImageOps.fit(
                        avatar_image.convert("RGBA"),
                        (inner_size, inner_size),
                        method=Image.Resampling.LANCZOS,
                    )
            except OSError:
                pass

        return _create_fallback_avatar(input_data, inner_size)

    def _create_text_layer(
        self, input_data: WelcomeBannerInput, width: int, height: int
    ) -> Image.Image:
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        headline, footer = self._create_fitted_text(input_data, width, height)
        headline_y, footer_y = _text_positions(height, headline.font_size)

        _draw_centered_text(
            draw,
            (width / 2, headline_y),
            headline.text,
            headline.font,
            (150, 104, 96, 255),
        )
        _draw_centered_text(
            draw,
            (width / 2, footer_y),
            footer.text,
            footer.font,
            (150, 104, 96, 255),
        )
        return layer

    def _create_fitted_text(
        self, input_data: WelcomeBannerInput, width: int, height: int
    ) -> tuple[FittedText, FittedText]:
        headline = _fit_text(
            input_data.headline_text,
            base_font_size=round(height * 0.086),
            min_font_size=round(height * 0.052),
            max_width=round(width * 0.78),
            max_characters=64,
        )
        footer_text = (
            f"Member #{input_data.member_count}"
            if input_data.member_count is not None
            else "Welcome aboard"
        )
        footer = _fit_text(
            footer_text,
            base_font_size=round(height * 0.064),
            min_font_size=round(height * 0.044),
            max_width=round(width * 0.5),
            max_characters=24,
        )
        return headline, footer


def _default_template_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "static"
        / "img"
        / "welcome-chill-fluffy-template.png"
    )


def _circle_mask(size: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    return mask


def _create_fallback_avatar(input_data: WelcomeBannerInput, size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (248, 245, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse((0, 0, size - 1, size - 1), fill=(248, 245, 255, 255))

    initial = next(
        iter((input_data.display_name or input_data.username or "?").strip()), "?"
    )
    font = _load_font(round(size * 0.48))
    _draw_centered_text(draw, (size / 2, size / 2), initial, font, (199, 120, 189, 255))
    return image


def _text_positions(height: int, headline_font_size: int) -> tuple[int, int]:
    avatar_size = round(height * 0.5)
    avatar_top = round(height * 0.1)
    headline_y = avatar_top + avatar_size + round(height * 0.11)
    footer_y = headline_y + round(headline_font_size * 1.42)
    return headline_y, footer_y


def _fit_text(
    value: str,
    *,
    base_font_size: int,
    min_font_size: int,
    max_width: int,
    max_characters: int,
) -> FittedText:
    text = _truncate_characters(value.strip(), max_characters)
    if not text:
        text = "Welcome"

    measure_image = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(measure_image)

    for font_size in range(base_font_size, min_font_size - 1, -1):
        font = _load_font(font_size)
        if _measure_text_width(draw, text, font) <= max_width:
            return FittedText(text=text, font=font, font_size=font_size)

    font = _load_font(min_font_size)
    return FittedText(
        text=_truncate_to_width(draw, text, font, max_width),
        font=font,
        font_size=min_font_size,
    )


def _truncate_characters(value: str, max_length: int) -> str:
    characters = list(value)
    if len(characters) <= max_length:
        return value
    return f"{''.join(characters[: max_length - 3])}..."


def _truncate_to_width(
    draw: ImageDraw.ImageDraw,
    value: str,
    font: WelcomeFont,
    max_width: int,
) -> str:
    ellipsis = "..."
    characters = list(value)
    while (
        characters
        and _measure_text_width(draw, f"{''.join(characters)}{ellipsis}", font)
        > max_width
    ):
        characters.pop()
    return f"{''.join(characters)}{ellipsis}" if characters else ellipsis


def _measure_text_width(draw: ImageDraw.ImageDraw, text: str, font: WelcomeFont) -> int:
    left, _top, right, _bottom = draw.textbbox((0, 0), text, font=font)
    return int(right - left)


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[float, float],
    text: str,
    font: WelcomeFont,
    fill: tuple[int, int, int, int],
) -> None:
    draw.text(position, text, font=font, fill=fill, anchor="mm")


def _load_font(size: int) -> WelcomeFont:
    font_path = _find_font_path()
    if font_path is not None:
        try:
            return ImageFont.truetype(str(font_path), size=size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


@lru_cache(maxsize=1)
def _find_font_path() -> Path | None:
    env_path = os.environ.get("WELCOME_BANNER_FONT_PATH")
    if env_path:
        path = Path(env_path)
        if path.exists():
            return path

    exact_candidates = (
        Path("/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc"),
        Path("/System/Library/Fonts/SFNSRounded.ttf"),
        Path("/usr/share/fonts/truetype/mplus/mplus-1c-regular.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for path in exact_candidates:
        if path.exists():
            return path

    search_dirs = (
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
        Path("/usr/share/fonts"),
        Path(__file__).resolve().parents[2] / "static" / "fonts",
    )
    token_groups = (
        ("hiragino", "maru"),
        ("丸", "ゴ"),
        ("rounded",),
        ("mplus",),
        ("noto", "cjk"),
        ("gothic",),
        ("sans",),
    )

    for tokens in token_groups:
        for path in _iter_font_files(search_dirs):
            filename = path.name.casefold()
            if all(token.casefold() in filename for token in tokens):
                return path
    return None


def _iter_font_files(search_dirs: tuple[Path, ...]) -> list[Path]:
    paths: list[Path] = []
    for directory in search_dirs:
        if not directory.exists():
            continue
        paths.extend(
            sorted(
                path
                for path in directory.rglob("*")
                if path.suffix.casefold() in {".ttf", ".ttc", ".otf"}
            )
        )
    return paths
