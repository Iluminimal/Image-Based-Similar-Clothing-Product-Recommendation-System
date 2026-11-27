"""Дэлгүүрийн өдөр. Цагийг UTC-ээр хадгалдаг. Харин "өнөөдөр", өдрийн тайлан зэрэгт өдөр хаанаас
эхлэхийг `SHOP_TIMEZONE` тогтооно. Ингэснээр Улаанбаатарт 00:00-08:00 цагийн борлуулалт өмнөх
өдөрт орохгүй."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo


def today(zone: ZoneInfo) -> date:
    return datetime.now(zone).date()


def start_of_day(day: date, zone: ZoneInfo) -> datetime:
    """Тухайн өдрийн эхлэх агшин (time zone-той)."""
    return datetime.combine(day, time.min, zone)
