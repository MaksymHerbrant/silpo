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


@dataclass(frozen=True)
class Restriction:
    slug: str
    label: str           # як показати користувачу
    triggers: tuple[str, ...]   # підрядки для пошуку у складі (нижній регістр)


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
    """product — ProductInfo. Повертає збіги обмежень зі складом товару."""
    if not restrictions:
        return []

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
            hits.append(
                AllergenHit(
                    product_id=product_id,
                    product_title=product.title,
                    restriction=restriction.label,
                    matched_text=snippet,
                    severity=severity,
                )
            )
            break
    return hits
