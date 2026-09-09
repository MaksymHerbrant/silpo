"""Фільтр шуму: що з чеків справді входить у звичний набір.

Проблема: у чеках повно разових позицій. Людина один раз купила лимон,
екзотичний фрукт чи батарейки — це не її звичка, і в звіті це сміття.

Але просто «викинути все, що куплено раз» — теж помилка: біорозкладні пакети
беруться щоразу під вагові товари, і без них список неповний.

Тому класифікуємо кожну позицію в один із трьох станів:
    regular   — купується систематично, це основа набору
    companion — супутнє витратне (пакети), тримається на частоті ЧЕКІВ
    noise     — разова покупка, у набір не входить
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Супутні витратні матеріали: беруться разом з іншими покупками, не є вибором
COMPANION_MARKERS = (
    "пакет", "пакунок", "торба", "серветк", "мішк", "фасувальн", "плівк",
)

MIN_TIMES_REGULAR = 2          # два рази за період — уже звичка
COMPANION_MIN_SHARE = 0.25     # супутнє лишається, якщо є у чверті чеків


@dataclass
class Classified:
    kind: str          # regular | companion | noise
    reason: str        # чому саме так — показуємо гостю в деталізації


def is_companion(name: str) -> bool:
    low = (name or "").lower()
    return any(marker in low for marker in COMPANION_MARKERS)


def classify(row: dict[str, Any], receipts: int) -> Classified:
    """row: {'name', 'times', 'total_qty'} — агрегат по одному товару."""
    times = int(row.get("times") or 0)
    name = row.get("name") or ""

    if is_companion(name):
        share = times / max(receipts, 1)
        if share >= COMPANION_MIN_SHARE:
            return Classified(
                "companion",
                f"супутнє, є у {round(share * 100)}% ваших чеків",
            )
        return Classified("noise", "супутнє, але береться рідко")

    if times >= MIN_TIMES_REGULAR:
        return Classified("regular", f"купуєте {times} раз(и) за період")

    return Classified("noise", "разова покупка, не входить у звичний набір")


def split(rows: list[dict[str, Any]], receipts: int) -> dict[str, Any]:
    """Ділить агрегати на набір і шум. Повертає і те, і те — шум показуємо
    як звіт агента («відсіяно N випадкових позицій»), а не ховаємо мовчки."""
    basket: list[dict[str, Any]] = []
    noise: list[dict[str, Any]] = []

    for row in rows:
        verdict = classify(row, receipts)
        enriched = {**row, "kind": verdict.kind, "kind_reason": verdict.reason}
        (noise if verdict.kind == "noise" else basket).append(enriched)

    basket.sort(key=lambda r: (r["kind"] != "regular", -r.get("times", 0)))
    noise.sort(key=lambda r: -(r.get("spend") or 0))
    return {
        "basket": basket,
        "noise": noise,
        "filtered_count": len(noise),
        "filtered_spend": round(sum(r.get("spend") or 0 for r in noise), 2),
    }
