"""Зураг дээрх хувцасны хэсгүүдийг олох (localizer).

Хайлтад нэг зургаас нэг vector гаргадаг. Тиймээс олон хувцастай зургаас (цамц + өмд + гутал) бүгд
холилдсон vector гарна. Localizer зургийг хэсгүүдэд хувааж, зөвхөн хэрэглэгчийн сонгосон хэсгийг
embed хийнэ. `WholeImageLocalizer` хэсэг олохгүй (хуучин арга, харьцуулах baseline).
`YoloGarmentLocalizer` (`ml/yolo.py`) бол жинхэнэ detector.
"""

from dataclasses import dataclass
from typing import Protocol

from PIL import Image


@dataclass(frozen=True)
class Box:
    """Зургийн хэмжээнд харьцуулсан (0..1) тэгш өнцөгт: `x0 < x1`, `y0 < y1`."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)

    def to_pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        """`Image.crop`-д өгөх бүхэл координат; хамгийн багадаа 1 pixel хэмжээтэй."""
        left = min(max(int(self.x0 * width), 0), width - 1)
        top = min(max(int(self.y0 * height), 0), height - 1)
        right = min(max(round(self.x1 * width), left + 1), width)
        bottom = min(max(round(self.y1 * height), top + 1), height)
        return left, top, right, bottom


WHOLE_IMAGE = Box(0.0, 0.0, 1.0, 1.0)


@dataclass(frozen=True)
class Region:
    """Embed хийх зургийн нэг хэсэг. `label` нь detector-ийн анги (бүтэн зургийнх нь `None`)."""

    image: Image.Image
    box: Box
    label: str | None = None
    score: float = 1.0


class GarmentLocalizer(Protocol):
    async def alocate(self, image: Image.Image) -> list[Region]:
        """Хайх хэсгүүд, хамгийн тохирох нь эхэнд. Хэзээ ч хоосон биш."""
        ...


class WholeImageLocalizer:
    """Detection хийхгүй: бүтэн зургийг хувцас гэж үзнэ."""

    async def alocate(self, image: Image.Image) -> list[Region]:
        return [Region(image=image, box=WHOLE_IMAGE)]
