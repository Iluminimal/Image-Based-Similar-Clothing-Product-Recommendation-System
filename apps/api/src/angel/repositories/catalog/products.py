"""Барааны бүх SQL: жагсаалтын шүүлтүүр, бүтэн текстийн ба ойролцоо (trigram) хайлт,
pgvector-ийн төстэй хайлт, админы жагсаалт ба өөрчлөлт.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import (
    ColumnElement,
    Select,
    Subquery,
    UnaryExpression,
    and_,
    case,
    delete,
    func,
    literal,
    literal_column,
    or_,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer
from sqlalchemy.sql.base import ExecutableOption

from angel.models import Order, OrderItem, Product
from angel.repositories.patterns import contains_pattern

# Бүтэн catalogue дээр хэмжсэн (docs/ml-pipeline.md): 200 утга 80-тай ижил хугацаанд recall@10 = 1.0
# өгнө. ~300-аас их бол query planner exact sequential scan сонгож эхэлдэг (~13 ms-ийн оронд ~90
# ms). Тиймээс хүсэлтийн утгыг хязгаарлана.
DEFAULT_EF_SEARCH = 200
MAX_EF_SEARCH = 300
# Iterative scan хамгийн ихдээ хэдэн index tuple үзэх вэ (pgvector-ийн анхдагч 20000). Маш нарийн
# filter-тэй үед бүх index-ийг гүйлгэхээс сэргийлнэ.
MAX_SCAN_TUPLES = 20_000


@dataclass(frozen=True)
class SearchFilters:
    """Талбар бүр заавал биш; нэг талбарт хэд хэдэн утга өгвөл "аль нэг нь" гэсэн утгатай."""

    genders: tuple[str, ...] = ()
    master_categories: tuple[str, ...] = ()
    sub_categories: tuple[str, ...] = ()
    article_types: tuple[str, ...] = ()
    base_colours: tuple[str, ...] = ()
    seasons: tuple[str, ...] = ()
    usages: tuple[str, ...] = ()
    # Навигацийн нэг цэсэнд хамаарах хамгийн доод (leaf) ангиллууд; catalog service тогтооно.
    category_ids: tuple[int, ...] = ()
    min_price_cents: int | None = None
    max_price_cents: int | None = None
    in_stock_only: bool = False

    def clauses(self) -> list[ColumnElement[bool]]:
        clauses: list[ColumnElement[bool]] = [Product.is_active.is_(True)]
        for column, values in (
            (Product.gender, self.genders),
            (Product.master_category, self.master_categories),
            (Product.sub_category, self.sub_categories),
            (Product.article_type, self.article_types),
            (Product.base_colour, self.base_colours),
            (Product.season, self.seasons),
            (Product.usage, self.usages),
            (Product.category_id, self.category_ids),
        ):
            if values:
                clauses.append(column.in_(values))
        if self.min_price_cents is not None:
            clauses.append(Product.price_cents >= self.min_price_cents)
        if self.max_price_cents is not None:
            clauses.append(Product.price_cents <= self.max_price_cents)
        if self.in_stock_only:
            clauses.append(Product.stock_quantity > 0)
        return clauses


ProductSort = Literal["newest", "price_asc", "price_desc", "relevance", "rating", "popular"]

# Зарагдсан гэж тооцох захиалгын төлөв (орлогын тооцоотой ижил: буцаагдсан, цуцлагдсан биш).
SOLD_STATUSES = ("paid", "shipped", "delivered")
# Ойролцоо хайлтын босго: pg_trgm `word_similarity`. Хэт бага бол хамааралгүй бараа орно.
FUZZY_THRESHOLD = 0.4


def _tsquery(words: str) -> ColumnElement[Any]:
    # websearch_to_tsquery хэрэглэгчийн бичсэн текстийг шууд (хашилт, "or", "-үг" орсон ч) алдаагүй
    # уншина.
    return func.websearch_to_tsquery(literal_column("'english'::regconfig"), words)


def _name_matches(words: str) -> ColumnElement[bool]:
    return Product.search_vector.op("@@")(_tsquery(words))


def _sold_units() -> Subquery:
    """Бараа бүрийн зарагдсан нийт ширхэг (`popular` эрэмбэд)."""
    return (
        select(
            OrderItem.product_id.label("product_id"),
            func.sum(OrderItem.quantity).label("units"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.status.in_(SOLD_STATUSES))
        .group_by(OrderItem.product_id)
        .subquery()
    )


# Эдгээр мөр карт, JSON болж харагддаг тул 2 KB-ийн vector болон tsvector хэрэггүй. Тэднийг ачаалбал
# нэг үр дүнгийн уншигдах хэмжээ бараг хоёр дахин ихэснэ.
_LIGHT_ROWS: tuple[ExecutableOption, ...] = (
    defer(Product.embedding),
    defer(Product.search_vector),
)


# Хэт олон цифртэй тоо bigint id байж чадахгүй.
MAX_ID_DIGITS = 18
AdminStatus = Literal["all", "active", "inactive"]
AdminSort = Literal["newest", "price_asc", "price_desc", "stock_asc"]


@dataclass(frozen=True)
class SimilarProduct:
    product: Product
    similarity: float  # cosine similarity, 1.0 = ижил чиглэл


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, product_id: int) -> Product | None:
        result = await self._session.execute(
            select(Product)
            .where(Product.id == product_id, Product.is_active.is_(True))
            .options(*_LIGHT_ROWS)
        )
        return result.scalar_one_or_none()

    async def get_many(
        self, product_ids: Sequence[int], *, for_update: bool = False
    ) -> dict[int, Product]:
        """Барааг id-аар нь авна, идэвхгүй барааг ч оруулна (сагс зарахаа больсон барааг ч харуулах
        ёстой). `for_update` мөрүүдийг id-ийн дарааллаар түгжинэ. Олон бараа түгждэг transaction
        бүр ижил дарааллаар түгждэг тул хоёр checkout deadlock-д орохгүй."""
        if not product_ids:
            return {}
        statement = (
            select(Product)
            .where(Product.id.in_(set(product_ids)))
            .options(*_LIGHT_ROWS)
            .order_by(Product.id)
        )
        if for_update:
            # populate_existing: түгжсэний дараа уншсан утга session-д өмнө нь хадгалсан утгыг солих
            # ёстой. Эс бөгөөс нөөцийг хуучин тооноос тооцож эхэлнэ.
            statement = statement.with_for_update().execution_options(populate_existing=True)
        result = await self._session.execute(statement)
        return {product.id: product for product in result.scalars()}

    async def list_products(
        self,
        *,
        filters: SearchFilters,
        text_query: str | None,
        sort: ProductSort,
        offset: int,
        limit: int,
        understood: tuple[SearchFilters, str] | None = None,
    ) -> tuple[list[Product], int]:
        """Catalogue-ийн нэг хуудас болон таарсан нийт тоо.

        `understood` бол `text_query`-г шүүлтүүр болгон ойлгосон хувилбар: (шүүлтүүрүүд, нэрээс хайх
        үлдсэн үгс). Нэр нь `text_query`-тэй таарсан **эсвэл** `understood`-д таарсан бараа орно.
        Нэрээрээ таарсан нь эхэнд гарна, тиймээс өөрийн монгол нэртэй бараа алдагдахгүй.

        Эрэмбэ үргэлж `id`-аар төгсдөг: олон бараа ижил үнэ эсвэл rank-тай үед ч хуудсууд
        давхцахгүй, бараа алгасахгүй."""
        clauses = filters.clauses()
        rank = None
        if text_query:
            matches = _name_matches(text_query)
            rank = func.ts_rank(Product.search_vector, _tsquery(text_query))
            if understood is not None:
                meaning, rest = understood
                parts = [*meaning.clauses(), *([_name_matches(rest)] if rest else [])]
                matches = or_(matches, and_(*parts))
            clauses.append(matches)

        statement, order = self._sorted(
            select(Product).where(*clauses), sort, rank, newest_ties=understood is not None
        )
        total = (
            await self._session.execute(select(func.count()).select_from(Product).where(*clauses))
        ).scalar_one()
        rows = await self._session.execute(
            statement.order_by(*order).offset(offset).limit(limit).options(*_LIGHT_ROWS)
        )
        return list(rows.scalars()), total

    async def list_products_fuzzy(
        self,
        *,
        filters: SearchFilters,
        text_query: str,
        sort: ProductSort,
        offset: int,
        limit: int,
    ) -> tuple[list[Product], int]:
        """`list_products`-тай адил, гэхдээ `text_query`-г барааны нэрээс үсгийн алдааг тэвчиж хайна
        (trigram). Зөвхөн яг таарах хайлт хоосон үед дуудна. Ингэснээр зөв бичсэн хайлт
        удаашрахгүй, алдаатай бичсэн ч хоосон хуудас гарахгүй."""
        # `<%` оператор session-ийн босгыг ашигладаг. Бид зөвхөн энэ transaction-д тохируулна.
        await self._session.execute(
            text(f"SET LOCAL pg_trgm.word_similarity_threshold = {FUZZY_THRESHOLD}")
        )
        clauses = filters.clauses()
        clauses.append(literal(text_query).op("<%")(Product.name))
        rank = func.word_similarity(text_query, Product.name)
        statement, order = self._sorted(select(Product).where(*clauses), sort, rank)
        total = (
            await self._session.execute(select(func.count()).select_from(Product).where(*clauses))
        ).scalar_one()
        rows = await self._session.execute(
            statement.order_by(*order).offset(offset).limit(limit).options(*_LIGHT_ROWS)
        )
        return list(rows.scalars()), total

    @staticmethod
    def _sorted(
        statement: Select[Any], sort: ProductSort, rank: Any, *, newest_ties: bool = False
    ) -> tuple[Select[Any], list[UnaryExpression[Any]]]:
        """Эрэмбийн дараалал (болон `popular`-д шаардлагатай join). Үргэлж `id`-ээр төгсдөг."""
        if sort == "price_asc":
            return statement, [Product.price_cents.asc(), Product.id.asc()]
        if sort == "price_desc":
            return statement, [Product.price_cents.desc(), Product.id.asc()]
        if sort == "relevance" and rank is not None:
            if newest_ties:  # ойлгосон үгээр олдсон нь бүгд rank 0: шинэ нь түрүүлнэ
                return statement, [rank.desc(), Product.created_at.desc(), Product.id.desc()]
            return statement, [rank.desc(), Product.id.asc()]
        if sort == "rating":
            return statement, [
                Product.rating_average.desc(),
                Product.rating_count.desc(),
                Product.id.asc(),
            ]
        if sort == "popular":
            sold = _sold_units()
            joined = statement.outerjoin(sold, sold.c.product_id == Product.id)
            return joined, [
                func.coalesce(sold.c.units, 0).desc(),
                Product.created_at.desc(),
                Product.id.desc(),
            ]
        return statement, [Product.created_at.desc(), Product.id.desc()]

    async def complementary(
        self,
        *,
        sub_category: str,
        genders: Sequence[str],
        usage: str | None,
        limit: int,
    ) -> list[Product]:
        """Тухайн дэд ангиллын зарагдаж буй, нөөцтэй бараанууд. Ижил `usage`-тай нь эхэнд, дараа нь
        хамгийн их зарагдсан нь. "Хослуулах бараа" хэсэгт ашиглана."""
        sold = _sold_units()
        same_usage = case((Product.usage == usage, 1), else_=0) if usage else literal(0)
        rows = await self._session.execute(
            select(Product)
            .outerjoin(sold, sold.c.product_id == Product.id)
            .where(
                Product.is_active.is_(True),
                Product.stock_quantity > 0,
                Product.sub_category == sub_category,
                Product.gender.in_(genders),
            )
            .order_by(same_usage.desc(), func.coalesce(sold.c.units, 0).desc(), Product.id.asc())
            .limit(limit)
            .options(*_LIGHT_ROWS)
        )
        return list(rows.scalars())

    async def sitemap_entries(
        self, *, offset: int, limit: int
    ) -> tuple[list[tuple[int, str, datetime]], int]:
        """Идэвхтэй барааны (id, slug, updated_at) id-н дарааллаар, мөн нийт тоо."""
        total = (
            await self._session.execute(
                select(func.count()).select_from(Product).where(Product.is_active.is_(True))
            )
        ).scalar_one()
        rows = await self._session.execute(
            select(Product.id, Product.slug, Product.updated_at)
            .where(Product.is_active.is_(True))
            .order_by(Product.id)
            .offset(offset)
            .limit(limit)
        )
        return [(r.id, r.slug, r.updated_at) for r in rows.all()], int(total)

    # --- admin: доорх бүх зүйл идэвхгүй барааг ч харна ---

    async def get_any(self, product_id: int, *, for_update: bool = False) -> Product | None:
        statement = select(Product).where(Product.id == product_id).options(*_LIGHT_ROWS)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_all(
        self,
        *,
        text_query: str | None,
        status: AdminStatus,
        category_id: int | None,
        sort: AdminSort,
        offset: int,
        limit: int,
        stock: str = "all",
        low_stock_threshold: int = 5,
    ) -> tuple[list[Product], int]:
        """Back-office-ийн барааны жагсаалт. Ажилтан үгийн хагасыг бичдэг тул нэрийг энгийн
        substring-ээр (эсвэл яг id-аар) хайна. Дэлгүүрийн full-text хайлт хагас үгийг олохгүй."""
        clauses = self._admin_clauses(
            text_query=text_query,
            category_id=category_id,
            stock=stock,
            low_stock_threshold=low_stock_threshold,
        )
        if status != "all":
            clauses.append(Product.is_active.is_(status == "active"))
        orders: dict[AdminSort, list[UnaryExpression[Any]]] = {
            "newest": [Product.created_at.desc(), Product.id.desc()],
            "price_asc": [Product.price_cents.asc(), Product.id.asc()],
            "price_desc": [Product.price_cents.desc(), Product.id.asc()],
            "stock_asc": [Product.stock_quantity.asc(), Product.id.asc()],
        }
        order = orders[sort]
        total = (
            await self._session.execute(select(func.count()).select_from(Product).where(*clauses))
        ).scalar_one()
        rows = await self._session.execute(
            select(Product)
            .where(*clauses)
            .order_by(*order)
            .offset(offset)
            .limit(limit)
            .options(*_LIGHT_ROWS)
        )
        return list(rows.scalars()), total

    @staticmethod
    def _admin_clauses(
        *, text_query: str | None, category_id: int | None, stock: str, low_stock_threshold: int
    ) -> list[ColumnElement[bool]]:
        """Жагсаалтын төлвөөс бусад шүүлтүүрүүд."""
        clauses: list[ColumnElement[bool]] = []
        if text_query:
            by_name = Product.name.ilike(contains_pattern(text_query), escape="\\")
            is_id = text_query.isdigit() and len(text_query) <= MAX_ID_DIGITS
            clauses.append(or_(by_name, Product.id == int(text_query)) if is_id else by_name)
        if category_id is not None:
            clauses.append(Product.category_id == category_id)
        if stock == "out":
            clauses.append(Product.stock_quantity == 0)
        elif stock == "low":
            clauses.append(Product.stock_quantity.between(1, low_stock_threshold))
        return clauses

    async def status_counts(
        self,
        *,
        text_query: str | None,
        category_id: int | None,
        stock: str = "all",
        low_stock_threshold: int = 5,
    ) -> tuple[int, int]:
        """(зарагдаж байгаа, зарахаа больсон) барааны тоо: жагсаалтын tab бүрийн тоо. Хайлт, бусад
        шүүлтүүр үйлчилнэ, сонгосон төлөв үйлчлэхгүй."""
        clauses = self._admin_clauses(
            text_query=text_query,
            category_id=category_id,
            stock=stock,
            low_stock_threshold=low_stock_threshold,
        )
        rows = await self._session.execute(
            select(Product.is_active, func.count()).where(*clauses).group_by(Product.is_active)
        )
        counts: dict[bool, int] = {active: int(count) for active, count in rows.all()}
        return counts.get(True, 0), counts.get(False, 0)

    async def delete(self, product_id: int) -> None:
        """Мөрийг устгана. Сагс, хадгалсан жагсаалтын мөрийг өгөгдлийн сан өөрөө устгана
        (`CASCADE`); захиалгад орсон бол татгалзана (`RESTRICT`)."""
        await self._session.execute(delete(Product).where(Product.id == product_id))

    async def add(self, product: Product) -> Product:
        self._session.add(product)
        return await self.save(product)

    async def save(self, product: Product) -> Product:
        """flush хийгээд database-ийн бичсэн timestamp-уудыг дахин уншина. Бичсэний дараа тэдгээр
        хуучирдаг, async кодод өөрөө дахин ачаалагдахгүй."""
        await self._session.flush()
        await self._session.refresh(product, ["created_at", "updated_at"])
        return product

    async def get_embedding(self, product_id: int) -> NDArray[np.float32] | None:
        result = await self._session.execute(
            select(Product.embedding).where(Product.id == product_id, Product.is_active.is_(True))
        )
        value = result.scalar_one_or_none()
        return None if value is None else np.asarray(value, dtype=np.float32)

    async def search_similar(
        self,
        embedding: Sequence[float] | NDArray[np.float32],
        *,
        filters: SearchFilters | None = None,
        limit: int = 20,
        ef_search: int = DEFAULT_EF_SEARCH,
        exclude_id: int | None = None,
        iterative_scan: bool = True,
    ) -> list[SimilarProduct]:
        """HNSW index ашиглан cosine similarity-ээр хамгийн төстэй `limit` барааг авна.

        Filter-тэй HNSW хайлтад мэдэгдэж буй нэг асуудал бий: index эхлээд `ef_search` ширхэг
        candidate өгөөд, дараа нь WHERE нөхцөл ихэнхийг нь хасвал `limit`-ээс цөөн мөр үлдэж болно.
        pgvector 0.8-аас хойшх iterative scan хангалттай мөр гарах хүртэл index-ийг үргэлжлүүлэн
        уншдаг тул илүү олон мөр татах хэрэггүй. `relaxed_order` хурдан ч мөрүүдийн дараалал бага
        зэрэг алдагдаж болзошгүй тул энд дахин эрэмбэлнэ (limit жижиг)."""
        distance = Product.embedding.cosine_distance(embedding)
        statement = (
            select(Product, distance.label("distance"))
            .where(*(filters or SearchFilters()).clauses())
            .order_by(distance)
            .limit(limit)
            .options(*_LIGHT_ROWS)
        )
        if exclude_id is not None:
            statement = statement.where(Product.id != exclude_id)

        # set_config(..., is_local=true) нь bind parameter-тэй SET LOCAL: зөвхөн одоогийн
        # transaction-д үйлчилнэ, тиймээс pool-ийн connection-ийг ашиглах бусдад нөлөөлөхгүй. Нэг
        # statement = нэг round trip.
        await self._session.execute(
            text(
                "SELECT set_config('hnsw.ef_search', :ef_search, true), "
                "set_config('hnsw.iterative_scan', :iterative_scan, true), "
                "set_config('hnsw.max_scan_tuples', :max_scan_tuples, true)"
            ),
            {
                "ef_search": str(min(max(ef_search, 1), MAX_EF_SEARCH)),
                "iterative_scan": "relaxed_order" if iterative_scan else "off",
                "max_scan_tuples": str(MAX_SCAN_TUPLES),
            },
        )
        rows = (await self._session.execute(statement)).all()
        hits = [SimilarProduct(product, 1.0 - float(dist)) for product, dist in rows]
        hits.sort(key=lambda hit: -hit.similarity)
        return hits
