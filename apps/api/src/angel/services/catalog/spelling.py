"""Хажуу хоёр үсэг солигдсон бичилт ("Norkdap" -> "Nordkap").

Trigram хайлт ийм алдааг заримдаа барьдаггүй: хоёр үсэг солигдоход гурван үсгийн хэсгүүдийн ихэнх нь
өөрчлөгддөг. Босгыг буулгавал хамааралгүй бараа орох тул оронд нь боломжит зөв бичилтүүдийг
яг таг хайна. Модуль pure."""

import re

_WORDS = re.compile(r"[A-Za-z0-9]+")
MAX_WORDS = 6
MIN_LENGTH = 4
MAX_LENGTH = 24


def swapped_spellings(text: str) -> str | None:
    """Нэг үгийн хажуу хоёр үсгийг сольсон бүх хувилбар, `websearch_to_tsquery`-ийн `or`-оор
    холбосон. Латин үг, тооноос өөр зүйл бичсэн, эсвэл солих үг байхгүй бол None."""
    words = text.split()
    if not words or len(words) > MAX_WORDS or not all(_WORDS.fullmatch(w) for w in words):
        return None
    options: dict[str, None] = {}  # дараалалтай, давхардалгүй
    for index, word in enumerate(words):
        if not (word.isalpha() and MIN_LENGTH <= len(word) <= MAX_LENGTH):
            continue
        for at in range(len(word) - 1):
            if word[at].lower() == word[at + 1].lower():
                continue
            # Том үсэг байрандаа үлдэнэ ("Norkdap" -> "Nordkap"); хайлт нь үсгийн томыг ялгахгүй.
            swapped = word[:at] + word[at + 1] + word[at] + word[at + 2 :]
            options[" ".join([*words[:index], swapped, *words[index + 1 :]])] = None
    return " or ".join(options) or None
