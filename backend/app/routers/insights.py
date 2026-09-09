"""Аналіз покупок і звичний кошик — головні екрани застосунку."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.db import repo
from app.mcp import tools as T
from app.mcp.gateway import silpo
from app.security.session import current_user_id
from app.services import habits, insights, jobs
from app.services.cart_analysis import fetch_cart

router = APIRouter(tags=["insights"])


async def _load(user_id: str, builder) -> dict[str, Any]:
    goal_row = await repo.get_goal(user_id) or {}

    async def _factory() -> dict[str, Any]:
        async with silpo(user_id) as api:
            ctx, _cart, meta = await fetch_cart(api)
            if ctx is None:
                return {"has_data": False, "reason": meta.get("reason", "Дані Сільпо недоступні")}
            orders = await habits.fetch_offline_orders(api, ctx)
            return await builder(api, ctx, orders, goal_row)

    return _factory


@router.get("/insights/overview")
async def overview(
    refresh: bool = False, user_id: str = Depends(current_user_id)
) -> dict[str, Any]:
    """Дзеркало покупок: гроші, топ товарів, категорії, динаміка по тижнях."""
    if refresh:
        jobs.invalidate("insights", user_id)

    async def builder(api, ctx, orders, goal_row):
        return await insights.build(api, ctx, orders, goal_row.get("goal"))

    factory = await _load(user_id, builder)
    return await jobs.cached_or_start("insights", user_id, factory)


@router.get("/basket/usual")
async def usual(refresh: bool = False, user_id: str = Depends(current_user_id)) -> dict[str, Any]:
    """Звичний тижневий набір гостя з актуальними цінами й акціями."""
    if refresh:
        jobs.invalidate("usual", user_id)

    async def builder(api, ctx, orders, _goal_row):
        return await insights.usual_basket(api, ctx, orders)

    factory = await _load(user_id, builder)
    return await jobs.cached_or_start("usual", user_id, factory)


@router.post("/basket/usual/apply")
async def apply_usual(
    payload: dict[str, Any], user_id: str = Depends(current_user_id)
) -> dict[str, Any]:
    """Додає обрані гостем позиції в кошик Сільпо. Тільки те, що він позначив."""
    selected = payload.get("items") or []
    if not selected:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Не обрано жодної позиції")

    async with silpo(user_id) as api:
        ctx, _cart, _meta = await fetch_cart(api)
        if ctx is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Кошик Сільпо недоступний")
        result = await api.call(T.ADD_OR_UPDATE_CART, {
            "shoppingCartId": ctx.cart_id,
            "products": [
                {
                    "productId": item["product_id"],
                    "quantity": int(item.get("quantity") or 1),
                    "companyId": ctx.company_id,
                    "branchId": ctx.branch_id,
                }
                for item in selected if item.get("product_id")
            ],
        })
        _c, after, _m = await fetch_cart(api)

    return {
        "applied": True,
        "added": len(selected),
        "cart_now": [{"name": p.get("name"), "quantity": p.get("quantity")} for p in after],
        "mcp_result": result,
    }
