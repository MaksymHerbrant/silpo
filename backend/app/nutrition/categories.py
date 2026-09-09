"""Категоріальний баланс кошика.

СВІДОМЕ ПРОДУКТОВЕ РІШЕННЯ: центральна метрика продукту — структура покупок за
категоріями, а не БЖУ.

Причина не в зручності, а в даних. Каталог Сільпо не містить цукру, солі,
насичених жирів і клітковини, а базові продукти (м'ясо, крупи, яйця) часто
взагалі без харчової цінності. Будувати головну фічу на таких даних —
означає відповідати на питання «звідки числа?» виправданнями.

Категорія ж визначається надійно: за назвою товару та його місцем у чеку.
Ми не ставимо діагнозів і не призначаємо дієт — ми показуємо СТРУКТУРУ
покупок і допомагаємо змістити її під ціль, яку обрав сам гість.

Орієнтири взяті з Harvard Healthy Eating Plate і використовуються ЯК ЕВРИСТИКА
для формування збалансованішого кошика, а не як медична норма.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Категорія -> маркери в назві товару. Порядок має значення: перший збіг виграє.
CATEGORY_MARKERS: dict[str, tuple[str, ...]] = {
    "veg_fruit": (
        "огірок", "помідор", "томат", "капуст", "морква", "цибул", "перець", "кабач",
        "броколі", "салат", "зелень", "шпинат", "буряк", "гарбуз", "баклажан", "редис",
        "яблук", "банан", "груш", "апельсин", "мандарин", "ягод", "виноград", "ківі",
        "лимон", "авокадо", "слив", "персик", "кавун", "диня", "інжир", "гриб", "зеленн",
    ),
    "protein": (
        "філе", "куряч", "індич", "яловичин", "свинин", "фарш", "стейк", "мітбол",
        "риба", "лосос", "сьомга", "тунец", "дорадо", "форель", "креветк", "яйц",
        "квасол", "нут", "сочевиц", "тофу", "печінк", "стегн",
    ),
    "grains": (
        "хліб", "багет", "булк", "крупа", "рис", "гречк", "макарон", "паста", "борошн",
        "пластівц", "мюслі", "картопл", "булгур", "кус-кус", "лаваш", "тортил", "каша",
    ),
    "dairy": ("молоко", "йогурт", "кефір", "сметан", "сир", "творог", "вершк", "масло вершкове"),
    "ultra_processed": (
        "чіпс", "снек", "печив", "шоколад", "цукерк", "батончик", "вафл", "сухарик",
        "круасан", "тістечк", "торт", "морозиво", "ковбас", "сосиск", "салямі", "бекон",
        "шинк", "паштет", "напівфабрикат", "пельмен", "вареник", "нагетс", "піца",
        "майонез", "кетчуп", "соус", "локшина швидк",
    ),
    "sweet_drinks": ("кола", "cola", "pepsi", "фанта", "спрайт", "лимонад", "нектар",
                     "енергетич", "energy", "морс", "сік "),
    "alcohol": ("пиво", "вино", "віскі", "горілк", "лікер", "сидр", "коньяк", "шампан"),
    "other": (),
}

CATEGORY_LABELS = {
    "veg_fruit": "Овочі та фрукти",
    "protein": "Білкові продукти",
    "grains": "Крупи та хліб",
    "dairy": "Молочні продукти",
    "ultra_processed": "Оброблені продукти",
    "sweet_drinks": "Солодкі напої",
    "alcohol": "Алкоголь",
    "other": "Інше",
}

# Евристичні орієнтири частки ВИТРАТ, натхнені Harvard Healthy Eating Plate.
# Це не медична норма — це орієнтир для збалансованішого кошика.
TARGET_SHARES: dict[str, tuple[float, float]] = {
    "veg_fruit": (25.0, 40.0),
    "protein": (20.0, 30.0),
    "grains": (15.0, 25.0),
    "dairy": (8.0, 18.0),
    "ultra_processed": (0.0, 12.0),
    "sweet_drinks": (0.0, 5.0),
    "alcohol": (0.0, 8.0),
}

# Куди зміщувати структуру під різні цілі гостя
GOAL_FOCUS: dict[str, dict[str, str]] = {
    "less_sugar": {
        "reduce": "sweet_drinks", "grow": "veg_fruit",
        "label": "Менше цукру",
        "hint": "зменшуємо частку солодких напоїв і оброблених продуктів",
    },
    "save_money": {
        "reduce": "ultra_processed", "grow": "grains",
        "label": "Заощадити гроші",
        "hint": "більше базових продуктів і акційних позицій замість дорогих оброблених",
    },
    "muscle": {
        "reduce": "sweet_drinks", "grow": "protein",
        "label": "Набрати м'язи",
        "hint": "збільшуємо частку білкових продуктів",
    },
    "healthier": {
        "reduce": "ultra_processed", "grow": "veg_fruit",
        "label": "Здоровіший раціон",
        "hint": "більше овочів і фруктів, менше оброблених продуктів",
    },
}


def categorize(name: str) -> str:
    low = (name or "").lower()
    for category, markers in CATEGORY_MARKERS.items():
        if markers and any(m in low for m in markers):
            return category
    return "other"


@dataclass
class CategoryStat:
    key: str
    label: str
    spend: float
    share: float
    items: int
    target: tuple[float, float] | None
    status: str            # ok | above | below | neutral

    def as_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label, "spend": round(self.spend, 2),
            "share": round(self.share, 1), "items": self.items,
            "target_min": self.target[0] if self.target else None,
            "target_max": self.target[1] if self.target else None,
            "status": self.status,
        }


@dataclass
class BasketStructure:
    categories: list[CategoryStat] = field(default_factory=list)
    total_spend: float = 0.0
    focus: dict[str, str] | None = None

    def as_dict(self) -> dict:
        return {
            "categories": [c.as_dict() for c in self.categories],
            "total_spend": round(self.total_spend, 2),
            "focus": self.focus,
            "methodology": (
                "Показуємо структуру витрат за категоріями. Орієнтири натхнені "
                "Harvard Healthy Eating Plate і використовуються як евристика для "
                "збалансованішого кошика, а не як медична норма."
            ),
        }

    def problem_categories(self) -> list[CategoryStat]:
        return [c for c in self.categories if c.status == "above"]


def analyse(lines: list[dict], goal: str | None = None) -> BasketStructure:
    """lines: [{'name': ..., 'price': ..., 'quantity': ...}]"""
    spend: dict[str, float] = {}
    counts: dict[str, int] = {}
    for line in lines:
        category = categorize(line.get("name") or "")
        value = float(line.get("price") or 0) * float(line.get("quantity") or 1)
        spend[category] = spend.get(category, 0.0) + value
        counts[category] = counts.get(category, 0) + 1

    total = sum(spend.values()) or 1.0
    stats: list[CategoryStat] = []
    for key, value in sorted(spend.items(), key=lambda x: -x[1]):
        share = value / total * 100
        target = TARGET_SHARES.get(key)
        if target is None:
            status = "neutral"
        elif share > target[1]:
            status = "above"
        elif share < target[0]:
            status = "below"
        else:
            status = "ok"
        stats.append(CategoryStat(
            key=key, label=CATEGORY_LABELS.get(key, key), spend=value,
            share=share, items=counts[key], target=target, status=status,
        ))

    return BasketStructure(
        categories=stats, total_spend=sum(spend.values()),
        focus=GOAL_FOCUS.get(goal or "", None),
    )
