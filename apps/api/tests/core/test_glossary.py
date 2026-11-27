"""Монгол нэр томьёоны толь (docs/glossary-mn.md): API-ийн хэрэглэгчид харагдах бичвэрт хуучирсан
хэлбэр байхгүй. Зөвхөн кодын string-үүдийг шалгана: comment, docstring-д энэ дүрэм хамаарахгүй."""

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "angel"

RETIRED = {
    "Хүслийн жагсаалт": "wishlist = «Хадгалсан бараа»",
    "[Хх]арагдацаар": "visual search = «Зургаар хайх»",
    "Мөнгө буцаасан": "refunded = «Төлбөр буцаагдсан»",
    "[Бб]уцаан ол": "refund = «төлбөр буцаах»",
    "Нөөц хүрэлцэхгүй": "тоо хэмжээ = «үлдэгдэл»",
    "захиалгад барь": "held for orders = «захиалагдсан»",
    "[Тт]авиур": "shelf count = «агуулахад байгаа тоо»",
    "[Хх]яналтын дугаар": "tracking number = «Илгээмжийн дугаар»",
    "Профайл": "profile page = «Миний мэдээлэл»",
    "Authenticator апп": "authenticator app = «баталгаажуулагч апп»",
    "секундийн": "зөв бичиг нь «секундын»",
    r"\{[\w.]*name\}[»”\"]?-[а-яөүё]": "нэрэнд нөхцөл залгахгүй: ямар ч нэрэнд таардаггүй",
}


def string_literals(path: Path) -> list[str]:
    """Файлын string-үүд, docstring-гүй. f-string-ийн орлуулах хэсэг `{нэр}` хэвээр үлдэнэ."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skipped: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr):
                skipped.add(id(first.value))
        elif isinstance(node, ast.JoinedStr):
            skipped.update(id(part) for part in node.values)

    found: list[str] = []
    for node in ast.walk(tree):
        if id(node) in skipped:
            continue
        if isinstance(node, ast.JoinedStr):
            found.append(
                "".join(
                    str(part.value)
                    if isinstance(part, ast.Constant)
                    else "{" + ast.unparse(part.value) + "}"  # type: ignore[attr-defined]
                    for part in node.values
                )
            )
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append(node.value)
    return found


TEXTS = {path: string_literals(path) for path in SRC.rglob("*.py")}


def test_the_scan_reads_the_messages_users_see() -> None:
    """Шалгалт юу ч уншаагүй мөртлөө "тэнцэх"-ээс сэргийлнэ."""
    everything = {text for texts in TEXTS.values() for text in texts}

    assert "Бараа олдсонгүй" in everything
    assert "{product_id} дугаартай бараа байхгүй байна." in everything


@pytest.mark.parametrize(("pattern", "why"), RETIRED.items())
def test_retired_terms_do_not_come_back(pattern: str, why: str) -> None:
    hits = [
        f"{path.relative_to(SRC)}: {text}"
        for path, texts in TEXTS.items()
        for text in texts
        if re.search(pattern, text)
    ]

    assert hits == [], why
