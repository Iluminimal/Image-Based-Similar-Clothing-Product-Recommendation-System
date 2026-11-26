"""Хувцасны төрлийн монгол үгс: тайлбарлагч ба сайт дээр харагддаг нэрс."""

import re
from pathlib import Path

import pytest

from angel.repositories.catalog.products import SearchFilters
from angel.schemas.catalog.catalog import CatalogFilters, CategoryNode, PriceRange
from angel.services.catalog.garment_words import GARMENTS, MASTERS
from angel.services.catalog.query_parser import (
    ParsedQuery,
    Vocabulary,
    apply_parsed,
    interpret_listing_query,
    parse_search_text,
)
from angel.services.catalog.spelling import swapped_spellings
from angel.services.catalog.taxonomy import DISPLAY_NAMES

WEB_VOCABULARY = Path(__file__).parents[3] / "web" / "src" / "i18n" / "vocab-mn.ts"

SHOES = ("Casual Shoes", "Sports Shoes", "Formal Shoes", "Heels", "Flats")


def vocabulary(*article_types: str, masters: tuple[str, ...] = ("Apparel",)) -> Vocabulary:
    def node(name: str, level: int, children: list[CategoryNode] | None = None) -> CategoryNode:
        return CategoryNode(
            id=1, name=name, slug="x", path="x", level=level, children=children or []
        )

    leaves = [node(name, 3) for name in article_types]
    tree = [node(master, 1, [node("Sub", 2, leaves)]) for master in masters]
    return Vocabulary.from_catalog(
        CatalogFilters(
            categories=tree,
            genders=["Boys", "Girls", "Men", "Unisex", "Women"],
            colors=["Black", "Blue", "Red", "White"],
            seasons=["Summer", "Winter"],
            usages=["Casual", "Formal", "Sports"],
            price_range=PriceRange(min_cents=1, max_cents=40_000_000),
        )
    )


CATALOGUE = vocabulary(
    "Shirts", "Tshirts", "Tops", "Dresses", "Jeans", "Trousers", "Track Pants", "Shorts",
    "Jackets", "Handbags", "Backpacks", "Watches", "Socks", "Sports Sandals", "Sports Shoes",
    "Casual Shoes", "Formal Shoes", "Heels", "Flats",
    masters=("Apparel", "Accessories"),
)  # fmt: skip


def parse(text: str, words: Vocabulary = CATALOGUE) -> ParsedQuery:
    return parse_search_text(text, vocabulary=words)


@pytest.mark.parametrize(
    ("text", "types"),
    [
        ("даашинз", {"Dresses"}),
        ("цамц", {"Shirts", "Tshirts", "Tops"}),
        ("футболк", {"Tshirts"}),
        ("жинс", {"Jeans"}),
        ("жинсэн өмд", {"Jeans"}),  # урт хэллэг түрүүлнэ: дангаар "өмд" биш
        ("өмд", {"Trousers", "Jeans", "Track Pants"}),
        ("богино өмд", {"Shorts"}),
        ("спортын өмд", {"Track Pants"}),
        ("куртка", {"Jackets"}),
        ("гутал", set(SHOES) | {"Sports Sandals"}),
        ("гутлууд", set(SHOES) | {"Sports Sandals"}),
        ("пүүз", {"Sports Shoes", "Casual Shoes"}),
        ("гар цүнх", {"Handbags"}),
        ("цүнх", {"Handbags", "Backpacks"}),
        ("цүнхнүүд", {"Handbags", "Backpacks"}),
        ("цаг", {"Watches"}),
        ("оймс", {"Socks"}),
    ],
)
def test_mongolian_garment_words_become_catalogue_types(text: str, types: set[str]) -> None:
    parsed = parse(text)

    assert set(parsed.article_types) == types
    assert parsed.remaining == ""


def test_a_garment_the_shop_does_not_sell_is_left_as_text() -> None:
    parsed = parse("даашинз", vocabulary("Shirts"))

    assert parsed.article_types == ()
    assert parsed.remaining == "даашинз"


def test_white_is_not_a_watch() -> None:
    parsed = parse("цагаан цамц")

    assert parsed.colors == ("White",)
    assert "Watches" not in parsed.article_types


def test_a_general_word_narrows_by_master_category_unless_a_type_is_named() -> None:
    assert parse("эмэгтэй хувцас").master_categories == ("Apparel",)

    specific = parse("хувцас даашинз")
    assert (specific.master_categories, specific.article_types) == ((), ("Dresses",))


def test_two_garments_widen_the_search() -> None:
    assert set(parse("даашинз оймс").article_types) == {"Dresses", "Socks"}


def test_garments_are_reported_with_a_name_the_site_can_translate() -> None:
    parsed = parse("улаан даашинз")

    assert parsed.applied == (("color", "Red"), ("article_type", "Dresses"))
    assert parsed.embedding_text == "Red Dresses"


def test_a_category_the_shopper_already_chose_is_not_replaced() -> None:
    chosen = SearchFilters(article_types=("Jeans",))

    filters, applied = apply_parsed(parse("даашинз"), chosen)

    assert filters.article_types == ("Jeans",)
    assert applied == ()


# --- жагсаалтын хайлт -------------------------------------------------------------------------


def interpret(text: str, filters: SearchFilters | None = None):  # type: ignore[no-untyped-def]
    return interpret_listing_query(text, vocabulary=CATALOGUE, filters=filters or SearchFilters())


def test_english_searches_are_never_interpreted() -> None:
    assert interpret("red dress") is None


def test_unknown_mongolian_words_are_reported_and_latin_words_stay_searchable() -> None:
    result = interpret("nike улаан өнгийн цэцэгтэй даашинз")

    assert result is not None
    assert result.text == "nike"
    assert result.ignored == ("цэцэгтэй",)  # "өнгийн" нь утгагүй холбох үг: мэдээлэхгүй
    assert result.filters.base_colours == ("Red",)
    assert result.filters.article_types == ("Dresses",)


def test_a_search_with_no_known_word_is_not_interpreted() -> None:
    assert interpret("цэцэгтэй загвар") is None


# --- сайт дээр харагддаг нэр бүр хайлтаар танигдана -----------------------------------------


def site_labels() -> list[tuple[str, str]]:
    """Web-ийн монгол толь дахь article type-уудын (англи нэр, монгол нэр)."""
    section = WEB_VOCABULARY.read_text(encoding="utf-8").split("// article type", 1)[1]
    section = section.split("};", 1)[0]
    return [
        (quoted or bare, label)
        for quoted, bare, label in re.findall(
            r'^\s*(?:"([^"]+)"|([A-Za-z]+)):\s*"([^"]+)"', section, flags=re.MULTILINE
        )
    ]


@pytest.mark.skipif(not WEB_VOCABULARY.exists(), reason="the web app is not checked out here")
def test_every_type_name_the_site_shows_can_be_searched_for() -> None:
    labels = site_labels()
    assert len(labels) > 90
    raw = {shown: name for name, shown in DISPLAY_NAMES.items()}
    everything = vocabulary(*{raw.get(name, name) for name, _ in labels})

    unfound = [
        (name, label)
        for name, label in labels
        if raw.get(name, name) not in parse(label, everything).article_types
    ]

    assert unfound == []


def test_every_reported_garment_name_is_one_the_site_translates() -> None:
    source = WEB_VOCABULARY.read_text(encoding="utf-8").split("MN_CATEGORY", 1)[1]
    translated = {
        quoted or bare
        for quoted, bare in re.findall(
            r'^\s*(?:"([^"]+)"|([A-Za-z]+)):\s*"', source, flags=re.MULTILINE
        )
    }

    assert [g.label for g in (*GARMENTS, *MASTERS) if g.label not in translated] == []


# --- солигдсон хоёр үсэг ---------------------------------------------------------------------


def test_swapped_neighbouring_letters_are_offered_as_spellings() -> None:
    offered = swapped_spellings("Norkdap")

    assert offered is not None
    assert "Nordkap" in offered.split(" or ")


def test_the_other_words_are_kept_in_every_spelling() -> None:
    offered = swapped_spellings("red Norkdap")

    assert offered is not None
    assert "red Nordkap" in offered.split(" or ")
    assert all(len(option.split()) == 2 for option in offered.split(" or "))


@pytest.mark.parametrize(
    "text", ["", "abc", "даашинз", "'; DROP TABLE products; --", "a b c d e f g", "x" * 200]
)
def test_nothing_is_respelled_for_short_foreign_or_odd_input(text: str) -> None:
    assert swapped_spellings(text) is None
