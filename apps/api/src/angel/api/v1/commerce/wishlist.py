from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from angel.core.deps import CurrentUserDep, WishlistServiceDep, forbid_staff_shopping, no_store
from angel.schemas.commerce.wishlist import WishlistOut
from angel.schemas.problem import ProblemDetail

router = APIRouter(
    prefix="/wishlist",
    tags=["wishlist"],
    # Ажилтан худалдан авалт хийдэггүй тул энэ хэсэг тэдэнд хаалттай.
    dependencies=[Depends(no_store), Depends(forbid_staff_shopping)],
    responses={
        401: {"model": ProblemDetail, "description": "Not signed in"},
        403: {"model": ProblemDetail, "description": "A staff account"},
    },
)

ProductId = Annotated[int, Path(ge=1, le=2**63 - 1)]


@router.get("", summary="Saved products, newest first")
async def list_wishlist(user_id: CurrentUserDep, service: WishlistServiceDep) -> WishlistOut:
    return await service.list(user_id)


@router.put(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Save a product (idempotent)",
    responses={404: {"model": ProblemDetail, "description": "Unknown or inactive product"}},
)
async def add_to_wishlist(
    product_id: ProductId, user_id: CurrentUserDep, service: WishlistServiceDep
) -> None:
    await service.add(user_id, product_id)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a product (idempotent)",
)
async def remove_from_wishlist(
    product_id: ProductId, user_id: CurrentUserDep, service: WishlistServiceDep
) -> None:
    await service.remove(user_id, product_id)
