"""Хувцас, гутал, аксессуарын төрлийг илэрхийлэх монгол үгс -> каталогийн article type.

**Хайлт ямар үг ойлгохыг нэмэх, засах бол зөвхөн энэ файлыг өөрчилнө.**

- `label` бол web-д орчуулгатай англи нэр (`apps/web/src/i18n/vocab-mn.ts`). Хэрэглэгчид "ингэж
  ойлголоо" гэж харуулахад хэрэглэнэ.
- `types` бол каталогийн article type-ууд. Каталогид байхгүйг нь алгасна.
- Хэллэгийг үг үгээр нь, бүтнээр нь тулгана. Урт хэллэг түрүүлж тулгагдана ("жинсэн өмд" нь
  "өмд"-өөс өмнө). Нөхцөл (`query_parser._SUFFIXES`) залгасан хэлбэрийг танина. Нөхцөл залгахад
  үндэс нь өөрчлөгддөг үгийг ("гутлууд") тусад нь бичнэ.
- Сайт дээр харагддаг бүх төрлийн нэрийг эндээс таньж чаддаг байх ёстой (`test_garment_words.py`
  шалгана).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Garment:
    label: str
    types: tuple[str, ...]
    phrases: tuple[str, ...]


def _g(label: str, types: tuple[str, ...], *phrases: str) -> Garment:
    return Garment(label, types, phrases)


_FOOTWEAR = (
    "Casual Shoes", "Sports Shoes", "Formal Shoes", "Heels", "Flats", "Booties",
    "Sandals", "Sports Sandals", "Flip Flops",
)  # fmt: skip
_BAGS = (
    "Handbags", "Backpacks", "Rucksacks", "Clutches", "Duffel Bag", "Laptop Bag",
    "Messenger Bag", "Trolley Bag", "Waist Pouch",
)  # fmt: skip
_JEWELLERY = (
    "Earrings", "Necklace and Chains", "Pendant", "Ring", "Bracelet", "Bangle", "Jewellery Set",
)  # fmt: skip

GARMENTS: tuple[Garment, ...] = (
    # --- дээд хувцас ---
    _g("Shirts", ("Shirts", "Tshirts", "Tops"), "цамц"),
    _g("T-shirts", ("Tshirts", "Lounge Tshirts"), "футболк", "футболка", "поло цамц"),
    _g("Lounge T-shirts", ("Lounge Tshirts",), "гэрийн футболк"),
    _g("Tops", ("Tops",), "топ"),
    _g("Tunics", ("Tunics",), "туник"),
    _g("Sweaters", ("Sweaters",), "свитер", "ноосон цамц"),
    _g("Sweatshirts", ("Sweatshirts",), "свитшот", "худи", "малгайтай цамц"),
    _g("Shrug", ("Shrug",), "богино кардиган"),
    _g("Jackets", ("Jackets", "Rain Jacket", "Blazers", "Nehru Jackets"), "хүрэм", "куртка",
       "жакет"),
    _g("Rain Jacket", ("Rain Jacket",), "борооны хүрэм", "борооны цув"),
    _g("Blazers", ("Blazers",), "блэйзер"),
    _g("Nehru Jackets", ("Nehru Jackets",), "неру хүрэм"),
    _g("Waistcoat", ("Waistcoat",), "жилет"),
    _g("Innerwear Vests", ("Innerwear Vests",), "майк", "дотуур майк"),
    # --- доод хувцас ---
    _g("Trousers", ("Trousers", "Jeans", "Track Pants"), "өмд"),
    _g("Jeans", ("Jeans",), "жинс", "жинсэн өмд"),
    _g("Track Pants", ("Track Pants",), "спортын өмд", "спорт өмд"),
    _g("Rain Trousers", ("Rain Trousers",), "борооны өмд"),
    _g("Lounge Pants", ("Lounge Pants",), "гэрийн өмд"),
    _g("Shorts", ("Shorts", "Lounge Shorts"), "богино өмд", "шорт"),
    _g("Lounge Shorts", ("Lounge Shorts",), "гэрийн богино өмд"),
    _g("Capris", ("Capris",), "капри"),
    _g("Leggings", ("Leggings", "Jeggings"), "леггинс", "лосин"),
    _g("Jeggings", ("Jeggings",), "жеггинс"),
    _g("Tights", ("Tights",), "колготик"),
    _g("Skirts", ("Skirts",), "банзал", "юбка"),
    # --- даашинз, иж бүрдэл, үндэсний хувцас ---
    _g("Dresses", ("Dresses",), "даашинз", "платье"),
    _g("Jumpsuit", ("Jumpsuit",), "жампсүүт"),
    _g("Rompers", ("Rompers",), "ромпер"),
    _g("Tracksuits", ("Tracksuits",), "спортын костюм", "спорт костюм"),
    _g("Clothing Set", ("Clothing Set",), "хувцасны иж бүрдэл"),
    _g("Kurtas", ("Kurtas", "Kurtis"), "курта"),
    _g("Kurtis", ("Kurtis",), "курти"),
    _g("Kurta Sets", ("Kurta Sets",), "курта иж бүрдэл"),
    _g("Sarees", ("Sarees",), "сари"),
    _g("Dupatta", ("Dupatta",), "дупатта"),
    _g("Salwar", ("Salwar",), "салвар"),
    _g("Salwar and Dupatta", ("Salwar and Dupatta",), "салвар ба дупатта"),
    _g("Churidar", ("Churidar",), "чуридар"),
    _g("Patiala", ("Patiala",), "патиала"),
    _g("Lehenga Choli", ("Lehenga Choli",), "лехенга чоли"),
    _g("Swimwear", ("Swimwear",), "усны хувцас"),
    # --- гэрийн, унтлагын, дотуур ---
    _g("Night suits", ("Night suits", "Nightdress"), "унтлагын хувцас", "пижама"),
    _g("Nightdress", ("Nightdress",), "унтлагын даашинз"),
    _g("Baby Dolls", ("Baby Dolls",), "богино унтлагын даашинз"),
    _g("Robe", ("Robe", "Bath Robe"), "халаад"),
    _g("Innerwear", ("Briefs", "Bra", "Trunk", "Boxers", "Innerwear Vests", "Camisoles",
                     "Shapewear"), "дотуур хувцас"),
    _g("Briefs", ("Briefs", "Trunk"), "дотуур өмд", "дотоож"),
    _g("Boxers", ("Boxers",), "боксер"),
    _g("Bra", ("Bra",), "хөхний даруулга", "лифчик"),
    _g("Camisoles", ("Camisoles",), "камисол"),
    _g("Shapewear", ("Shapewear",), "биеийн хэлбэр засах дотуур хувцас"),
    _g("Socks", ("Socks",), "оймс"),
    _g("Stockings", ("Stockings",), "урт оймс"),
    # --- гутал ---
    _g("Shoes", _FOOTWEAR, "гутал", "гутлууд", "гутлын"),
    _g("Casual Shoes", ("Casual Shoes",), "энгийн гутал"),
    _g("Sports Shoes", ("Sports Shoes",), "спортын гутал", "спорт гутал"),
    _g("Sports Shoes", ("Sports Shoes", "Casual Shoes"), "пүүз", "кет"),
    _g("Formal Shoes", ("Formal Shoes",), "албан ёсны гутал"),
    _g("Heels", ("Heels",), "өндөр өсгийтэй гутал", "өсгийтэй гутал"),
    _g("Flats", ("Flats",), "хавтгай ултай гутал"),
    _g("Booties", ("Booties",), "шагай гутал"),
    _g("Sandals", ("Sandals", "Sports Sandals"), "сандаль", "сандал"),
    _g("Sports Sandals", ("Sports Sandals",), "спортын сандаль"),
    _g("Flip Flops", ("Flip Flops",), "шаахай", "углааш"),
    _g("Shoe Laces", ("Shoe Laces",), "гутлын үдээс"),
    # --- цүнх ---
    _g("Bags", _BAGS, "цүнх"),
    _g("Handbags", ("Handbags", "Clutches"), "гар цүнх"),
    _g("Clutches", ("Clutches",), "клач"),
    _g("Backpacks", ("Backpacks", "Rucksacks"), "үүргэвч"),
    _g("Duffel Bag", ("Duffel Bag",), "аяллын цүнх"),
    _g("Laptop Bag", ("Laptop Bag",), "зөөврийн компьютерын цүнх", "ноутбукийн цүнх"),
    _g("Messenger Bag", ("Messenger Bag",), "мөрөвч цүнх"),
    _g("Trolley Bag", ("Trolley Bag",), "дугуйтай чемодан", "чемодан"),
    _g("Waist Pouch", ("Waist Pouch",), "бэлхийн уут"),
    _g("Mobile Pouch", ("Mobile Pouch",), "утасны уут"),
    _g("Tablet Sleeve", ("Tablet Sleeve",), "таблетын уут"),
    _g("Wallets", ("Wallets",), "түрийвч", "хэтэвч"),
    # --- аксессуар ---
    _g("Watches", ("Watches",), "цаг", "бугуйн цаг"),
    _g("Sunglasses", ("Sunglasses",), "нарны шил", "нүдний шил", "нарны нүдний шил"),
    _g("Belts", ("Belts",), "бүс"),
    _g("Hat", ("Hat", "Caps"), "малгай"),
    _g("Caps", ("Caps",), "кепка", "кепк", "малгай кепка"),
    _g("Headband", ("Headband",), "толгойн боолт"),
    _g("Hair Accessory", ("Hair Accessory",), "үсний хэрэгсэл"),
    _g("Wristbands", ("Wristbands",), "бугуйн боолт"),
    _g("Gloves", ("Gloves",), "бээлий"),
    _g("Scarves", ("Scarves", "Mufflers", "Stoles"), "ороолт"),
    _g("Mufflers", ("Mufflers",), "хүзүүний ороолт"),
    _g("Stoles", ("Stoles",), "шаль"),
    _g("Ties", ("Ties",), "зангиа"),
    _g("Cufflinks", ("Cufflinks",), "ханцуйн товч"),
    _g("Ties and Cufflinks", ("Ties and Cufflinks",), "зангиа ба ханцуйн товч"),
    _g("Suspenders", ("Suspenders",), "өмдний оосор"),
    _g("Umbrellas", ("Umbrellas",), "шүхэр"),
    _g("Water Bottle", ("Water Bottle",), "усны сав"),
    _g("Key chain", ("Key chain",), "түлхүүрийн оосор"),
    _g("Travel Accessory", ("Travel Accessory",), "аяллын хэрэгсэл"),
    _g("Perfume and Body Mist", ("Perfume and Body Mist",), "үнэртэн ба биеийн спрей", "үнэртэн"),
    _g("Accessory Gift Set", ("Accessory Gift Set",), "аксессуарын бэлгийн иж бүрдэл"),
    # --- гоёл чимэглэл ---
    _g("Jewellery", _JEWELLERY, "үнэт эдлэл", "гоёл чимэглэл"),
    _g("Jewellery Set", ("Jewellery Set",), "үнэт эдлэлийн иж бүрдэл"),
    _g("Earrings", ("Earrings",), "ээмэг"),
    _g("Necklace and Chains", ("Necklace and Chains", "Pendant"), "зүүлт"),
    _g("Necklace and Chains", ("Necklace and Chains",), "зүүлт ба гинж"),
    _g("Pendant", ("Pendant",), "дүүжин зүүлт"),
    _g("Ring", ("Ring",), "бөгж"),
    _g("Bracelet", ("Bracelet", "Bangle"), "бугуйвч"),
    _g("Bangle", ("Bangle",), "хатуу бугуйвч"),
)  # fmt: skip

# Ерөнхий үг: тодорхой төрлийн нэртэй хамт бичвэл тооцохгүй ("хувцас даашинз" = даашинз).
MASTERS: tuple[Garment, ...] = (
    _g("Clothing", ("Apparel",), "хувцас"),
    _g("Accessories", ("Accessories",), "аксессуар"),
)

# Хайлтад утга нэмдэггүй үгс: "танигдаагүй" гэж мэдээлэхгүй.
STOP_WORDS = frozenset(
    {
        "өнгийн", "өнгөтэй", "өнгө", "төрлийн", "бараа", "ба", "болон", "эсвэл", "авах",
        "авмаар", "хайх", "хайж", "байна", "надад", "хэрэгтэй",
    }
)  # fmt: skip
