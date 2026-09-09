"""Звірка обмежень гостя зі складом товару.

Фактична відповідь silpo_get_my_food_restrictions (перевірено):

    {"success": true, "summary": "Found 3 food restrictions",
     "restrictions": [{"slug": "lactoza", "name": null},
                      {"slug": "gluten",  "name": null},
                      {"slug": "sugar",   "name": null}]}

Тобто приходять СЛАГИ без людських назв — їх треба мапити самим. Слаг
`all-food` означає «обмежень немає».

Джерело для звірки — атрибути товару:
  «Містить алергени» -> "МОЛОКО.  Може містити сліди: ПШЕНИЦЮ, СОЮ."
  «Склад»            -> повний перелік інгредієнтів
Перший цінніший: там алергени вже виділені виробником.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

NO_RESTRICTION_SLUGS = {"all-food", "all_food", "none", ""}

# Два принципово різні типи обмежень — і поводимось із ними по-різному.
#
# ALLERGEN — питання безпеки. Діє глобально: якщо в складі є молоко, а гість
# не переносить лактозу, товар блокується незалежно від категорії.
#
# PREFERENCE — дієтичне вподобання. Діє КОНТЕКСТНО, лише в категоріях явного
# джерела. «Без цукру» не має вирізати хліб, молочку й соуси, де цукор —
# технологічний компонент: гість отримає напівпорожній кошик і закриє застосунок.
# Тому таке обмеження працює там, де цукор є суттю продукту: солодкі напої,
# солодощі й снеки. У решті категорій — м'яка позначка, без блокування.
KIND_ALLERGEN = "allergen"
KIND_PREFERENCE = "preference"

RESTRICTION_KIND: dict[str, str] = {
    "sugar": KIND_PREFERENCE,
    "alcohol": KIND_PREFERENCE,
    "vegetarian": KIND_PREFERENCE,
    "vegan": KIND_PREFERENCE,
    "halal": KIND_PREFERENCE,
    "meat": KIND_PREFERENCE,
    "pork": KIND_PREFERENCE,
}

# Категорії, у яких вподобання діє жорстко (див. nutrition/categories.py)
PREFERENCE_SCOPE: dict[str, set[str]] = {
    "sugar": {"sweet_drinks", "ultra_processed"},
    "alcohol": {"alcohol"},
    "vegetarian": {"protein"},
    "vegan": {"protein", "dairy"},
    "halal": {"protein"},
    "meat": {"protein"},
    "pork": {"protein"},
}


@dataclass(frozen=True)
class Restriction:
    slug: str
    label: str           # як показати користувачу
    triggers: tuple[str, ...]   # підрядки для пошуку у складі (нижній регістр)

    @property
    def kind(self) -> str:
        return RESTRICTION_KIND.get(self.slug, KIND_ALLERGEN)

    @property
    def scope(self) -> set[str] | None:
        """Категорії, у яких обмеження діє жорстко. None = скрізь."""
        return PREFERENCE_SCOPE.get(self.slug) if self.kind == KIND_PREFERENCE else None


# slug із профілю Сільпо -> людська назва + тригери у складі
RESTRICTION_MAP: dict[str, tuple[str, tuple[str, ...]]] = {
    "lactoza": ("Лактоза", ("молок", "лактоз", "вершк", "сир", "сироват", "кефір", "йогурт", "масло вершкове", "milk")),
    "lactose": ("Лактоза", ("молок", "лактоз", "вершк", "сир", "сироват", "milk")),
    "gluten": ("Глютен", ("глютен", "пшениц", "пшенич", "жито", "житн", "ячмін", "ячмен", "овес", "вівсян", "солод", "борошн", "gluten", "wheat")),
    "sugar": ("Цукор", ("цукор", "цукру", "сироп", "глюкоз", "фруктоз", "патока", "мальтодекстрин", "меляс", "sugar")),
    "nuts": ("Горіхи", ("горіх", "мигдал", "фундук", "кешʼю", "кеш'ю", "кешью", "фісташ", "nut", "almond")),
    "peanut": ("Арахіс", ("арахіс", "арахис", "peanut")),
    "soy": ("Соя", ("соя", "соєв", "соев", "soy")),
    "egg": ("Яйця", ("яйц", "яєч", "альбумін", "egg")),
    "fish": ("Риба", ("риба", "риб", "тунец", "лосос", "оселед", "fish")),
    "seafood": ("Морепродукти", ("креветк", "мідії", "кальмар", "краб", "молюск", "shrimp")),
    "sesame": ("Кунжут", ("кунжут", "сезам", "тахін", "sesame")),
    "celery": ("Селера", ("селер", "сельдер", "celery")),
    "mustard": ("Гірчиця", ("гірчиц", "горчиц", "mustard")),
    "sulfite": ("Діоксид сірки", ("діоксид сірки", "сульфіт", "e220", "e221", "e222")),
    "pork": ("Свинина", ("свинин", "свиняч", "pork")),
    "meat": ("Мʼясо", ("мʼяс", "м'яс", "яловичин", "курятин", "куряч", "свинин", "індич")),
    "vegetarian": ("Вегетаріанство", ("мʼяс", "м'яс", "яловичин", "куряч", "свинин", "риба", "желатин")),
    "vegan": ("Веганство", ("мʼяс", "м'яс", "молок", "яйц", "мед", "желатин", "риба")),
    "halal": ("Халяль", ("свинин", "свиняч", "желатин", "спирт", "алкогол")),
    "alcohol": ("Алкоголь", ("спирт", "алкогол", "пиво", "вино", "лікер")),
}


@dataclass
class AllergenHit:
    product_id: str
    product_title: str
    restriction: str
    matched_text: str
    severity: str          # high — прямо в переліку алергенів; medium — у складі
    kind: str = KIND_ALLERGEN
    action: str = "block"  # block — прибрати; swap — запропонувати заміну; info — просто позначка
    slug: str = ""


def parse_restrictions(payload) -> list[Restriction]:
    if not isinstance(payload, dict):
        return []
    out: list[Restriction] = []
    for row in payload.get("restrictions") or []:
        if not isinstance(row, dict):
            continue
        slug = str(row.get("slug") or "").strip().lower()
        if slug in NO_RESTRICTION_SLUGS:
            continue
        label, triggers = RESTRICTION_MAP.get(
            slug, (row.get("name") or slug.replace("-", " ").capitalize(), (slug,))
        )
        out.append(Restriction(slug=slug, label=label, triggers=triggers))
    return out


def check_product(product, restrictions: list[Restriction]) -> list[AllergenHit]:
    """Збіги обмежень зі складом товару з урахуванням категорії.

    Алерген знайдено — блокуємо. Вподобання в профільній категорії —
    пропонуємо заміну. Вподобання поза нею — лише інформуємо.
    """
    if not restrictions:
        return []

    from app.nutrition.categories import categorize

    category = categorize(product.title)

    hits: list[AllergenHit] = []
    sources = [
        (product.allergens_text, "high"),
        (product.ingredients, "medium"),
    ]
    product_id = product.product_id or product.slug

    for restriction in restrictions:
        for text, severity in sources:
            if not text:
                continue
            low = text.lower()
            found = next((t for t in restriction.triggers if t in low), None)
            if not found:
                continue
            idx = low.find(found)
            snippet = re.sub(r"\s+", " ", text[max(0, idx - 25): idx + 45]).strip()

            if restriction.kind == KIND_ALLERGEN:
                action = "block"
            elif restriction.scope and category in restriction.scope:
                action = "swap"
            else:
                # Цукор у хлібі чи молочці — технологічний компонент,
                # а не суть продукту. Позначаємо, але не блокуємо.
                action = "info"

            hits.append(
                AllergenHit(
                    product_id=product_id,
                    product_title=product.title,
                    restriction=restriction.label,
                    matched_text=snippet,
                    severity=severity,
                    kind=restriction.kind,
                    action=action,
                    slug=restriction.slug,
                )
            )
            break
    return hits


def blocking(hits: list[AllergenHit]) -> list[AllergenHit]:
    return [h for h in hits if h.action == "block"]


def swap_worthy(hits: list[AllergenHit]) -> list[AllergenHit]:
    return [h for h in hits if h.action == "swap"]
