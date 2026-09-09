"""План наступної покупки: знахідки, рішення, дія."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db import repo
from app.mcp import tools as T
from app.mcp.gateway import silpo
from app.security.session import current_user_id
from app.services import habits, jobs, plan as plan_service
from app.services.cart_analysis import fetch_cart

router = APIRouter(tags=["plan"])


class PlanItemIn(BaseModel):
    product_id: str
    quantity: int = 1
    name: str | None = None


class ApplyIn(BaseModel):
    items: list[PlanItemIn]


@router.get("/plan")
async def get_plan(refresh: bool = False, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    """Знахідки агента + план покупки. Довга операція йде у фон із кешем."""
    if refresh:
        jobs.invalidate("plan_next", user_id)

    goal_row = await repo.get_goal(user_id) or {}

    async def _factory() -> dict[str, Any]:
        async with silpo(user_id) as api:
            ctx, _cart, meta = await fetch_cart(api)
            if ctx is None:
                return {"has_data": False, "reason": meta.get("reason", "Дані Сільпо недоступні")}
            orders = await habits.fetch_offline_orders(api, ctx)
            return await plan_service.build(api, ctx, orders, goal_row.get("goal"))

    return await jobs.cached_or_start("plan_next", user_id, _factory)


@router.post("/plan/cart")
async def to_cart(payload: ApplyIn, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    """Створює онлайн-кошик Сільпо з позицій, які гість позначив."""
    if not payload.items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Не обрано жодної позиції")

    async with silpo(user_id) as api:
        ctx, _cart, _meta = await fetch_cart(api)
        if ctx is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Кошик Сільпо недоступний")
        result = await api.call(T.ADD_OR_UPDATE_CART, {
            "shoppingCartId": ctx.cart_id,
            "products": [
                {
                    "productId": item.product_id,
                    "quantity": max(item.quantity, 1),
                    "companyId": ctx.company_id,
                    "branchId": ctx.branch_id,
                }
                for item in payload.items
            ],
        })
        # Перечитуємо кошик — це і є доказ, що запис справді відбувся
        _c, after, _m = await fetch_cart(api)

    return {
        "applied": True,
        "added": len(payload.items),
        "cart_total": round(sum(float(p.get("total") or 0) for p in after), 2),
        "cart_now": [{"name": p.get("name"), "quantity": p.get("quantity")} for p in after],
        "checkout_hint": "Відкрийте кошик у застосунку Сільпо, щоб підтвердити замовлення",
        "mcp_result": result,
    }


@router.post("/plan/list")
async def to_list(payload: ApplyIn, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    """Офлайн-варіант: список за категоріями, у порядку обходу магазину."""
    cached = jobs.get_cached("plan_next", user_id) or {}
    by_id = {i["product_id"]: i for i in (cached.get("items") or [])}

    groups: dict[str, list[dict[str, Any]]] = {}
    for item in payload.items:
        source = by_id.get(item.product_id, {})
        category = source.get("category", "other")
        groups.setdefault(category, []).append({
            "name": source.get("name") or item.name or "Товар",
            "quantity": item.quantity,
            "price": source.get("price"),
            "on_promotion": source.get("on_promotion", False),
            "note": source.get("note", ""),
        })

    from app.nutrition.categories import CATEGORY_LABELS

    total = sum(
        (row.get("price") or 0) * row["quantity"] for rows in groups.values() for row in rows
    )
    return {
        "groups": [
            {"category": key, "label": CATEGORY_LABELS.get(key, "Інше"), "items": rows}
            for key, rows in groups.items()
        ],
        "items": sum(len(r) for r in groups.values()),
        "total_price": round(total, 2),
    }
