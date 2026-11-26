"""Барааны удирдлага: зургаас нэмэх, засах, зураг солих, зарах эсэхийг солих, тоолох, устгах.
Өөрчлөх эрх агуулахын ажилтанд л бий (route дээр шалгана).

Өөрчлөлт бүр үйлдлийн журналд бичигдэж, хайлтын cache хүчингүй болно.
"""

import asyncio
import math
import secrets
import uuid
from dataclasses import dataclass
from http import HTTPStatus

import numpy as np
from numpy.typing import NDArray
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from angel.core.errors import (
    INVALID_CATEGORY_TYPE,
    PRODUCT_HAS_ORDERS_TYPE,
    PRODUCT_NOT_FOUND_TYPE,
    STOCK_BELOW_COMMITTED_TYPE,
    ProblemError,
)
from angel.core.logging import get_logger
from angel.core.slug import slugify
from angel.core.uploads import ALLOWED_FORMATS, invalid_image
from angel.ingestion.images import (
    THUMBNAIL_SIZES,
    Thumbnails,
    build_thumbnails,
    thumbnail_key,
)
from angel.ml.embeddings import EmbeddingService
from angel.ml.preprocess import InvalidImageError, load_image
from angel.models import Product, User
from angel.repositories.admin.audit import AuditRepository
from angel.repositories.catalog.categories import CategoryRepository, LeafCategory
from angel.repositories.catalog.products import ProductRepository
from angel.repositories.commerce.orders import OrderRepository
from angel.schemas.admin.products import (
    AdminCategory,
    AdminProductListQuery,
    AdminProductOut,
    AdminProductPage,
    AdminProductUpdate,
    ProductFields,
    ProductStatusCounts,
)
from angel.services.cache import SearchCache
from angel.services.mappers import to_admin_product_out
from angel.storage import Storage

log = get_logger(__name__)

# Эндээс үүсгэсэн барааны зураг нь dataset-ийн `products/NNN/<id>` key-үүдээс тусдаа байрлана.
ADMIN_IMAGE_PREFIX = "products/admin/"
# Хайлтын pipeline болон ingestion-тэй ижил decode хэмжээ: хадгалсан vector харьцуулах боломжтой
# байхын тулд.
DECODE_MIN_SIDE = 800


@dataclass(frozen=True)
class PreparedImage:
    thumbnails: Thumbnails
    embedding: NDArray[np.float32]


def _not_found(product_id: int) -> ProblemError:
    return ProblemError(
        HTTPStatus.NOT_FOUND,
        "Бараа олдсонгүй",
        f"{product_id} дугаартай бараа байхгүй байна.",
        type_=PRODUCT_NOT_FOUND_TYPE,
    )


def _has_orders() -> ProblemError:
    return ProblemError(
        HTTPStatus.CONFLICT,
        "Захиалгад орсон барааг устгах боломжгүй",
        "Өмнөх захиалгууд энэ барааг хадгалдаг тул устгаж болохгүй. Харин зарахаа больж болно: "
        "дэлгүүрт харагдахаа болино.",
        type_=PRODUCT_HAS_ORDERS_TYPE,
    )


class AdminProductService:
    def __init__(
        self,
        session: AsyncSession,
        storage: Storage,
        embedder: EmbeddingService,
        cache: SearchCache,
        *,
        currency: str,
        max_upload_pixels: int,
        low_stock_threshold: int = 5,
    ) -> None:
        self._session = session
        self._storage = storage
        self._embedder = embedder
        self._cache = cache
        self._currency = currency
        self._max_pixels = max_upload_pixels
        self._low_stock = low_stock_threshold
        self._products = ProductRepository(session)
        self._categories = CategoryRepository(session)
        self._orders = OrderRepository(session)
        self._audit = AuditRepository(session)

    # --- унших ---

    async def categories(self) -> list[AdminCategory]:
        async with self._session.begin():
            leaves = await self._categories.leaf_categories()
        return [
            AdminCategory(
                id=c.id,
                path=c.path,
                master_category=c.master_category,
                sub_category=c.sub_category,
                article_type=c.article_type,
            )
            for c in leaves
        ]

    async def list_products(self, query: AdminProductListQuery) -> AdminProductPage:
        async with self._session.begin():
            products, total = await self._products.list_all(
                text_query=query.q,
                status=query.status,
                category_id=query.category_id,
                sort=query.sort,
                offset=(query.page - 1) * query.page_size,
                limit=query.page_size,
                stock=query.stock,
                low_stock_threshold=self._low_stock,
            )
            ids = [p.id for p in products]
            held = await self._orders.committed_units(ids)
            ordered = await self._orders.ordered_product_ids(ids)
            active, inactive = await self._products.status_counts(
                text_query=query.q,
                category_id=query.category_id,
                stock=query.stock,
                low_stock_threshold=self._low_stock,
            )
        return AdminProductPage(
            items=[
                to_admin_product_out(
                    p, self._storage, committed=held.get(p.id, 0), ordered=p.id in ordered
                )
                for p in products
            ],
            status_counts=ProductStatusCounts(
                all=active + inactive, active=active, inactive=inactive
            ),
            total=total,
            page=query.page,
            page_size=query.page_size,
            pages=math.ceil(total / query.page_size),
        )

    async def get(self, product_id: int) -> AdminProductOut:
        async with self._session.begin():
            product = await self._products.get_any(product_id)
            if product is None:
                raise _not_found(product_id)
            committed, ordered = await self._holds(product_id)
        return to_admin_product_out(product, self._storage, committed=committed, ordered=ordered)

    # --- бичих ---

    async def create(
        self, data: bytes, fields: ProductFields, *, is_active: bool, actor: User
    ) -> AdminProductOut:
        """Зургаас шинэ бараа: thumbnail, blur placeholder, FashionCLIP embedding-ийг upload-аас
        тооцоолно, тиймээс visual search-ээр тэр даруй олдоно."""
        async with self._session.begin():
            category = await self._leaf(fields.category_id)
        prepared = await self._prepare(data)
        key = await self._store(prepared)
        try:
            async with self._session.begin():
                product = await self._products.add(
                    Product(
                        slug=f"{slugify(fields.name) or 'product'}-{secrets.token_hex(4)}",
                        name=fields.name,
                        category_id=category.id,
                        gender=fields.gender,
                        master_category=category.master_category,
                        sub_category=category.sub_category,
                        article_type=category.article_type,
                        base_colour=fields.base_colour,
                        season=fields.season,
                        usage=fields.usage,
                        year=fields.year,
                        price_cents=fields.price_cents,
                        currency=self._currency,
                        stock_quantity=fields.stock_quantity,
                        is_active=is_active,
                        image_key=key,
                        blur_data_url=prepared.thumbnails.blur_data_url,
                        embedding=prepared.embedding.tolist(),
                        embedding_version=self._embedder.version,
                    )
                )
                self._audit.record(
                    actor,
                    "product.create",
                    "product",
                    product.id,
                    {"name": fields.name, "stock": fields.stock_quantity, "active": is_active},
                )
        except Exception:
            await self._discard(key)
            raise
        await self._cache.invalidate_catalogue()
        log.info("product_created", product_id=product.id, actor_id=actor.id)
        return to_admin_product_out(product, self._storage)

    async def update(
        self, product_id: int, changes: AdminProductUpdate, *, actor: User
    ) -> AdminProductOut:
        values = changes.model_dump(exclude_unset=True)
        if "category_id" in values and values["category_id"] is None:
            raise ProblemError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "Ангилал буруу",
                "Барааг ангилалд хамруулах ёстой.",
                type_=INVALID_CATEGORY_TYPE,
            )
        for required in ("name", "gender", "price_cents", "on_hand"):
            if required in values and values[required] is None:
                raise ProblemError(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    "Утга буруу",
                    f"{required} талбарыг хоосон болгох боломжгүй.",
                )
        async with self._session.begin():
            product = await self._products.get_any(product_id, for_update=True)
            if product is None:
                raise _not_found(product_id)
            committed, ordered = await self._holds(product_id)
            changed = sorted(values)
            if "on_hand" in values:
                self._count_shelf(product, values.pop("on_hand"), committed, actor)
            if "category_id" in values:
                category = await self._leaf(values.pop("category_id"))
                product.category_id = category.id
                product.master_category = category.master_category
                product.sub_category = category.sub_category
                product.article_type = category.article_type
            for name, value in values.items():
                setattr(product, name, value)
            await self._products.save(product)
            self._audit.record(actor, "product.update", "product", product_id, {"fields": changed})
        await self._cache.invalidate_catalogue()
        log.info("product_updated", product_id=product_id, fields=changed, actor_id=actor.id)
        return to_admin_product_out(product, self._storage, committed=committed, ordered=ordered)

    async def replace_image(self, product_id: int, data: bytes, *, actor: User) -> AdminProductOut:
        """Шинэ зураг, шинэ embedding. Файлууд шинэ key авна, ингэвэл browser болон cache хуучин
        зургийг үргэлжлүүлэн үзүүлэхгүй."""
        async with self._session.begin():
            if await self._products.get_any(product_id) is None:
                raise _not_found(product_id)
        prepared = await self._prepare(data)
        key = await self._store(prepared)
        try:
            async with self._session.begin():
                product = await self._products.get_any(product_id, for_update=True)
                if product is None:
                    raise _not_found(product_id)
                old_key = product.image_key
                product.image_key = key
                product.blur_data_url = prepared.thumbnails.blur_data_url
                product.embedding = prepared.embedding.tolist()
                product.embedding_version = self._embedder.version
                await self._products.save(product)
                self._audit.record(actor, "product.image", "product", product_id)
                committed, ordered = await self._holds(product_id)
        except Exception:
            await self._discard(key)
            raise
        if old_key.startswith(ADMIN_IMAGE_PREFIX):
            await self._discard(old_key)
        await self._cache.invalidate_catalogue()
        log.info("product_image_replaced", product_id=product_id, actor_id=actor.id)
        return to_admin_product_out(product, self._storage, committed=committed, ordered=ordered)

    async def set_active(self, product_id: int, *, active: bool, actor: User) -> AdminProductOut:
        """Зарахаа болих эсвэл дахин зарах. Захиалга, сагс, хадгалсан жагсаалт өөрчлөгдөхгүй;
        зарахаа больсон бараа дэлгүүр, хайлт, төстэй барааны жагсаалтад харагдахгүй."""
        async with self._session.begin():
            product = await self._products.get_any(product_id, for_update=True)
            if product is None:
                raise _not_found(product_id)
            if product.is_active != active:
                product.is_active = active
                await self._products.save(product)
                self._audit.record(
                    actor,
                    "product.activate" if active else "product.deactivate",
                    "product",
                    product_id,
                )
            committed, ordered = await self._holds(product_id)
        await self._cache.invalidate_catalogue()
        log.info("product_active_changed", product_id=product_id, active=active, actor_id=actor.id)
        return to_admin_product_out(product, self._storage, committed=committed, ordered=ordered)

    async def set_stock(self, product_id: int, on_hand: int, *, actor: User) -> AdminProductOut:
        """Агуулахад тоолсон тоог оруулна. Барааны мөрийг түгжинэ (checkout, илгээлт, цуцлалт
        ч мөн адил түгждэг), ингэвэл тооллого зэрэг явагдаж буй борлуулалтад алдагдахгүй,
        борлуулалтыг ч алдахгүй."""
        async with self._session.begin():
            product = await self._products.get_any(product_id, for_update=True)
            if product is None:
                raise _not_found(product_id)
            committed, ordered = await self._holds(product_id)
            self._count_shelf(product, on_hand, committed, actor)
            await self._products.save(product)
        await self._cache.invalidate_catalogue()
        return to_admin_product_out(product, self._storage, committed=committed, ordered=ordered)

    async def delete(self, product_id: int, *, actor: User) -> None:
        """Хэзээ ч захиалагдаагүй барааг бүрмөсөн устгана (андуурч нэмсэн гэх мэт). Захиалгад
        орсон бол захиалгын түүх бараа руугаа заадаг тул 409: оронд нь зарахаа болино.

        Барааны мөрийг түгждэг (checkout ч мөн түгждэг) тул шалгалт ба устгалын хооронд шинэ
        захиалга орохгүй; ямар нэг шалтгаанаар орвол өгөгдлийн сангийн `RESTRICT` татгалзана."""
        try:
            async with self._session.begin():
                product = await self._products.get_any(product_id, for_update=True)
                if product is None:
                    raise _not_found(product_id)
                if await self._orders.ordered_product_ids([product_id]):
                    raise _has_orders()
                name, image_key = product.name, product.image_key
                self._audit.record(actor, "product.delete", "product", product_id, {"name": name})
                await self._products.delete(product_id)
        except IntegrityError as error:
            raise _has_orders() from error
        # Мөр устсаны дараа л файлыг устгана: устгалт амжилтгүй бол бараа зураггүй үлдэхгүй.
        # Зураг солихтой адил зөвхөн эндээс upload хийсэн файлыг устгана; dataset-ийнхыг үлдээнэ.
        if image_key.startswith(ADMIN_IMAGE_PREFIX):
            await self._discard(image_key)
        await self._cache.invalidate_catalogue()
        log.info("product_deleted", product_id=product_id, actor_id=actor.id)

    async def _holds(self, product_id: int) -> tuple[int, bool]:
        """(захиалагдсан, илгээгээгүй тоо; хэзээ нэгэн цагт захиалагдсан эсэх)"""
        ordered = await self._orders.ordered_product_ids([product_id])
        return await self._committed(product_id), bool(ordered)

    async def _committed(self, product_id: int) -> int:
        return (await self._orders.committed_units([product_id])).get(product_id, 0)

    def _count_shelf(self, product: Product, on_hand: int, committed: int, actor: User) -> None:
        """Зарах боломжтой = агуулахад байгаа - захиалагдсан. Дуудагч мөрийг түгжсэн байна."""
        if on_hand < committed:
            raise ProblemError(
                HTTPStatus.CONFLICT,
                "Тоо захиалагдсанаас бага байна",
                f"Илгээгээгүй захиалгад {committed} ширхэг байгаа тул агуулахад үүнээс цөөн "
                "байж болохгүй. Бараа дутсан бол эхлээд тухайн захиалгыг цуцлах эсвэл төлбөрийг "
                "нь буцаах шаардлагатай.",
                type_=STOCK_BELOW_COMMITTED_TYPE,
                extensions={"committed": committed},
            )
        previous = product.stock_quantity + committed
        product.stock_quantity = on_hand - committed
        if on_hand != previous:
            self._audit.record(
                actor,
                "product.stock",
                "product",
                product.id,
                {"previous": previous, "quantity": on_hand},
            )
            log.info(
                "product_stock_set",
                product_id=product.id,
                previous=previous,
                on_hand=on_hand,
                committed=committed,
                actor_id=actor.id,
            )

    # --- алхмууд ---

    async def _leaf(self, category_id: int) -> LeafCategory:
        leaves = await self._categories.leaf_categories(category_id)
        if not leaves:
            raise ProblemError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "Ангилал буруу",
                f"{category_id} дугаартай ангилал байхгүй эсвэл барааны төрөл биш байна.",
                type_=INVALID_CATEGORY_TYPE,
            )
        return leaves[0]

    async def _prepare(self, data: bytes) -> PreparedImage:
        try:
            image = await asyncio.to_thread(
                load_image,
                data,
                min_side=DECODE_MIN_SIDE,
                formats=ALLOWED_FORMATS,
                max_pixels=self._max_pixels,
            )
        except InvalidImageError as exc:
            log.info("upload_rejected", reason=str(exc)[:200])
            raise invalid_image(
                "Файл нь JPEG, PNG эсвэл WebP зураг биш, эсвэл зургийн хэмжээ хэт том байна."
            ) from exc
        thumbnails = await asyncio.to_thread(build_thumbnails, image)
        embedding = (await self._embedder.aembed_images([image]))[0]
        return PreparedImage(thumbnails, embedding)

    async def _store(self, prepared: PreparedImage) -> str:
        key = f"{ADMIN_IMAGE_PREFIX}{uuid.uuid4().hex}"
        try:
            for size, webp in prepared.thumbnails.webp.items():
                await asyncio.to_thread(self._storage.put, thumbnail_key(key, size), webp)
        except Exception:
            await self._discard(key)
            raise
        return key

    async def _discard(self, key: str) -> None:
        """Хэрэггүй болсон зургийн файлуудыг (бүх хэмжээ) устгана."""
        for size in THUMBNAIL_SIZES:
            try:
                await asyncio.to_thread(self._storage.delete, thumbnail_key(key, size))
            except Exception as exc:  # цэвэрлэгээ нь түүнийг үүсгэсэн алдааг нуух ёсгүй
                log.warning("image_cleanup_failed", key=key, error=type(exc).__name__)
