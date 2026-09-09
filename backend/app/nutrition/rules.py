"""Правила заміни: проблемний товар -> що шукати натомість.

Свідомо БЕЗ LLM. Кожне правило — це:
  * умова спрацювання (маркери в назві + профіль харчової цінності);
  * пошукові запити для silpo_find_products_batch (масив назв, max 30);
  * пояснення, чому заміна краща.

Так двигун передбачуваний, безкоштовний і не залежить від зовнішнього API.
Остаточний відбір усе одно роблять числа: кандидат проходить, лише якщо його
детермінований скор вищий за оригінал (див. services/swap_engine.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from app.nutrition.parser import ProductInfo


@dataclass
class SwapRule:
    key: str
    title: str                      # як пояснити проблему користувачу
    queries: list[str]              # що шукати в Сільпо — ТА САМА роль товару
    reason: str                     # чим заміна краща
    match: Callable[[ProductInfo], bool]
    priority: int = 50
    tags: list[str] = field(default_factory=list)
    # Заміна має виконувати ту саму роль: чіпси міняємо на інші чіпси, а не на
    # броколі. Інакше порада виглядає безглуздо і її ніхто не застосує.
    max_price_ratio: float = 1.25   # дорожче ніж на чверть — не пропонуємо


def _name_has(product: ProductInfo, *markers: str) -> bool:
    low = f"{product.title} {product.brand or ''}".lower()
    return any(m in low for m in markers)


def _carbs(product: ProductInfo) -> float:
    return product.nutrition.carbs or 0


def _kcal(product: ProductInfo) -> float:
    return product.nutrition.energy_kcal or 0


def _protein(product: ProductInfo) -> float:
    return product.nutrition.protein or 0


RULES: list[SwapRule] = [
    SwapRule(
        key="sugary_drink",
        title="Солодкий газований напій",
        queries=[
            "Напій Coca-Cola Zero", "Напій Pepsi Max", "Напій Coca-Cola Light",
            "Чай холодний без цукру", "Сік 100% без цукру", "Напій без цукру газований",
        ],
        reason="той самий смак і газованість, але без цукру",
        match=lambda p: p.is_liquid and not p.is_alcohol and _carbs(p) >= 4,
        priority=95,
        tags=["цукор"],
    ),
    SwapRule(
        key="energy_drink",
        title="Енергетик",
        queries=["Напій енергетичний без цукру", "Напій енергетичний zero", "Кава холодна без цукру"],
        reason="той самий ефект, але без цукру",
        match=lambda p: p.is_liquid and _name_has(p, "energy", "енергетич", "red bull", "monster"),
        priority=96,
        tags=["цукор"],
    ),
    SwapRule(
        key="juice_nectar",
        title="Сік або нектар із цукром",
        queries=["Сік 100% без цукру", "Сік прямого віджиму", "Нектар без цукру"],
        reason="той самий сік, але без доданого цукру",
        match=lambda p: p.is_liquid and _name_has(p, "нектар", "сік", "морс") and _carbs(p) >= 7,
        priority=85,
        tags=["цукор"],
    ),
    SwapRule(
        key="sweet_snack",
        title="Солодкий снек",
        queries=[
            "Печиво вівсяне без цукру", "Батончик злаковий без цукру",
            "Фрукти сушені без цукру", "Чорний шоколад 70%", "Горіхи волоські",
        ],
        reason="той самий формат снеку, але менше цукру",
        match=lambda p: not p.is_liquid and _carbs(p) >= 40 and _kcal(p) >= 300
        and _name_has(p, "шоколад", "цукерк", "печив", "вафл", "батончик", "круасан",
                      "тістечк", "пряник", "рулет", "халва", "десерт"),
        priority=90,
        tags=["цукор"],
    ),
    SwapRule(
        key="chips",
        title="Чіпси й солоні снеки",
        queries=["Чіпси рисові", "Чіпси яблучні", "Попкорн солоний", "Кукурудзяні палички",
                 "Хлібці цільнозернові", "Сухарики житні"],
        reason="той самий хрусткий снек, але менше жиру",
        match=lambda p: not p.is_liquid and _kcal(p) >= 400
        and _name_has(p, "чіпс", "сухарик", "снек", "крекер", "палички солоні"),
        priority=88,
        tags=["жири"],
    ),
    SwapRule(
        key="white_bakery",
        title="Випічка з білого борошна",
        queries=["Хліб цільнозерновий", "Хліб житній", "Хлібці цільнозернові", "Лаваш тонкий"],
        reason="цільне зерно замість білого борошна",
        match=lambda p: not p.is_liquid and _carbs(p) >= 40
        and _name_has(p, "булк", "багет", "батон", "хліб білий", "бургер", "тост"),
        priority=70,
        tags=["вуглеводи"],
    ),
    SwapRule(
        key="processed_meat",
        title="Ковбасні вироби",
        queries=["Філе куряче охолоджене", "Індичка філе", "Тунець консервований у власному соку"],
        reason="більше білка, менше жиру й солі",
        match=lambda p: not p.is_liquid
        and _name_has(p, "ковбас", "сосиск", "салямі", "бекон", "шинк", "паштет", "сарделн"),
        priority=80,
        tags=["жири"],
    ),
    SwapRule(
        key="sweet_dairy",
        title="Солодкий молочний продукт",
        queries=["Йогурт грецький без цукру", "Йогурт натуральний без цукру",
                 "Сир кисломолочний без добавок"],
        reason="без доданого цукру, більше білка",
        match=lambda p: _name_has(p, "йогурт", "сирок", "десерт молоч", "пудинг", "глазурован")
        and _carbs(p) >= 10,
        priority=86,
        tags=["цукор"],
    ),
    SwapRule(
        key="alcohol",
        title="Алкоголь",
        queries=["Пиво безалкогольне", "Сидр безалкогольний", "Напій безалкогольний без цукру"],
        reason="той самий напій, але без алкоголю",
        match=lambda p: p.is_alcohol,
        priority=60,
        tags=["алкоголь"],
    ),
    SwapRule(
        key="high_energy_density",
        title="Дуже калорійний товар",
        queries=["Йогурт грецький без цукру", "Сир кисломолочний 5%", "Хлібці цільнозернові"],
        reason="менша калорійність на 100 г",
        match=lambda p: not p.is_liquid and _kcal(p) >= 450 and _protein(p) < 12,
        priority=40,
        tags=["калорійність"],
    ),
]


def match_rule(product: ProductInfo) -> SwapRule | None:
    """Найпріоритетніше правило, що спрацювало на товарі."""
    if not product.has_nutrition:
        return None
    matched = [r for r in RULES if _safe(r, product)]
    if not matched:
        return None
    return max(matched, key=lambda r: r.priority)


def _safe(rule: SwapRule, product: ProductInfo) -> bool:
    try:
        return rule.match(product)
    except Exception:  # noqa: BLE001 — правило не має валити аналіз
        return False
