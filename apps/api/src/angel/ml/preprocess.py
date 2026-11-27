"""Зургийг decode хийж, CLIP-ийн оролт болгон бэлтгэнэ.

Зургийг model-ийн оролт болгодог ЦОРЫН ГАНЦ газар. Ingestion, хайлт хоёул үүнийг ашигладаг тул
каталог ба query-ийн embedding үргэлж ижил preprocessing-оор гарна.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from pathlib import Path
from typing import BinaryIO, Literal

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError

CLIP_SIZE = 224
# Бүтнээр decode хийхээс өмнө үүнээс том зургийг татгалзана (decompression bomb-оос хамгаална).
MAX_PIXELS = 50_000_000
# Каталогийн зургуудын studio дэвсгэр цагаан тул padding болон ил тод хэсгийг цагаанаар дүүргэвэл
# байгалийн харагдана.
BACKGROUND = (255, 255, 255)

ResizeMode = Literal["crop", "pad"]
ImageSource = str | Path | bytes | BinaryIO


class InvalidImageError(ValueError):
    """Оролт decode хийгдэхгүй эсвэл хэмжээ нь зөвшөөрөгдөхгүй зураг."""


def load_image(
    source: ImageSource,
    *,
    min_side: int | None = None,
    formats: Sequence[str] | None = None,
    max_pixels: int = MAX_PIXELS,
) -> Image.Image:
    """Зургийг зөв чиглэлтэй RGB болгон decode хийж, EXIF metadata-г хасна.

    `min_side` өгвөл JPEG decoder зургийг 1/2, 1/4, 1/8 хэмжээгээр (хоёр тал нь `min_side`-аас
    багагүй байхаар) decode хийж хурдасгана. Бусад формат үүнийг тооцохгүй. Найдваргүй оролтод
    (upload) `formats` болон бага `max_pixels` өгнө. `formats` бол зөвшөөрөх Pillow форматууд:
    бусдыг файлын нэр, төрлөөс үл хамааран magic bytes-аар нь таньж татгалзана. Зөвхөн эхний
    frame-ийг decode хийнэ.
    """
    file: str | Path | BinaryIO = io.BytesIO(source) if isinstance(source, bytes) else source
    try:
        image = Image.open(file, formats=None if formats is None else list(formats))
        width, height = image.size
        if width <= 0 or height <= 0 or width * height > max_pixels:
            raise InvalidImageError(f"image dimensions {width}x{height} are not acceptable")
        if min_side is not None and image.format == "JPEG":
            image.draft("RGB", (min_side, min_side))
        image.load()
        return _strip_metadata(_to_rgb(ImageOps.exif_transpose(image)))
    except InvalidImageError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
    ) as exc:
        raise InvalidImageError(f"cannot decode image: {exc}") from exc


def _strip_metadata(image: Image.Image) -> Image.Image:
    """EXIF (камер, GPS ...), ICC profile, comment-ийг хасна. Зургийн чиглэлийг аль хэдийн зассан
    тул эдгээр цаашид хэрэггүй: decode хийсэн зургийг дахин encode хийхгүй."""
    image.getexif().clear()
    image.info.clear()
    return image


def _to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, BACKGROUND)
        canvas.paste(rgba, mask=rgba.getchannel("A"))
        return canvas
    return image.convert("RGB")


def to_clip_array(image: Image.Image, mode: ResizeMode = "pad") -> NDArray[np.uint8]:
    """224x224 uint8 HWC array болгон жижигрүүлнэ.

    `crop` бол CLIP-ийн стандарт арга: богино талыг 224 болгоод голоос нь тайрна. Ингэхэд босоо
    хувцасны дээд, доод хэсэг тасардаг. `pad` хувцсыг бүтнээр нь үлдээж, дөрвөлжин болтол дэвсгэр
    нэмнэ.
    """
    width, height = image.size
    if mode == "crop":
        scale = CLIP_SIZE / min(width, height)
        resized = image.resize(
            (max(CLIP_SIZE, round(width * scale)), max(CLIP_SIZE, round(height * scale))),
            Image.Resampling.BICUBIC,
        )
        left = (resized.width - CLIP_SIZE) // 2
        top = (resized.height - CLIP_SIZE) // 2
        resized = resized.crop((left, top, left + CLIP_SIZE, top + CLIP_SIZE))
    else:
        scale = CLIP_SIZE / max(width, height)
        resized = image.resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            Image.Resampling.BICUBIC,
        )
        canvas = Image.new("RGB", (CLIP_SIZE, CLIP_SIZE), BACKGROUND)
        canvas.paste(resized, ((CLIP_SIZE - resized.width) // 2, (CLIP_SIZE - resized.height) // 2))
        resized = canvas
    return np.asarray(resized, dtype=np.uint8)
