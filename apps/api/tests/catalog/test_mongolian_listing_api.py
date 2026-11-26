"""Толгой хэсгийн хайлт (`GET /products?q=`) монгол үгээр, мөн солигдсон үсгээр."""

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import Api
from tests.support.catalogue import Entry
from tests.support.commerce import set_product

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("require_infra")]

PRODUCTS = "/api/v1/products"


async def search(api: Api, q: str, **params: str | int) -> dict[str, Any]:
    response = await api.client.get(PRODUCTS, params={"q": q, "page_size": 60, **params})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def found(body: dict[str, Any]) -> set[int]:
    return {item["id"] for item in body["items"]}


def of(api: Api, article_type: str, genders: tuple[str, ...] | None = None) -> set[int]:
    def wanted(entry: Entry) -> bool:
        return entry.article_type == article_type and (genders is None or entry.gender in genders)

    return {entry.product_id for entry in api.entries if wanted(entry)}


async def test_a_mongolian_garment_word_finds_that_kind_of_product(api: Api) -> None:
    body = await search(api, "гутал")

    assert found(body) == of(api, "Casual Shoes")
    assert body["total"] == len(of(api, "Casual Shoes"))
    assert body["fuzzy"] is False
    assert body["interpretation"] == {
        "applied": [{"key": "article_type", "value": "Shoes"}],
        "ignored": [],
    }


async def test_gender_and_unknown_words_are_understood_and_reported(api: Api) -> None:
    body = await search(api, "эмэгтэй цэцэгтэй гутал")

    assert found(body) == of(api, "Casual Shoes", ("Women", "Unisex"))
    assert body["interpretation"]["ignored"] == ["цэцэгтэй"]


async def test_latin_words_beside_mongolian_ones_still_search_the_name(api: Api) -> None:
    assert found(await search(api, "brand жинс")) == of(api, "Jeans")
    assert found(await search(api, "zzzz жинс")) == set()


async def test_a_product_with_a_mongolian_name_is_still_found_and_comes_first(
    api: Api, db_engine: AsyncEngine
) -> None:
    own = sorted(of(api, "Jeans"))[0]
    await set_product(db_engine, own, name="Монгол ноолууран цамц")

    body = await search(api, "цамц")

    assert body["items"][0]["id"] == own
    assert found(body) == {own} | of(api, "Shirts") | of(api, "Tshirts")


async def test_the_category_the_shopper_chose_wins_over_the_words(api: Api) -> None:
    assert found(await search(api, "гутал")) == of(api, "Casual Shoes")

    body = await search(api, "хар гутал", article_type="Jeans")  # тестийн жинс бүгд хар

    assert found(body) == of(api, "Jeans")  # гутал биш: сонгосон ангилал хэвээр, хар нь хэрэгжинэ
    assert [a["key"] for a in body["interpretation"]["applied"]] == ["color"]


async def test_interpreted_results_can_be_sorted_and_paged(api: Api) -> None:
    first = await search(api, "гутал", sort="price_asc", page_size=3)
    second = await search(api, "гутал", sort="price_asc", page_size=3, page=2)

    prices = [item["price_cents"] for item in first["items"] + second["items"]]
    assert len(prices) == 6
    assert prices == sorted(prices)
    assert found(first).isdisjoint(found(second))


async def test_an_english_search_is_left_as_it_was(api: Api) -> None:
    body = await search(api, "Jeans")

    assert found(body) == of(api, "Jeans")
    assert body["interpretation"] is None


async def test_two_swapped_letters_still_find_the_product_and_say_so(
    api: Api, db_engine: AsyncEngine
) -> None:
    own = api.entries[0].product_id
    await set_product(db_engine, own, name="Nordkap parka")

    body = await search(api, "Norkdap")

    assert found(body) == {own}
    assert body["fuzzy"] is True


async def test_odd_input_with_mongolian_letters_is_still_answered(api: Api) -> None:
    for query in ["'; DROP TABLE products; -- гутал", "%гутал%", "ө" * 200, "гутал or -жинс"]:
        response = await api.client.get(PRODUCTS, params={"q": query})
        assert response.status_code == 200, query


async def test_the_swapped_spelling_beats_a_loose_resemblance(
    api: Api, db_engine: AsyncEngine
) -> None:
    meant, lookalike = (entry.product_id for entry in api.entries[:2])
    await set_product(db_engine, meant, name="Nordkap parka")
    await set_product(db_engine, lookalike, name="Norkdapia socks")  # trigram үүнийг "ойр" гэнэ

    assert found(await search(api, "Norkdap")) == {meant}
