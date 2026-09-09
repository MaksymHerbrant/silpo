"""Аналіз кошика за фактичною схемою MCP Сільпо.

Порядок викликів:
1. silpo_get_my_shopping_cart      -> shoppingCartId
2. silpo_get_shopping_cart_by_id   -> контекст (branchId, deliveryType, timeslot) + товари
3. silpo_get_time_slots            -> валідація контексту доставки
4. silpo_get_product_details       -> по одному на товар (slug + контекст), з throttle
5. silpo_get_my_food_restrictions  -> дієтичні обмеження гостя
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.db import repo
from app.mcp import tools as T
from app.mcp.gateway import silpo
from app.nutrition import allergens as al
from app.nutrition.parser import ProductInfo, parse_product
from app.nutrition.score import ScoredItem, score_basket, score_product


async def fetch_cart(api) -> tuple[T.CartContext | None, list[dict[str, Any]], dict[str, Any]]:
    head = await api.call(T.GET_MY_CART, {})
    cart_id = head.get("shoppingCartId") if isinstance(head, dict) else None
    if not cart_id:
        return None, [], {"reason": "Активний кошик Сільпо не знайдено"}

    cart_payload = await api.call(T.GET_CART_BY_ID, {"shoppingCartId": str(cart_id)})
    error = T.is_mcp_error(cart_payload)
    if error:
        return None, [], {"reason": f"Кошик недоступний: {error[:120]}"}

    ctx = T.cart_context(cart_payload, str(cart_id))
    products = T.cart_products(cart_payload)
    return ctx, products, {"raw_cart": cart_payload}


async def load_details(api, ctx: T.CartContext, slugs: list[str]) -> dict[str, ProductInfo]:
    """Послідовно (через throttle) тягне деталі. 20+ паралельних викликів = 429."""
    out: dict[str, ProductInfo] = {}
    for slug in slugs:
        if not slug or slug in out:
            continue
        try:
            payload = await api.call(T.GET_PRODUCT_DETAILS, ctx.product_args(slug))
        except Exception:  # noqa: BLE001 — один товар не має валити весь аналіз
            continue
        if T.is_mcp_error(payload):
            continue
        out[slug] = parse_product(payload, fallback_slug=slug)
    return out


async def analyze_cart(user_id: str) -> dict[str, Any]:
    async with silpo(user_id) as api:
        ctx, raw_products, meta = await fetch_cart(api)
        if ctx is None:
            return {"empty": True, "reason": meta.get("reason", "Кошик порожній"), "items": [], "score": None}
        if not raw_products:
            return {
                "cart_id": ctx.cart_id, "empty": True, "items": [], "score": None,
                "reason": "У кошику Сільпо зараз немає товарів",
            }

        # Валідація контексту доставки перед product-запитами
        try:
            await api.call(
                T.GET_TIME_SLOTS,
                {"branchId": ctx.branch_id, "deliveryTypes": [ctx.delivery_type], "limit": 5},
            )
        except Exception:  # noqa: BLE001 — не блокує аналіз
            pass

        details = await load_details(api, ctx, [p.get("slug") for p in raw_products])

        try:
            restrictions_payload = await api.call(T.GET_FOOD_RESTRICTIONS, {})
        except Exception:  # noqa: BLE001
            restrictions_payload = None

    restrictions = (
        [] if T.restrictions_are_empty(restrictions_payload)
        else al.parse_restrictions(restrictions_payload)
    )
    has_profile_restrictions = bool(restrictions)

    scored: list[ScoredItem] = []
    hits: list[al.AllergenHit] = []
    for raw in raw_products:
        slug = raw.get("slug")
        product = details.get(slug)
        if product is None:
            scored.append(
                ScoredItem(
                    product_id=str(raw.get("productId") or ""), slug=str(slug or ""),
                    title=str(raw.get("name") or slug or "Товар"), brand=None,
                    image=raw.get("image"), quantity=raw.get("quantity") or 1,
                    grams=None, price=raw.get("price"), is_own_brand=False, is_alcohol=False,
                    has_nutrition=False, nutrition=None, score=None, letter=None,
                    note="Деталі товару не завантажились",
                )
            )
            continue
        item = score_product(product, raw.get("quantity") or 1, bool(raw.get("weighted")))
        scored.append(item)
        hits.extend(al.check_product(product, restrictions))

    basket = score_basket(scored)
    items_payload = [_item_dict(i) for i in scored]
    await repo.cache_cart_analysis(user_id, ctx.cart_id, items_payload, basket.score)

    return {
        "cart_id": ctx.cart_id,
        "branch_id": ctx.branch_id,
        "delivery_type": ctx.delivery_type,
        "timeslot": {"start": ctx.timeslot_start, "end": ctx.timeslot_end},
        "empty": False,
        "score": basket.score,
        "letter": basket.letter,
        "shares": basket.shares,
        "deviations": basket.deviations,
        "energy_density": basket.energy_density,
        "penalties": basket.penalties,
        "totals": basket.totals,
        "coverage": {
            "covered": basket.covered_items,
            "skipped": basket.skipped_items,
            "pct": basket.coverage_pct,
        },
        "methodology": basket.methodology,
        "items": items_payload,
        "restrictions": [r.label for r in restrictions],
        "has_profile_restrictions": has_profile_restrictions,
        "allergen_warnings": [asdict(h) for h in hits],
    }


def _item_dict(i: ScoredItem) -> dict[str, Any]:
    return {
        "product_id": i.product_id,
        "slug": i.slug,
        "title": i.title,
        "brand": i.brand,
        "image": i.image,
        "quantity": i.quantity,
        "grams": i.grams,
        "price": i.price,
        "is_own_brand": i.is_own_brand,
        "is_alcohol": i.is_alcohol,
        "has_nutrition": i.has_nutrition,
        "score": i.score,
        "letter": i.letter,
        "shares": i.shares,
        "kcal_total": i.kcal_total,
        "note": i.note,
        "allergens_text": i.allergens_text,
        "nutrition": (
            {
                "energy_kcal": i.nutrition.energy_kcal,
                "protein": i.nutrition.protein,
                "fat": i.nutrition.fat,
                "carbs": i.nutrition.carbs,
                "missing": i.nutrition.missing,
            }
            if i.nutrition else None
        ),
    }
