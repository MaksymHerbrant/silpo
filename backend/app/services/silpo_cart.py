"""Кошик, який гість уже зібрав у Сільпо.

Сценарій, заради якого це існує: людина зайшла в застосунок Сільпо й склала
кошик сама. Вона не хоче, щоб ми його переписували. Але їй корисно почути
дві речі, і обидві ми можемо сказати з її ж історії:

    «ви зазвичай берете хліб, а його в кошику немає»
    «сир у кошику зараз є дешевший — ви й так берете різні марки»

Це НЕ частина кешованого плану. План перебудовується раз на новий чек, а
кошик змінюється щохвилини — тому читаємо його наживо, окремим дешевим
запитом, і звіряємо з уже порахованим ядром звичок.
"""
from __future__ import annotations

from typing import Any

from app.services import kinds

# Скільки забутих позицій показувати: довгий список читається як докір
MAX_FORGOTTEN = 5


def _line(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": product.get("name"),
        "slug": product.get("slug"),
        "product_id": str(product.get("productId") or product.get("id") or ""),
        "quantity": int(float(product.get("quantity") or 1)),
        "price": float(product.get("price") or 0),
        "total": float(product.get("total") or 0),
    }


def compare(cart_products: list[dict[str, Any]], plan: dict[str, Any] | None) -> dict[str, Any]:
    """Звіряє готовий кошик Сільпо зі звичним набором гостя."""
    items = [_line(p) for p in cart_products if p.get("name")]
    in_cart_kinds = {kinds.kind_of(i["name"]) for i in items}

    basket = [
        i for i in ((plan or {}).get("items") or [])
        if i.get("action") != "blocked" and i.get("kind") != "companion"
    ]

    forgotten: list[dict[str, Any]] = []
    for item in basket:
        kind = item.get("kind_key") or kinds.kind_of(item.get("name") or "")
        if kind in in_cart_kinds:
            continue
        forgotten.append({
            "slug": item.get("slug"),
            "product_id": item.get("product_id"),
            "name": item.get("name"),
            "image": item.get("image"),
            "price": item.get("price"),
            "quantity": item.get("quantity", 1),
            "kind": kind,
            "why": item.get("kind_note") or item.get("kind_reason") or "",
            "on_promotion": bool(item.get("on_promotion")),
        })

    # Спершу те, що зараз в акції, потім дорожче — там більша ціна забудькуватості
    forgotten.sort(key=lambda r: (not r["on_promotion"], -(r.get("price") or 0)))

    # Позиції кошика, для яких у плані є вигідніша марка того ж виду
    better: list[dict[str, Any]] = []
    by_kind = {
        (i.get("kind_key") or kinds.kind_of(i.get("name") or "")): i
        for i in basket if i.get("alternative")
    }
    for line in items:
        habit = by_kind.get(kinds.kind_of(line["name"]))
        if not habit:
            continue
        alt = habit["alternative"]
        if (alt.get("saved") or 0) <= 0 or alt.get("slug") == line.get("slug"):
            continue
        better.append({
            "in_cart": line["name"],
            "slug": alt.get("slug"),
            "product_id": alt.get("product_id"),
            "name": alt.get("name"),
            "price": alt.get("price"),
            "saved": alt.get("saved"),
            "why": alt.get("why"),
        })

    return {
        "items": items,
        "count": len(items),
        "total": round(sum(i["total"] or i["price"] * i["quantity"] for i in items), 2),
        "forgotten": forgotten[:MAX_FORGOTTEN],
        "forgotten_total": len(forgotten),
        "better": better[:3],
        "has_plan": bool(basket),
    }
