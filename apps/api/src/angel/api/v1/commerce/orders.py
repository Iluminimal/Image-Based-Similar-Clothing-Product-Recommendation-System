from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from angel.core.deps import (
    CartServiceDep,
    CurrentUserDep,
    OrderRequestServiceDep,
    OrderServiceDep,
    ShoppingGuard,
    no_store,
)
from angel.core.rate_limit import rate_limit
from angel.schemas.commerce.cart import ReorderOut
from angel.schemas.commerce.order import OrderOut, OrderPage, OrderRequestCreate
from angel.schemas.problem import ProblemDetail

router = APIRouter(
    prefix="/orders",
    tags=["orders"],
    dependencies=[Depends(no_store)],
    responses={401: {"model": ProblemDetail, "description": "Not signed in"}},
)


@router.get("", summary="Your orders, newest first")
async def list_orders(
    user_id: CurrentUserDep,
    service: OrderServiceDep,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> OrderPage:
    return await service.list(user_id, page=page, page_size=page_size)


@router.get(
    "/{number}",
    summary="One of your orders, with the prices as they were charged",
    responses={404: {"model": ProblemDetail, "description": "Not one of your orders"}},
)
async def get_order(
    number: Annotated[str, Path(min_length=4, max_length=20)],
    user_id: CurrentUserDep,
    service: OrderServiceDep,
) -> OrderOut:
    return await service.get(user_id, number)


@router.post(
    "/{number}/cancel",
    summary="Cancel an order that is still waiting for payment",
    description=(
        "Releases the reserved stock and closes the payment invoice. Only orders that have not "
        "been paid can be cancelled; paid orders are refunded by an administrator."
    ),
    responses={
        404: {"model": ProblemDetail, "description": "Not one of your orders"},
        409: {"model": ProblemDetail, "description": "The order is not waiting for payment"},
        502: {"model": ProblemDetail, "description": "The payment provider failed"},
    },
)
async def cancel_order(
    number: Annotated[str, Path(min_length=4, max_length=20)],
    user_id: CurrentUserDep,
    service: OrderServiceDep,
) -> OrderOut:
    return await service.cancel(user_id, number)


@router.post(
    "/{number}/requests",
    summary="Ask to cancel an unshipped order, or to return a delivered one",
    description=(
        "For the whole order. `available_request` on the order says which kind, if any, can be "
        "asked for now. A member of staff decides; nothing is refunded until then."
    ),
    dependencies=[Depends(rate_limit("order_request"))],
    responses={
        404: {"model": ProblemDetail, "description": "Not one of your orders"},
        409: {"model": ProblemDetail, "description": "No such request can be made now"},
        429: {"model": ProblemDetail, "description": "Rate limit exceeded"},
    },
)
async def create_order_request(
    number: Annotated[str, Path(min_length=4, max_length=20)],
    body: OrderRequestCreate,
    user_id: CurrentUserDep,
    service: OrderRequestServiceDep,
) -> OrderOut:
    return await service.create(user_id, number, body)


@router.post(
    "/{number}/requests/{request_id}/withdraw",
    summary="Take back a request that has not been decided",
    responses={
        404: {"model": ProblemDetail, "description": "Not one of your orders"},
        409: {"model": ProblemDetail, "description": "The request is already decided"},
    },
)
async def withdraw_order_request(
    number: Annotated[str, Path(min_length=4, max_length=20)],
    request_id: Annotated[int, Path(ge=1, le=2**63 - 1)],
    user_id: CurrentUserDep,
    service: OrderRequestServiceDep,
) -> OrderOut:
    return await service.withdraw(user_id, number, request_id)


@router.post(
    "/{number}/reorder",
    summary="Put the items of one of your orders back in the bag",
    description=(
        "Each line goes in with the same size and quantity, limited by what is in stock now. Lines "
        "that cannot go in (sold out, withdrawn, bag full) or only partly are listed in `skipped`."
    ),
    responses={
        403: {"model": ProblemDetail, "description": "Staff accounts do not shop"},
        404: {"model": ProblemDetail, "description": "Not one of your orders"},
    },
)
async def reorder(
    number: Annotated[str, Path(min_length=4, max_length=20)],
    user_id: CurrentUserDep,
    _guard: ShoppingGuard,
    service: CartServiceDep,
) -> ReorderOut:
    return await service.reorder(user_id, number)
