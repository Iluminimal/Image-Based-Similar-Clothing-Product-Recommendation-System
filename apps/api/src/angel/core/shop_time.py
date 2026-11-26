"""Дэлгүүрийн өдөр. Өгөгдөл UTC-ээр хадгалагддаг; "өнөөдөр", өдрийн тайлан зэрэг өдрийн хилийг
`SHOP_TIMEZONE`-оор тогтооно (Улаанбаатарт 00:00-08:00-ны борлуулалт өмнөх өдөрт орохгүй)."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo


def today(zone: ZoneInfo) -> date:
    return datetime.now(zone).date()


def start_of_day(day: date, zone: ZoneInfo) -> datetime:
    """Тухайн өдрийн эхлэх агшин (time zone-той)."""
    return datetime.combine(day, time.min, zone)
