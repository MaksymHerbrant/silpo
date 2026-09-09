"""Заміни: цілі беруться і з чеків (звички), і з кошика.

Кандидатів шукає app/services/swap_engine.py за правилами (без LLM).
Застосування — «розумне»: є активний кошик -> міняємо товар у ньому,
немає -> кладемо здоровішу альтернативу в обране, щоб вона підказалась
у магазині. Обидва шляхи — реальні write-виклики MCP.
"""
from __future__ import annotations

from typing import Any

from app.db import repo
from app.mcp import tools as T
from app.mcp.gateway import silpo
from app.nutrition.parser import parse_product
from app.nutrition.rules import match_rule
from app.nutrition.score import score_product
from app.services import swap_engine
from app.services.cart_analysis import fetch_cart, load_details
from app.services.habits import fetch_offline_orders, load_details_for

MAX_HABIT_PRODUCTS = 12


async def build_suggestions(user_id: str, source: str = "habits") -> list[dict[str, Any]]:
    """source: habits — по всіх чеках; cart — лише поточний кошик."""
    async with silpo(user_id) as api:
        ctx, cart_products, meta = await fetch_cart(api)
        if ctx is None:
            return []

        targets: list[tuple[Any, dict[str, Any]]] = []

        if source in ("cart", "both") and cart_products:
            details = await load_details(api, ctx, [p.get("slug") for p in cart_products])
            for raw in cart_products:
                product = details.get(raw.get("slug"))
                if product is None:
                    continue
                rule = match_rule(product)
                if rule is None:
                    continue
                scored = score_product(product, raw.get("quantity") or 1, bool(raw.get("weighted")))
                targets.append((scored, {
                    "rule": rule, "times": 1, "in_cart": True, "product": product,
                    "external_product_id": raw.get("externalProductId"),
                }))

        if source in ("habits", "both"):
            orders = await fetch_offline_orders(api, ctx)
            frequency: dict[str, dict[str, Any]] = {}
            for order in orders:
                for line in order.items:
                    slug = line.get("slug")
                    if not slug:
                        continue
                    row = frequency.setdefault(slug, {"slug": slug, "times": 0, "title": line.get("name")})
                    row["times"] += line.get("quantity") or 1
            top = sorted(frequency.values(), key=lambda r: -r["times"])[:MAX_HABIT_PRODUCTS]
            details = await load_details_for(api, ctx, [r["slug"] for r in top])
            targets.extend(swap_engine.targets_from_habits(top, details))

        try:
            restrictions_payload = await api.call(T.GET_FOOD_RESTRICTIONS, {})
        except Exception:  # noqa: BLE001
            restrictions_payload = None
        from app.nutrition import allergens as al

        restriction_labels = (
            [] if T.restrictions_are_empty(restrictions_payload)
            else [r.label for r in al.parse_restrictions(restrictions_payload)]
        )
        return await swap_engine.build(user_id, api, ctx, targets, restriction_labels)


async def apply_swap(user_id: str, swap_id: str) -> dict[str, Any]:
    """Розумне застосування: кошик, якщо він є; інакше — обране."""
    swap = await repo.get_swap(user_id, swap_id)
    if not swap:
        raise KeyError("Пропозицію не знайдено")

    async with silpo(user_id) as api:
        ctx, cart_products, _meta = await fetch_cart(api)
        if ctx is None:
            raise RuntimeError("Кошик Сільпо недоступний")

        original = next(
            (p for p in cart_products
             if str(p.get("productId")) == str(swap["original_product_id"])),
            None,
        )

        if original:
            quantity = original.get("quantity") or 1
            added = await api.call(T.ADD_OR_UPDATE_CART, {
                "shoppingCartId": ctx.cart_id,
                "products": [{
                    "productId": swap["suggested_product_id"],
                    "companyId": ctx.company_id,
                    "branchId": ctx.branch_id,
                    "quantity": quantity,
                }],
            })
            # Перевірено наживо: tool очікує products: [{productId}], не productIds
            removed = await api.call(T.REMOVE_CART_PRODUCTS, {
                "shoppingCartId": ctx.cart_id,
                "products": [{"productId": swap["original_product_id"]}],
            })
            await repo.mark_swap(swap_id, accepted=True)
            return {"applied": True, "mode": "cart", "cart_id": ctx.cart_id,
                    "added": added, "removed": removed}

        # Товару в кошику немає (типовий кейс для замін зі звичок) —
        # кладемо здоровішу альтернативу в обране.
        detail = await api.call(
            T.GET_PRODUCT_DETAILS, ctx.product_args(swap.get("suggested_slug") or "")
        )
        external_id = None
        if isinstance(detail, dict):
            external_id = (detail.get("product") or {}).get("externalProductId")
        result = await api.call(T.ADD_OR_UPDATE_FAVORITES, {
            "actions": [{
                "productId": swap["suggested_product_id"],
                "externalProductId": int(external_id or 0),
                "toDelete": False,
            }]
        })

    await repo.mark_swap(swap_id, accepted=True)
    return {"applied": True, "mode": "favorites", "result": result}


async def decline_swap(user_id: str, swap_id: str) -> None:
    if not await repo.get_swap(user_id, swap_id):
        raise KeyError("Пропозицію не знайдено")
    await repo.mark_swap(swap_id, accepted=False)
