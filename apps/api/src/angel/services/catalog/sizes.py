"""Бараа ямар хэмжээтэй ирдэг вэ.

Catalogue-д хэмжээний өгөгдөл байхгүй тул хэмжээг ангиллаас гаргана. Энэ нь барааны хуудас юу
санал болгохыг шийддэг `apps/web/src/features/catalog/sizes.ts`-тэй таарна; хоёрыг нэг хэвээр
байлга. Үлдэгдлийг хэмжээ бүрээр биш, бараагаар нь хөтөлнө."""

from angel.models import Product

_CLOTHING = ("XS", "S", "M", "L", "XL", "XXL")
_KIDS_CLOTHING = ("2-3Y", "4-5Y", "6-7Y", "8-9Y", "10-11Y")
_SHOES = ("6", "7", "8", "9", "10", "11")
_KIDS_SHOES = ("10C", "11C", "12C", "13C", "1Y", "2Y")
_BELTS = ("S", "M", "L")


def sizes_for(product: Product) -> tuple[str, ...]:
    """Хэмжээ хамаарахгүй бараанд (цаг, цүнх, үнэт эдлэл, үнэртэн) хоосон."""
    kids = product.gender in ("Boys", "Girls")
    if product.master_category == "Apparel":
        return _KIDS_CLOTHING if kids else _CLOTHING
    if product.master_category == "Footwear":
        return _KIDS_SHOES if kids else _SHOES
    if product.sub_category == "Belts":
        return _BELTS
    return ()
