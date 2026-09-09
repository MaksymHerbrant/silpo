"""Парсер відповідей MCP Сільпо.

Написаний під ФАКТИЧНУ схему, знайдену пробними викликами (scripts/probe_mcp.py),
а не під вигадану. Реальний silpo_get_product_details повертає:

    {"success": true, "product": {
        "id", "name", "slug", "price", "ratio": "шт", "displayRatio": "13,5г",
        "images": [...], "branchId", "companyId",
        "attributes": {
            "Торгова марка": "Nesquik",
            "Країна": "Угорщина",
            "Енергетична цінність (кКал/кДЖ)": "386/1634",
            "Білки (г)": 5.1, "Жири (г)": 3.6, "Вуглеводи (г)": 78.9,
            "Містить алергени": "МОЛОКО.  Може містити сліди: ПШЕНИЦЮ, СОЮ.",
            "Склад": "борошно ПШЕНИЧНЕ в/с, вода питна, ..."
        }}}

Ключі атрибутів — довільний текст українською з одиницями в дужках, тому
зіставляємо їх ПІДРЯДКОМ, а не точним збігом. Чого в каталозі немає взагалі:
цукор, насичені жири, сіль, клітковина — див. app/nutrition/score.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Підрядки нормалізованого ключа атрибута -> поле харчової цінності.
# Порядок важливий: перший збіг виграє.
ATTR_MATCHERS: list[tuple[str, tuple[str, ...]]] = [
    ("energy_kcal", ("енергетичнацінність", "енергетична", "калорійність", "ккал", "kcal", "energy")),
    ("saturated_fat", ("насиченіжир", "насичених", "saturated")),
    ("sugar", ("цукор", "цукри", "sugar")),
    ("fiber", ("клітковин", "харчовіволокна", "fiber", "fibre")),
    ("salt", ("сіль", "salt")),
    ("sodium", ("натрій", "sodium")),
    ("protein", ("білк", "білок", "protein")),
    ("fat", ("жир", "fat")),
    ("carbs", ("вуглевод", "carbohydrate", "carbs")),
]

BRAND_ATTRS = ("торговамарка", "бренд", "brand", "тм")
ALLERGEN_ATTRS = ("міститьалергени", "алерген", "allergen")
INGREDIENT_ATTRS = ("склад", "ingredients", "composition")
COUNTRY_ATTRS = ("країна",)
ALCOHOL_ATTRS = ("спирту", "алкоголь", "alcohol")

# Власні марки Сільпо — пріоритет у свопах
OWN_BRAND_MARKERS = (
    "власна марка", "премія", "premiya", "premia", "зелена країна", "делікатеси",
    "щедрий дар", "то що треба", "sk", "лавка традицій", "самі свої", "фуршет",
    "розумний вибір", "сільпо", "silpo",
)

_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")


def norm(text: str) -> str:
    return re.sub(r"[^a-zа-яіїєґ0-9]", "", str(text).lower())


def to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = _NUM.search(str(value))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


def is_liquid_unit(text: Any) -> bool:
    raw = str(text or "").strip().lower()
    return any(u in raw for u in ("л", "мл", "l", "ml")) and "кл" not in raw


# Вага часто не в окремому полі, а всередині назви: «Крупа гречана 800 г»,
# «Олія соняшникова 1,15 л», «Яйця курячі С1, 10 шт».
_WEIGHT_IN_NAME = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(кг|kg|г\b|g\b|мл|ml|л\b|l\b)", re.IGNORECASE
)


def weight_from_name(name: str | None) -> float | None:
    if not name:
        return None
    matches = _WEIGHT_IN_NAME.findall(str(name))
    if not matches:
        return None
    # беремо найбільше знайдене значення: у назві може бути і «2 шт по 500 г»
    best = None
    for value, unit in matches:
        try:
            number = float(value.replace(",", "."))
        except ValueError:
            continue
        unit = unit.lower()
        grams = number * 1000 if unit.startswith(("кг", "kg", "л", "l")) else number
        if 5 <= grams <= 20000 and (best is None or grams > best):
            best = grams
    return best


def parse_weight_grams(text: Any) -> float | None:
    """'13,5г' -> 13.5 | '0,46л' -> 460 | '1 кг' -> 1000 | 'шт' -> None."""
    if text is None:
        return None
    raw = str(text).strip().lower().replace(",", ".")
    m = _NUM.search(raw)
    if not m:
        return None
    value = float(m.group(0))
    unit = raw[m.end():].strip()
    if unit.startswith(("кг", "kg", "л", "l")):
        return value * 1000
    if unit.startswith(("мл", "ml", "г", "g")):
        return value
    return value if value > 0 else None


@dataclass
class Nutrition:
    """Харчова цінність на 100 г/мл. None = даних немає (НЕ нуль)."""

    energy_kcal: float | None = None
    protein: float | None = None
    fat: float | None = None
    carbs: float | None = None
    saturated_fat: float | None = None
    sugar: float | None = None
    fiber: float | None = None
    salt: float | None = None
    sodium: float | None = None
    sources: dict[str, str] = field(default_factory=dict)

    @property
    def macros(self) -> list[float | None]:
        return [self.protein, self.fat, self.carbs]

    @property
    def has_minimum(self) -> bool:
        """Мінімум для оцінки: калорійність + хоча б один макронутрієнт.

        Свідомо НЕ вимагаємо цукор/сіль — їх немає в каталозі Сільпо в принципі,
        і така вимога відкинула б 100% товарів.
        """
        return self.energy_kcal is not None and any(m is not None for m in self.macros)

    @property
    def missing(self) -> list[str]:
        return [
            name for name in ("energy_kcal", "protein", "fat", "carbs")
            if getattr(self, name) is None
        ]


@dataclass
class ProductInfo:
    product_id: str
    slug: str
    title: str
    brand: str | None
    country: str | None
    ingredients: str | None
    allergens_text: str | None
    image: str | None
    price: float | None
    old_price: float | None
    weight_g: float | None
    is_alcohol: bool
    is_liquid: bool
    nutrition: Nutrition
    is_own_brand: bool
    raw_attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def has_nutrition(self) -> bool:
        return self.nutrition.has_minimum

    @property
    def discount(self) -> float:
        """Скільки гість економить на цій упаковці просто зараз."""
        if self.old_price and self.price and self.old_price > self.price:
            return round(self.old_price - self.price, 2)
        return 0.0

    @property
    def on_promotion(self) -> bool:
        return self.discount > 0


def parse_attributes(attributes: dict[str, Any]) -> Nutrition:
    n = Nutrition()
    for key, value in (attributes or {}).items():
        nk = norm(key)
        for field_name, needles in ATTR_MATCHERS:
            if getattr(n, field_name) is not None:
                continue
            if not any(needle in nk for needle in needles):
                continue
            # "386/1634" -> перше число це ккал, друге кДж
            num = to_float(str(value).split("/")[0] if field_name == "energy_kcal" else value)
            if num is None:
                continue
            setattr(n, field_name, num)
            n.sources[field_name] = key
            break

    # Санітарна перевірка: макронутрієнт на 100 г не буває > 100 г
    for macro in ("protein", "fat", "carbs", "saturated_fat", "sugar", "fiber", "salt"):
        val = getattr(n, macro)
        if val is not None and not (0 <= val <= 100):
            setattr(n, macro, None)
            n.sources.pop(macro, None)
    if n.energy_kcal is not None and n.energy_kcal > 900:
        n.energy_kcal = round(n.energy_kcal / 4.184, 1)  # схоже, це кДж
    return n


def _attr(attributes: dict[str, Any], needles: tuple[str, ...]) -> str | None:
    for key, value in (attributes or {}).items():
        if any(needle in norm(key) for needle in needles):
            text = str(value).strip()
            if text and text.lower() not in ("none", "null"):
                return text
    return None


def detect_own_brand(*values: str | None) -> bool:
    blob = " ".join(v.lower() for v in values if v)
    return any(marker in blob for marker in OWN_BRAND_MARKERS)


def parse_product(payload: Any, fallback_slug: str = "", fallback_title: str = "") -> ProductInfo:
    """Приймає відповідь silpo_get_product_details цілком або вже поле product."""
    product = payload
    if isinstance(payload, dict) and "product" in payload:
        product = payload["product"]
    if not isinstance(product, dict):
        product = {}

    attributes = product.get("attributes") or {}
    brand = _attr(attributes, BRAND_ATTRS)
    title = product.get("name") or fallback_title or fallback_slug
    weight = (
        parse_weight_grams(product.get("displayRatio"))
        or parse_weight_grams(product.get("ratio"))
        or weight_from_name(title)
    )
    if product.get("weighted") and not weight:
        weight = 1000.0     # ваговий товар: кількість рахується в кілограмах
    images = product.get("images") or []

    return ProductInfo(
        product_id=str(product.get("id") or ""),
        slug=str(product.get("slug") or fallback_slug),
        title=str(title),
        brand=brand,
        country=_attr(attributes, COUNTRY_ATTRS),
        ingredients=_attr(attributes, INGREDIENT_ATTRS),
        allergens_text=_attr(attributes, ALLERGEN_ATTRS),
        image=(product.get("image") or (images[0] if images else None)),
        price=to_float(product.get("price")),
        old_price=to_float(product.get("oldPrice")),
        weight_g=weight,
        is_alcohol=_attr(attributes, ALCOHOL_ATTRS) is not None,
        is_liquid=is_liquid_unit(product.get("displayRatio")) or is_liquid_unit(product.get("ratio")),
        nutrition=parse_attributes(attributes),
        is_own_brand=detect_own_brand(brand, str(title)),
        raw_attributes=attributes,
    )
