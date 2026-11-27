"""CSV тайлан бичнэ. Excel-д зөв нээгдэхийн тулд UTF-8 BOM нэмнэ. `=`, `+`, `-`, `@`-ээр эхэлсэн
текстийн өмнө `'` тавьж, томьёо шургуулах халдлагаас (formula injection) хамгаална. Мөнгөн дүнг
дэлгүүрт харагддаг нэгжээр, цагийг дэлгүүрийн цагаар бичнэ."""

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
    """Бага нэгжийн (x100) дүнг төгрөг болгоно: бүхэл бол бутархайгүй, үгүй бол 2 оронтой."""
    whole, rest = divmod(cents, 100)
    return whole if rest == 0 else f"{Decimal(cents) / 100:.2f}"


def local_time_cell(moment: datetime, zone: ZoneInfo) -> str:
    """Excel огноо гэж таних хэлбэр, дэлгүүрийн цагаар."""
    return moment.astimezone(zone).strftime("%Y-%m-%d %H:%M:%S")


def safe_cell(value: Any) -> Any:
    """Хэрэглэгчийн оруулсан текстийг (нэр, имэйл) Excel томьёо гэж уншихаас сэргийлнэ."""
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
