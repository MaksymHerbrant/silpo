"""Стеження за цінами того, що гість купує регулярно.

Чому не «обране»: silpo_get_my_favorites повертає помилку на боці Сільпо
(«Cannot read properties of null»), перевірено наживо на трьох варіантах
аргументів. Та й регулярні покупки — це реальна поведінка, а список обраного
може бути порожнім чи забутим.

Падіння ціни фіксуємо лише коли воно варте уваги: і в гривнях, і у відсотках.
Інакше кожні 50 копійок коливання перетворилися б на сповіщення.
"""
from __future__ import annotations

from typing import Any

MIN_DROP_UAH = 5.0
MIN_DROP_PCT = 5.0


def compare(items: list[dict[str, Any]], stored: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Порівнює поточні ціни з попереднім знімком.

    Повертає падіння та новий знімок для запису. Товар, який бачимо вперше,
    падінням не вважається — з чим порівнювати ще немає.
    """
    drops: list[dict[str, Any]] = []
    snapshot: list[dict[str, Any]] = []

    for item in items:
        slug = item.get("slug")
        price = item.get("price")
        if not slug or not price:
            continue
        previous = stored.get(slug) or {}
        last = previous.get("last_price")
        last = float(last) if last is not None else None
        low = previous.get("min_price")
        low = float(low) if low is not None else None

        if last is not None and price < last:
            delta = last - price
            pct = delta / last * 100
            if delta >= MIN_DROP_UAH and pct >= MIN_DROP_PCT:
                drops.append({
                    "slug": slug,
                    "product_id": item.get("product_id"),
                    "name": item.get("name"),
                    "image": item.get("image"),
                    "price": price,
                    "was": round(last, 2),
                    "saved": round(delta, 2),
                    "pct": round(pct),
                    "lowest_seen": low is not None and price <= low,
                })

        snapshot.append({
            "slug": slug,
            "product_id": item.get("product_id"),
            "name": item.get("name"),
            "last_price": price,
            "min_price": price if low is None else min(low, price),
        })

    drops.sort(key=lambda d: -d["saved"])
    return {
        "drops": drops,
        "snapshot": snapshot,
        "tracked": len(snapshot),
        "total_saved": round(sum(d["saved"] for d in drops), 2),
    }


def digest_line(drop: dict[str, Any]) -> str:
    tail = " — найнижча ціна за час стеження" if drop["lowest_seen"] else ""
    return f"• {drop['name']} — {round(drop['price'])} ₴ замість {round(drop['was'])} ₴ (−{drop['pct']}%){tail}"
