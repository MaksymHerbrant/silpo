"""Фільтр шуму з адаптивним вікном частоти.

Проблема жорсткого порогу «купував 2+ рази»: він знищує довгий хвіст.
Молоко раз на місяць, туалетний папір, соуси, спеції, побутова хімія —
усе це зникає з поля зору, і гість вирішує, що застосунок зламався.

Рішення: **у кожної категорії свій цикл покупки**. Хліб беруть щотижня,
молочку — раз на два тижні, побутову хімію — раз на два місяці. Тому поріг
рахується не в абсолютних разах, а від того, скільки покупок ОЧІКУВАНО
за наявний період саме для цієї категорії.

    очікувано = період / цикл категорії
    поріг     = max(1, round(очікувано × 0.4))

Хліб за 46 днів: очікувано 6.6 покупок, поріг 3 — куплений раз є шумом.
Молоко за ті самі 46 днів: очікувано 3.3, поріг 1 — куплене раз лишається.
Побутова хімія: очікувано 0.8, поріг 1 — одна покупка це норма циклу.

Окремо тримаються супутні витратні матеріали (пакети): вони не є вибором
гостя, тому оцінюються часткою чеків, у яких з'явились.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.nutrition.categories import categorize
from app.services import habit_model

# Супутні витратні: беруться разом з іншими покупками, не є окремим вибором
COMPANION_MARKERS = (
    "пакет", "пакунок", "торба", "серветк", "мішк", "фасувальн", "плівк",
)

# Типовий цикл покупки за категорією, у днях.
# Це не наука, а робоча евристика споживчої поведінки — і вона прозора.
CATEGORY_CYCLE_DAYS: dict[str, int] = {
    "veg_fruit": 7,          # свіже беруть щотижня
    "grains": 7,             # хліб теж
    "water": 7,              # воду носять постійно
    "tobacco": 14,           # пачки стиків вистачає приблизно на два тижні
    "dairy": 14,             # молочка живе довше
    "protein": 10,           # м'ясо й риба
    "sweet_drinks": 10,
    "coffee_tea": 21,
    "ultra_processed": 14,   # снеки, ковбаси
    "alcohol": 21,
    "household": 45,         # папір, мило, побутова хімія
    "other": 30,             # соуси, спеції, решта
}
DEFAULT_CYCLE_DAYS = 21

EXPECTED_RATIO = 0.4         # яку частку очікуваних покупок вважаємо звичкою
COMPANION_MIN_SHARE = 0.25   # супутнє лишається, якщо є у чверті чеків

# Звичка — це ПОВТОРЕННЯ. Одна покупка не є звичкою навіть у категорії з
# довгим циклом: ми просто ще не знаємо, чи вона повториться.
#
# Без цього правила адаптивний поріг вироджувався в одиницю майже скрізь
# (46 днів / цикл 14 × 0.4 ≈ 1), і в «звичний кошик» потрапляли чіпси за
# 229 ₴, куплені раз, джин і пиво. Краще показати менше, але правду.
MIN_TIMES = 2
# Закупівля про запас — теж звичка, але тільки якщо обсяг справді помітний
BULK_MIN_UNITS = 4


@dataclass
class Classified:
    kind: str          # regular | companion | noise
    reason: str        # пояснення для деталізації
    habit: Any = None  # розбір звички: розподіл покупок у часі
    threshold: int = 1
    cycle_days: int = DEFAULT_CYCLE_DAYS


def is_companion(name: str) -> bool:
    low = (name or "").lower()
    return any(marker in low for marker in COMPANION_MARKERS)


def cycle_for(name: str) -> int:
    return CATEGORY_CYCLE_DAYS.get(categorize(name), DEFAULT_CYCLE_DAYS)


def threshold_for(name: str, period_days: int) -> tuple[int, int]:
    """Скільки разів товар має з'явитись, щоб вважатись звичним. І цикл категорії."""
    cycle = cycle_for(name)
    expected = max(period_days, 1) / cycle
    return max(1, round(expected * EXPECTED_RATIO)), cycle


def classify(row: dict[str, Any], receipts: int, period_days: int) -> Classified:
    """Визначає, чи товар справді є звичкою.

    Рішення ухвалює habit_model: він дивиться на РОЗПОДІЛ покупок у часі, а не
    лише на їх кількість. Тут лишаються два винятки, яких модель не бачить:
    супутні витратні (пакети) і закупівля про запас.
    """
    times = int(row.get("times") or 0)
    name = row.get("name") or ""

    if is_companion(name):
        share = times / max(receipts, 1)
        if share >= COMPANION_MIN_SHARE:
            return Classified("companion", f"супутнє, є у {round(share * 100)}% ваших чеків")
        return Classified("noise", "супутнє, але береться рідко")

    threshold, cycle = threshold_for(name, period_days)
    quantity = float(row.get("total_qty") or 0)
    habit = habit_model.analyse(row.get("days") or [], period_days, cycle)

    # Вид, у якому жодна марка не повторилась, — не звичка, а перебирання.
    # Тестувальник узяв вісім різних напоїв по разу; за днями це «стабільно»,
    # за суттю — вісім разових покупок з обличчям у вигляді комбучі.
    brands = int(row.get("kind_brands") or 1)
    if brands >= 2 and int(row.get("repeat_brands") or 0) == 0 and habit.kind == habit_model.STABLE:
        habit = habit_model.Habit(
            habit_model.OCCASIONAL,
            f"{brands} різних товарів по одному разу — жоден не повторився",
            habit.days, habit.weeks, habit.span_days, habit.coverage, habit.since_last_days,
        )

    # Закупівля про запас: десять пляшок води за один похід — це запас на
    # тижні вперед, навіть якщо походів було мало.
    bulk = quantity >= max(threshold * 2, BULK_MIN_UNITS)
    if bulk and habit.kind != habit_model.STABLE:
        return Classified(
            "regular", f"берете про запас: {round(quantity)} шт за {period_days} дн.",
            habit, threshold, cycle,
        )

    kind = "regular" if habit.kind == habit_model.STABLE else "noise"
    return Classified(kind, habit.reason, habit, threshold, cycle)


def split(rows: list[dict[str, Any]], receipts: int, period_days: int) -> dict[str, Any]:
    """Ділить агрегати на звичний набір і шум. Шум не ховаємо — показуємо звітом."""
    basket: list[dict[str, Any]] = []
    noise: list[dict[str, Any]] = []

    for row in rows:
        verdict = classify(row, receipts, period_days)
        enriched = {
            **row, "kind": verdict.kind, "kind_reason": verdict.reason,
            "cycle_days": verdict.cycle_days, "threshold": verdict.threshold,
            "habit": verdict.habit.as_dict() if verdict.habit else None,
        }
        (noise if verdict.kind == "noise" else basket).append(enriched)

    basket.sort(key=lambda r: (r["kind"] != "regular", -(r.get("spend") or 0)))
    noise.sort(key=lambda r: -(r.get("spend") or 0))
    def _of_kind(kind: str) -> list[dict[str, Any]]:
        return sorted(
            (r for r in noise if (r.get("habit") or {}).get("kind") == kind),
            key=lambda r: -(r.get("spend") or 0),
        )

    return {
        "basket": basket,
        "noise": noise,
        # Не звичка — але і не сміття: варте окремих слів в інтерфейсі
        "emerging": _of_kind(habit_model.EMERGING),
        "fading": _of_kind(habit_model.FADING),
        "filtered_count": len(noise),
        "filtered_spend": round(sum(r.get("spend") or 0 for r in noise), 2),
    }
