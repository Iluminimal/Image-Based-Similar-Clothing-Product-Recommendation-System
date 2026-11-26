"""CSV гаргалт: Excel-д зөв нээгдэх (UTF-8 BOM) ба томьёоны инжекцээс хамгаалсан (`=`, `+`, `-`,
`@`-ээр эхэлсэн текстийг `'` угтварлана). Мөнгийг дэлгүүрт харагддаг нэгжээр, цагийг дэлгүүрийн
цагаар бичнэ."""

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Response

_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def money_cell(cents: int) -> int | str:
    """Хадгалсан бага нэгжийг (x100) үндсэн нэгж болгоно: бүхэл бол тоо, үлдэгдэлтэй бол 2 орон."""
    whole, rest = divmod(cents, 100)
    return whole if rest == 0 else f"{Decimal(cents) / 100:.2f}"


def local_time_cell(moment: datetime, zone: ZoneInfo) -> str:
    """Excel огноо гэж таних хэлбэр, дэлгүүрийн цагаар."""
    return moment.astimezone(zone).strftime("%Y-%m-%d %H:%M:%S")


def safe_cell(value: Any) -> Any:
    """Хэрэглэгчийн оруулсан текстийг (нэр, имэйл) Excel томьёо гэж тайлбарлуулахгүй."""
    if isinstance(value, str) and value.startswith(_FORMULA_STARTS):
        return "'" + value
    return value


def csv_response(filename: str, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow([safe_cell(cell) for cell in row])
    return Response(
        content="﻿" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
