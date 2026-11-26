"""Бичсэн үгийг хэрхэн ойлгосон (жагсаалтын ба зургийн хайлт хоёуланд)."""

from typing import Literal

from pydantic import BaseModel


class AppliedFilter(BaseModel):
    """Текстээс задалж хэрэгжүүлсэн шүүлтүүр. `value`: өнгө, хүйс, улирал, хэрэглээ, төрөлд англи
    нэр; `min_price`/`max_price`-д бага нэгжийн
    (төгрөг x 100) тоо; `in_stock`-д "true"."""

    key: Literal[
        "gender",
        "color",
        "season",
        "usage",
        "article_type",
        "master_category",
        "min_price",
        "max_price",
        "in_stock",
    ]
    value: str


class SearchInterpretation(BaseModel):
    """Монгол үгтэй хайлтыг шүүлтүүр болгон ойлгосон байдал."""

    applied: list[AppliedFilter]
    # Танигдаагүй тул тооцоогүй монгол үгс.
    ignored: list[str]
