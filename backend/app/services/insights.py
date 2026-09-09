"""Аналіз покупок — фундамент продукту.

Спершу розуміння, потім будь-які поради. Без цього рекомендація — це
повчання, а з ним — обґрунтований факт про самого гостя.

Правило тону: жодних оцінок «добре/погано». Ми показуємо, що людина купує,
скільки це коштує і де вона переплачує. Висновки робить вона сама.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from app.mcp import tools as T
from app.nutrition import categories as cats
from app.nutrition.parser import parse_product

MAX_DETAIL_LOOKUPS = 18


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


async def build(api, ctx: T.CartContext, orders, goal: str | None = None) -> dict[str, Any]:
    """Повна картина покупок гостя за наявними чеками."""
    if not orders:
        return {"has_data": False, "reason": "Чеків Сільпо поки не знайшли"}

    lines = [line for order in orders for line in order.items]
    period_days = (
        max((orders[0].created_at - orders[-1].created_at).days, 1) if len(orders) > 1 else 1
    )
    total_spend = sum(o.total for o in orders)
    total_saved = sum(o.discount for o in orders)

    # --- топ товарів: не просто частота, а частота В ГРОШАХ ---
    products: dict[str, dict[str, Any]] = {}
    for line in lines:
        name = line.get("name") or ""
        if not name:
            continue
        row = products.setdefault(name, {
            "name": name, "slug": line.get("slug"), "times": 0, "spend": 0.0,
            "image": line.get("image"), "last_price": line.get("price"),
        })
        row["times"] += 1
        row["spend"] += float(line.get("price") or 0) * float(line.get("quantity") or 1)

    top_by_spend = sorted(products.values(), key=lambda r: -r["spend"])[:10]
    top_by_times = sorted(products.values(), key=lambda r: -r["times"])[:10]
    for row in top_by_spend:
        row["spend"] = round(row["spend"], 2)
        row["share_of_spend"] = round(row["spend"] / (total_spend or 1) * 100, 1)

    # --- категорії витрат ---
    structure = cats.analyse(lines, goal)

    # --- динаміка по тижнях ---
    by_week: dict[date, dict[str, float]] = defaultdict(lambda: {"spend": 0.0, "saved": 0.0, "visits": 0})
    for order in orders:
        week = _week_start(order.created_at.date())
        by_week[week]["spend"] += order.total
        by_week[week]["saved"] += order.discount
        by_week[week]["visits"] += 1
    weeks = [
        {
            "week": week.isoformat(),
            "spend": round(values["spend"], 2),
            "saved": round(values["saved"], 2),
            "visits": int(values["visits"]),
        }
        for week, values in sorted(by_week.items())
    ]

    # --- магазини ---
    branches: dict[str, float] = defaultdict(float)
    for order in orders:
        branches[order.branch] += order.total
    favourite = max(branches.items(), key=lambda x: x[1])[0] if branches else None

    return {
        "has_data": True,
        "period": {
            "days": period_days,
            "receipts": len(orders),
            "first": orders[-1].created_at.date().isoformat(),
            "last": orders[0].created_at.date().isoformat(),
        },
        "money": {
            "total_spend": round(total_spend, 2),
            "total_saved": round(total_saved, 2),
            "avg_check": round(total_spend / len(orders), 2),
            "per_week": round(total_spend / max(period_days / 7, 1), 2),
            "visits_per_week": round(len(orders) / max(period_days / 7, 1), 1),
            "saved_share": round(total_saved / (total_spend + total_saved) * 100, 1),
        },
        "top_by_spend": top_by_spend,
        "top_by_times": [
            {**r, "spend": round(r["spend"], 2)} for r in top_by_times
        ],
        "categories": structure.as_dict(),
        "weeks": weeks,
        "favourite_branch": favourite,
        "distinct_products": len(products),
    }


async def usual_basket(api, ctx: T.CartContext, orders, weeks_back: int = 4) -> dict[str, Any]:
    """Реконструює типовий тижневий набір гостя з чеків.

    Це не «правильний» кошик і не поради — це те, що людина бере сама.
    Беремо товари, які повторюються, рахуємо середню тижневу кількість
    і підтягуємо АКТУАЛЬНУ ціну та ознаку акції з каталогу.
    """
    if not orders:
        return {"items": [], "reason": "Немає чеків для реконструкції"}

    period_days = (
        max((orders[0].created_at - orders[-1].created_at).days, 7) if len(orders) > 1 else 7
    )
    weeks = max(period_days / 7, 1)

    counts: dict[str, dict[str, Any]] = {}
    for order in orders:
        for line in order.items:
            slug = line.get("slug")
            if not slug:
                continue
            row = counts.setdefault(slug, {
                "slug": slug, "name": line.get("name"), "total_qty": 0.0,
                "times": 0, "image": line.get("image"),
            })
            row["total_qty"] += float(line.get("quantity") or 1)
            row["times"] += 1

    # У звичний набір беремо те, що куплено щонайменше двічі за період
    regulars = [r for r in counts.values() if r["times"] >= 2]
    regulars.sort(key=lambda r: -r["times"])
    regulars = regulars[:MAX_DETAIL_LOOKUPS]

    items: list[dict[str, Any]] = []
    for row in regulars:
        try:
            payload = await api.call(T.GET_PRODUCT_DETAILS, ctx.product_args(row["slug"]))
        except Exception:  # noqa: BLE001
            continue
        if T.is_mcp_error(payload):
            continue
        product = parse_product(payload, fallback_slug=row["slug"], fallback_title=row["name"] or "")
        per_week = max(round(row["total_qty"] / weeks), 1)
        items.append({
            "slug": product.slug,
            "product_id": product.product_id,
            "name": product.title,
            "image": product.image or row.get("image"),
            "quantity": per_week,
            "price": product.price,
            "old_price": product.old_price,
            "saved": product.discount,
            "on_promotion": product.on_promotion,
            "category": cats.categorize(product.title),
            "times_bought": row["times"],
            "line_total": round((product.price or 0) * per_week, 2),
        })

    total = sum(i["line_total"] for i in items)
    saved = sum((i["saved"] or 0) * i["quantity"] for i in items)
    return {
        "items": items,
        "total_price": round(total, 2),
        "saved_now": round(saved, 2),
        "promo_items": sum(1 for i in items if i["on_promotion"]),
        "based_on_weeks": round(weeks, 1),
    }
