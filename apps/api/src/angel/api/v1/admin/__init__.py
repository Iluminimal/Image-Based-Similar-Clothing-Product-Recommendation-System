"""Back-office-ийн API. Бүх хэсэг ижил хамгаалалттай: эхлээд rate limit шалгана (token таах
оролдлогыг удаашруулна), дараа нь ажилтан мөн эсэхийг шалгана. Хариуг cache хийхгүй.

Ямар role юу хийхийг endpoint бүр өөрөө тодорхойлно:
- Агуулахын ажилтан (`WarehouseDep`): бараа, нөөц өөрчлөх; захиалга илгээх, хүргэх (ship/deliver).
- Админ (`AdminDep`): хэрэглэгч, сэтгэгдэл, статистик; захиалга цуцлах, төлбөр буцаах.
- Аль ч ажилтан (`StaffDep`): бараа, захиалга харах."""

from fastapi import APIRouter, Depends

from angel.api.v1.admin import (
    audit,
    customers,
    export,
    fulfillment,
    orders,
    products,
    reviews,
    stats,
)
from angel.core.deps import get_current_admin, get_current_staff, no_store
from angel.core.rate_limit import rate_limit
from angel.schemas.problem import ProblemDetail

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(rate_limit("admin")), Depends(get_current_staff), Depends(no_store)],
    responses={
        401: {"model": ProblemDetail, "description": "Not signed in"},
        403: {
            "model": ProblemDetail,
            "description": "Not a staff account, or not allowed for this role",
        },
        429: {"model": ProblemDetail, "description": "Rate limit exceeded"},
    },
)
# Бараа, захиалгад endpoint бүр өөрийн role-оо тодорхойлно (дээрх тайлбар).
for section in (products, orders, fulfillment):
    router.include_router(section.router)
# Хэрэглэгч, статистик, сэтгэгдлийн хэсэг бүхэлдээ админых: агуулахын ажилтан нэвтэрч чадахгүй.
for section in (audit, customers, export, stats, reviews):
    router.include_router(section.router, dependencies=[Depends(get_current_admin)])
