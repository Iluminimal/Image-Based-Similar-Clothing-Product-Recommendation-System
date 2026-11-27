"""Захиалгын имэйлийн текст: баталгаажуулалт (бараа, хаяг, дүн) болон хугацаа дууссан мэдэгдэл."""

from angel.core.mail import Email
from angel.core.money import format_minor
from angel.models import Order

_METHODS = {
    "standard": "Энгийн хүргэлт",
    "express": "Шуурхай хүргэлт",
    "pickup": "Дэлгүүрээс авах",
}


def address_line(snapshot: dict[str, object]) -> str:
    """Монгол дарааллаар: аймаг/хот, дүүрэг/сум, хороо, гудамж, нэмэлт."""
    parts = (
        snapshot.get("region"),
        snapshot.get("city"),
        snapshot.get("khoroo"),
        snapshot.get("line1"),
        snapshot.get("line2"),
    )
    return ", ".join(str(part) for part in parts if part)


def confirmation_body(order: Order, charged: str) -> str:
    """ "Баярлалаа" имэйлийн бичвэр: юу авсан, хаашаа хүргэх, хэдэн төгрөг."""
    lines = [
        f"Баярлалаа! Таны {order.number} дугаартай захиалгын {charged} төлбөрийг хүлээн авлаа.",
        "",
        "Бараа:",
    ]
    for item in order.items:
        size = f" ({item.size})" if item.size else ""
        total = format_minor(item.unit_price_cents * item.quantity, order.currency)
        lines.append(f"  • {item.product_name}{size} × {item.quantity}: {total}")
    lines += [
        "",
        f"Хүргэлт: {_METHODS.get(order.shipping_method, order.shipping_method)}"
        f" ({format_minor(order.shipping_cents, order.currency)})",
        f"Хаяг: {address_line(order.shipping_address)}",
    ]
    phone = order.shipping_address.get("phone")
    if phone:
        lines.append(f"Утас: {phone}")
    lines += ["", f"Нийт: {format_minor(order.total_cents, order.currency)}"]
    return "\n".join(lines)


def expired_body(order: Order) -> str:
    return (
        f"{order.number} дугаартай захиалгын төлбөр хугацаандаа төлөгдөөгүй тул цуцлагдлаа. "
        "Танаас мөнгө аваагүй. Сагс тань хэвээр байгаа тул хүсвэл дахин захиалж болно."
    )


def ready_for_pickup_body(order: Order, pickup_address: str) -> str:
    return "\n".join(
        [
            f"{order.number} дугаартай захиалга тань авахад бэлэн боллоо.",
            "",
            f"Авах хаяг: {pickup_address}",
            f"Ирэхдээ захиалгын дугаараа хэлнэ үү: {order.number}",
        ]
    )


_REQUEST_NAMES = {"cancel": "цуцлах", "return": "буцаах"}


def request_received(order: Order, kind: str) -> Email:
    return Email(
        to=order.contact_email,
        subject=f"{order.number}: {_REQUEST_NAMES[kind]} хүсэлтийг хүлээн авлаа",
        body=f"{order.number} дугаартай захиалгыг {_REQUEST_NAMES[kind]} тухай таны хүсэлтийг "
        "хүлээн авлаа. Шийдвэрийг имэйлээр мэдэгдэнэ. Захиалгын хуудаснаас ч харж болно.",
    )


def return_approved(order: Order, address: str, note: str | None) -> Email:
    lines = [
        f"{order.number} дугаартай захиалгыг буцаах хүсэлтийг зөвшөөрлөө.",
        "",
        "Барааг дараах хаягаар авчирна уу, эсвэл илгээнэ үү:",
        address,
        f"Захиалгын дугаараа хавсаргана уу: {order.number}",
        "",
        "Бараа ирснийг шалгасны дараа төлбөрийг буцаана.",
    ]
    if note:
        lines += ["", note]
    return Email(
        to=order.contact_email,
        subject=f"{order.number}: буцаах хүсэлт зөвшөөрөгдлөө",
        body="\n".join(lines),
    )


def request_declined(order: Order, kind: str, note: str) -> Email:
    return Email(
        to=order.contact_email,
        subject=f"{order.number}: {_REQUEST_NAMES[kind]} хүсэлтийг зөвшөөрөх боломжгүй",
        body=f"{order.number} дугаартай захиалгыг {_REQUEST_NAMES[kind]} хүсэлтийг зөвшөөрөх "
        f"боломжгүй байна.\n\nТайлбар: {note}",
    )


def return_received(order: Order) -> Email:
    return Email(
        to=order.contact_email,
        subject=f"{order.number}: буцаасан бараа ирлээ",
        body=f"{order.number} дугаартай захиалгын буцаасан барааг хүлээн авлаа. "
        "Төлбөрийг буцаамагц дахин мэдэгдэнэ.",
    )


def refund_sent(order: Order, note: str | None = None) -> Email:
    """`note`: цуцлах хүсэлтийг зөвшөөрөхдөө ажилтны хэрэглэгчид бичсэн тайлбар."""
    body = (
        f"{order.number} дугаартай захиалгын төлбөрийг буцаалаа.\n"
        f"Буцаасан дүн: {format_minor(order.total_cents, order.currency)}\n"
        "Мөнгө таны дансанд орж харагдахад хэдэн хоног болж магадгүй."
    )
    return Email(
        to=order.contact_email,
        subject=f"{order.number} дугаартай захиалгын төлбөр буцаагдлаа",
        body=f"{body}\n\n{note}" if note else body,
    )
