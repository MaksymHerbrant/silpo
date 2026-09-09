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

# Супутні витратні: беруться разом з іншими покупками, не є окремим вибором
COMPANION_MARKERS = (
    "пакет", "пакунок", "торба", "серветк", "мішк", "фасувальн", "плівк",
)

# Типовий цикл покупки за категорією, у днях.
# Це не наука, а робоча евристика споживчої поведінки — і вона прозора.
CATEGORY_CYCLE_DAYS: dict[str, int] = {
    "veg_fruit": 7,          # свіже беруть щотижня
    "grains": 7,             # хліб теж
    "dairy": 14,             # молочка живе довше
    "protein": 10,           # м'ясо й риба
    "sweet_drinks": 10,
    "ultra_processed": 14,   # снеки, ковбаси
    "alcohol": 30,
    "other": 30,             # побутове, папір, соуси, спеції
}
DEFAULT_CYCLE_DAYS = 21

EXPECTED_RATIO = 0.4         # яку частку очікуваних покупок вважаємо звичкою
COMPANION_MIN_SHARE = 0.25   # супутнє лишається, якщо є у чверті чеків


@dataclass
class Classified:
    kind: str          # regular | companion | noise
    reason: str        # пояснення для деталізації
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
    """row: агрегат по товару з полями name / times."""
    times = int(row.get("times") or 0)
    name = row.get("name") or ""

    if is_companion(name):
        share = times / max(receipts, 1)
        if share >= COMPANION_MIN_SHARE:
            return Classified("companion", f"супутнє, є у {round(share * 100)}% ваших чеків")
        return Classified("noise", "супутнє, але береться рідко")

    threshold, cycle = threshold_for(name, period_days)
    if times >= threshold:
        if threshold == 1:
            reason = f"категорія з довгим циклом (~{cycle} дн.), одна покупка — це норма"
        else:
            reason = f"купуєте {times} раз(и) за {period_days} дн. (поріг {threshold})"
        return Classified("regular", reason, threshold, cycle)

    return Classified(
        "noise",
        f"разова покупка: для цієї категорії очікується щонайменше {threshold} за період",
        threshold, cycle,
    )


def split(rows: list[dict[str, Any]], receipts: int, period_days: int) -> dict[str, Any]:
    """Ділить агрегати на звичний набір і шум. Шум не ховаємо — показуємо звітом."""
    basket: list[dict[str, Any]] = []
    noise: list[dict[str, Any]] = []

    for row in rows:
        verdict = classify(row, receipts, period_days)
        enriched = {
            **row, "kind": verdict.kind, "kind_reason": verdict.reason,
            "cycle_days": verdict.cycle_days, "threshold": verdict.threshold,
        }
        (noise if verdict.kind == "noise" else basket).append(enriched)

    basket.sort(key=lambda r: (r["kind"] != "regular", -(r.get("spend") or 0)))
    noise.sort(key=lambda r: -(r.get("spend") or 0))
    return {
        "basket": basket,
        "noise": noise,
        "filtered_count": len(noise),
        "filtered_spend": round(sum(r.get("spend") or 0 for r in noise), 2),
    }
