"""Дэлгүүрийн каталог: барааны жагсаалт (шүүлтүүр, эрэмбэ, үгээр хайх), барааны хуудас,
хослуулах бараа, ангиллын мод, sitemap.
"""

import math
from dataclasses import replace
from http import HTTPStatus

from sqlalchemy.ext.asyncio import AsyncSession

from angel.core.errors import CATEGORY_NOT_FOUND_TYPE, PRODUCT_NOT_FOUND_TYPE, ProblemError
from angel.models import Category, Product
from angel.repositories.catalog.categories import CategoryRepository
from angel.repositories.catalog.products import ProductRepository, ProductSort, SearchFilters
from angel.schemas.catalog.catalog import (
    CatalogFilters,
    CatalogNav,
    CategoryNode,
    PriceRange,
    SitemapEntry,
    SitemapPage,
    SitemapQuery,
)
from angel.schemas.catalog.interpretation import AppliedFilter, SearchInterpretation
from angel.schemas.catalog.product import ProductListQuery, ProductOut, ProductPage
from angel.services.cache import SearchCache
from angel.services.catalog.query_parser import (
    ListingInterpretation,
    Vocabulary,
    interpret_listing_query,
)
from angel.services.catalog.spelling import swapped_spellings
from angel.services.catalog.taxonomy import (
    DEPARTMENT_BY_SLUG,
    TaxonomySnapshot,
    build_snapshot,
)
from angel.services.mappers import to_product_out, to_search_filters
from angel.storage import Storage


def _to_interpretation(meaning: ListingInterpretation | None) -> SearchInterpretation | None:
    if meaning is None:
        return None
    return SearchInterpretation(
        applied=[AppliedFilter.model_validate({"key": k, "value": v}) for k, v in meaning.applied],
        ignored=list(meaning.ignored),
    )


def build_category_tree(categories: list[Category]) -> list[CategoryNode]:
    nodes = {
        c.id: CategoryNode(id=c.id, name=c.name, slug=c.slug, path=c.path, level=c.level)
        for c in categories
    }
    roots: list[CategoryNode] = []
    for category in categories:
        parent = nodes.get(category.parent_id) if category.parent_id is not None else None
        (parent.children if parent else roots).append(nodes[category.id])
    return roots


# "Хослуулах бараа": аль дэд ангиллын барааг юутай хамт өмсдөг вэ. Жагсаалтад байхгүй дэд ангилалд
# (дотуур хувцас, оймс, үнэртэн...) хослол санал болгохгүй. Хамгийн тохирохоос нь эхэлж жагсаасан.
COMPLEMENTS: dict[str, tuple[str, ...]] = {
    "Topwear": ("Bottomwear", "Shoes", "Bags", "Watches", "Belts"),
    "Bottomwear": ("Topwear", "Shoes", "Belts", "Bags", "Watches"),
    "Dress": ("Shoes", "Bags", "Jewellery", "Watches"),
    "Saree": ("Jewellery", "Bags", "Sandal", "Watches"),
    "Apparel Set": ("Shoes", "Bags", "Watches"),
    "Shoes": ("Topwear", "Bottomwear", "Bags", "Watches"),
    "Sandal": ("Topwear", "Bottomwear", "Bags"),
    "Flip Flops": ("Topwear", "Bottomwear", "Bags"),
    "Bags": ("Topwear", "Bottomwear", "Shoes", "Watches"),
    "Watches": ("Topwear", "Bottomwear", "Shoes"),
    "Belts": ("Topwear", "Bottomwear", "Shoes"),
    "Jewellery": ("Dress", "Topwear", "Bags"),
    "Eyewear": ("Topwear", "Bottomwear", "Shoes"),
    "Wallets": ("Topwear", "Bottomwear", "Shoes"),
}
# Нэг дэд ангиллаас хамгийн ихдээ ийм тооны бараа (хослол олон төрлөөс бүрдэнэ).
PER_COMPLEMENT = 2


def outfit_genders(gender: str) -> tuple[str, ...]:
    """Хослолд тохирох хүйс: Unisex бараанд бүх хүйс, бусад бараанд өөрийн хүйс болон Unisex."""
    return ("Men", "Women", "Boys", "Girls", "Unisex") if gender == "Unisex" else (gender, "Unisex")


def interleave(groups: list[list[Product]], limit: int) -> list[Product]:
    """Бүлэг бүрээс ээлжлэн нэг нэгийг авч, `limit` хүртэл цуглуулна. Ингэснээр нэг ангилал бүх
    хослолыг эзлэхгүй."""
    out: list[Product] = []
    for rank in range(max((len(g) for g in groups), default=0)):
        for group in groups:
            if rank < len(group) and len(out) < limit:
                out.append(group[rank])
    return out


class CatalogService:
    def __init__(self, session: AsyncSession, storage: Storage, cache: SearchCache) -> None:
        self._session = session
        self._storage = storage
        self._cache = cache

    async def list_products(self, query: ProductListQuery) -> ProductPage:
        sort: ProductSort = query.sort or ("relevance" if query.q else "newest")
        if sort == "relevance" and not query.q:
            raise ProblemError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "Эрэмбэлэлт буруу",
                "«Хамгийн тохирох» эрэмбэлэлт нь хайх үг бичсэн үед л ажиллана.",
            )
        filters = await self._navigation_filters(query)
        if filters is None:
            return ProductPage(
                items=[], total=0, page=query.page, page_size=query.page_size, pages=0
            )
        offset = (query.page - 1) * query.page_size
        fuzzy = False
        meaning = await self._interpret(query.q, filters)
        async with self._session.begin():
            repository = ProductRepository(self._session)
            products, total = await repository.list_products(
                filters=filters,
                text_query=query.q,
                sort=sort,
                offset=offset,
                limit=query.page_size,
                understood=(meaning.filters, meaning.text) if meaning else None,
            )
            if total == 0 and query.q:
                # Яг таарах бараа алга, үсгийн алдаатай бичсэн байж магадгүй. Эхлээд хоёр үсэг
                # байраа сольсон гэж үзэж шалгана (яг таг тулгадаг тул нарийн), дараа нь ойролцоо
                # хайлт (trigram) хийнэ.
                if respelled := swapped_spellings(query.q):
                    products, total = await repository.list_products(
                        filters=filters,
                        text_query=respelled,
                        sort=sort,
                        offset=offset,
                        limit=query.page_size,
                    )
                if total == 0:
                    products, total = await repository.list_products_fuzzy(
                        filters=filters,
                        text_query=query.q,
                        sort=sort,
                        offset=offset,
                        limit=query.page_size,
                    )
                fuzzy = total > 0
        return ProductPage(
            items=[to_product_out(p, self._storage) for p in products],
            total=total,
            page=query.page,
            page_size=query.page_size,
            pages=math.ceil(total / query.page_size),
            fuzzy=fuzzy,
            interpretation=_to_interpretation(meaning),
        )

    async def _interpret(
        self, text: str | None, filters: SearchFilters
    ) -> ListingInterpretation | None:
        """Монгол үгтэй хайлтыг шүүлтүүр болгоно. `filters()` өөрийн transaction нээдэг тул
        жагсаалтын transaction эхлэхээс өмнө дуудна."""
        if not text:
            return None
        vocabulary = Vocabulary.from_catalog(await self.filters())
        return interpret_listing_query(text, vocabulary=vocabulary, filters=filters)

    async def _navigation_filters(self, query: ProductListQuery) -> SearchFilters | None:
        """`department`, `category`-г тооцсон query-ийн filter-үүд. Ямар ч бараа таарах боломжгүй
        бол None (жишээ нь department-д хамаарахгүй gender зэрэг заасан)."""
        filters = to_search_filters(query)
        if query.department is not None:
            department = DEPARTMENT_BY_SLUG.get(query.department)
            if department is None:
                raise _category_not_found(f"{query.department!r} гэсэн хэлтэс байхгүй байна.")
            genders = (
                tuple(g for g in filters.genders if g in department.genders)
                if filters.genders
                else department.genders
            )
            if not genders:
                return None
            filters = replace(filters, genders=genders)
        if query.category is not None:
            snapshot = await self.taxonomy()
            ids = snapshot.category_ids.get(query.category.strip("/"))
            if ids is None:
                raise _category_not_found(f"{query.category!r} гэсэн ангилал байхгүй байна.")
            filters = replace(filters, category_ids=tuple(ids))
        return filters

    async def get_product(self, product_id: int) -> ProductOut:
        async with self._session.begin():
            product = await ProductRepository(self._session).get_by_id(product_id)
        if product is None:
            raise ProblemError(
                HTTPStatus.NOT_FOUND,
                "Бараа олдсонгүй",
                f"{product_id} дугаартай бараа байхгүй байна.",
                type_=PRODUCT_NOT_FOUND_TYPE,
            )
        return to_product_out(product, self._storage)

    async def complete_the_look(self, product_id: int, limit: int) -> list[ProductOut]:
        """Энэ бараатай хамт өмсөх бараанууд: нэмэлт дэд ангилал бүрээс хамгийн их зарагдсан
        бараануудыг ээлжлэн авна. Нөөцгүй, идэвхгүй бараа болон энэ барааг өөрийг нь оруулахгүй."""
        async with self._session.begin():
            repository = ProductRepository(self._session)
            product = await repository.get_by_id(product_id)
            if product is None:
                raise ProblemError(
                    HTTPStatus.NOT_FOUND,
                    "Бараа олдсонгүй",
                    f"{product_id} дугаартай бараа байхгүй байна.",
                    type_=PRODUCT_NOT_FOUND_TYPE,
                )
            groups: list[list[Product]] = []
            for sub_category in COMPLEMENTS.get(product.sub_category, ()):
                groups.append(
                    await repository.complementary(
                        sub_category=sub_category,
                        genders=outfit_genders(product.gender),
                        usage=product.usage,
                        limit=PER_COMPLEMENT,
                    )
                )
        return [to_product_out(p, self._storage) for p in interleave(groups, limit)]

    async def sitemap(self, query: SitemapQuery) -> SitemapPage:
        async with self._session.begin():
            rows, total = await ProductRepository(self._session).sitemap_entries(
                offset=(query.page - 1) * query.page_size, limit=query.page_size
            )
        return SitemapPage(
            items=[SitemapEntry(id=i, slug=slug, updated_at=at) for i, slug, at in rows],
            total=total,
            page=query.page,
            page_size=query.page_size,
            pages=math.ceil(total / query.page_size),
        )

    async def filters(self) -> CatalogFilters:
        """Зөвхөн бараа нэмэгдэх, өнгө нь солигдоход л өөрчлөгддөг. Тиймээс хэдэн минутын cache
        хэрэглэгчид анзаарагдахгүй, харин хуудас бүрт хэд хэдэн DISTINCT scan хэмнэнэ."""
        cached = await self._cache.get_catalog_filters()
        if cached is not None:
            return cached
        async with self._session.begin():
            repository = CategoryRepository(self._session)
            categories = await repository.all_categories()
            options = await repository.filter_options()
        result = CatalogFilters(
            categories=build_category_tree(categories),
            genders=options.genders,
            colors=options.colours,
            seasons=options.seasons,
            usages=options.usages,
            price_range=PriceRange(
                min_cents=options.min_price_cents, max_cents=options.max_price_cents
            ),
        )
        await self._cache.set_catalog_filters(result)
        return result

    async def taxonomy(self) -> TaxonomySnapshot:
        """Department-ууд ба тэдгээрийн барааны тоо, мөн цэс бүрд хамаарах ангиллын id-ууд. Тоо
        зөвхөн catalogue өөрчлөгдөхөд өөрчлөгддөг тул filter-ийн сонголтуудтай хамт cache хийнэ."""
        cached = await self._cache.get_taxonomy()
        if cached is not None:
            return cached
        async with self._session.begin():
            repository = CategoryRepository(self._session)
            categories = await repository.all_categories()
            counts = await repository.gender_category_counts()
        snapshot = build_snapshot(categories, counts)
        await self._cache.set_taxonomy(snapshot)
        return snapshot

    async def nav(self) -> CatalogNav:
        return (await self.taxonomy()).nav


def _category_not_found(detail: str) -> ProblemError:
    return ProblemError(
        HTTPStatus.NOT_FOUND, "Ангилал олдсонгүй", detail, type_=CATEGORY_NOT_FOUND_TYPE
    )
